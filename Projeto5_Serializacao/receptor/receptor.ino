/*****************************************************
 * Camada Fisica da Computacao
 * Projeto 5 - Serializacao UART "na mao"  --  RECEPTOR
 *
 * Recebe o frame UART em um pino digital QUALQUER (pino 2), sem usar o chip
 * UART do Arduino, e imprime o caractere no monitor serial do PC.
 *
 * Como o receptor se sincroniza (o ponto central do projeto):
 *
 *   A linha fica em ALTO quando esta em repouso. O START e um BAIXO, ou seja,
 *   produz uma BORDA DE DESCIDA -- e e essa borda que da o "tiro de largada".
 *   A interrupcao externa INT0 (que no Uno mora no pino 2) avisa o instante
 *   exato dessa borda.
 *
 *   A partir dai o Timer1 conta os instantes de leitura. E aqui esta o
 *   detalhe que o enunciado destaca: NAO se pode ler nos instantes de
 *   transicao do nivel logico. Entao a primeira espera e de MEIO periodo de
 *   bit, o que joga a leitura para o MEIO do start bit; da em diante as
 *   leituras acontecem de 1 periodo em 1 periodo, sempre caindo no meio de
 *   cada bit -- o ponto mais longe possivel das duas bordas vizinhas.
 *
 *     linha  ‾‾‾‾|____ START ____|--D0--|--D1--| ...
 *                 ^              ^      ^
 *                 |              |      |
 *              borda:         meio do  meio do    <- momentos de leitura,
 *            dispara INT0     start     D0           marcados pelo Timer1
 *                 |<-- 1/2 bit -->|<-1 bit->|
 *
 *   A leitura do meio do start bit ainda serve de conferencia: se naquele
 *   instante a linha ja voltou para ALTO, a borda era so um ruido e o frame
 *   e descartado sem estragar a sincronizacao.
 *
 * Nao ha delay() nem delayMicroseconds() em lugar nenhum: quem conta o tempo
 * e o Timer1, por hardware.
 *
 * Ligacao: pino 2 deste Arduino <- pino 8 do Arduino transmissor
 *          GND deste Arduino    <- GND do Arduino transmissor
 *
 * ATENCAO: os pinos RESET *NAO* devem estar ligados no GND neste projeto.
 *****************************************************/

// ---- Configuracao ---------------------------------------------------------
const uint8_t  PINO_RX  = 2;       // precisa ser 2 ou 3: sao os pinos de
                                   // interrupcao externa (INT0 / INT1) do Uno
const uint32_t BAUDRATE = 9600;    // tem que ser igual ao do transmissor

// O codigo liga e desliga a interrupcao externa na mao (registradores EIMSK e
// EIFR), entao o numero da interrupcao precisa combinar com o pino escolhido:
//   pino 2 -> INT0 / INTF0        pino 3 -> INT1 / INTF1
// Trocando o PINO_RX acima, troque tambem estas duas linhas.
#define MASCARA_INT   (1 << INT0)     // liga/desliga a interrupcao externa
#define MASCARA_FLAG  (1 << INTF0)    // flag "houve borda", limpo escrevendo 1

// ---- Base de tempo (mesma conta do transmissor) ---------------------------
// Timer1 em CTC com prescaler 8: OCR1A = F_CPU / (8 * BAUDRATE) - 1
const uint16_t TICKS_POR_BIT = F_CPU / 8UL / BAUDRATE;
const uint16_t OCR_BIT       = TICKS_POR_BIT - 1;
const uint16_t OCR_MEIO_BIT  = (TICKS_POR_BIT / 2) - 1;

// ---- Estado da recepcao ---------------------------------------------------
const uint8_t PARADO    = 0;   // esperando a borda de descida do start
const uint8_t CONFERE   = 1;   // vai ler o meio do start bit
const uint8_t RECEBENDO = 2;   // lendo dados, paridade e stop

volatile uint8_t estado = PARADO;
volatile uint8_t amostra;      // 0..7 dados, 8 paridade, 9 stop
volatile uint8_t dado;         // byte sendo remontado
volatile uint8_t paridadeRx;   // bit de paridade que veio na linha

// Resultado entregue ao loop()
volatile bool    temByte = false;
volatile uint8_t byteRecebido;
volatile bool    erroParidade;
volatile bool    erroFrame;    // stop bit nao veio em nivel alto
volatile uint16_t ruidos = 0;  // bordas descartadas por falso start

// ---- Paridade -------------------------------------------------------------
uint8_t calculaParidadePar(uint8_t d) {
  uint8_t uns = 0;
  for (uint8_t i = 0; i < 8; i++) {
    uns += (d >> i) & 0x01;
  }
  return uns % 2;
}

// ---- Interrupcao externa: chegou a borda de descida do start bit ----------
void bordaDeStart() {
  if (estado != PARADO) {
    return;                            // ja estamos no meio de um frame
  }

  // Desliga a INT0 durante o frame: as bordas dos bits de dados nao devem
  // ser confundidas com o inicio de um novo caractere.
  EIMSK &= ~MASCARA_INT;

  estado  = CONFERE;
  amostra = 0;
  dado    = 0;

  TCNT1   = 0;
  OCR1A   = OCR_MEIO_BIT;              // primeira leitura: meio do start bit
  TIFR1   = (1 << OCF1A);              // descarta comparacao pendente
                                       // (flag se limpa ESCREVENDO 1, por isso '='
                                       //  e nao '|=': com |= as outras flags que
                                       //  estivessem em 1 seriam limpas junto)
  TIMSK1 |= (1 << OCIE1A);             // liga o Timer1
}

// ---- Interrupcao do Timer1: um instante de leitura ------------------------
ISR(TIMER1_COMPA_vect) {
  uint8_t nivel = digitalRead(PINO_RX);

  if (estado == CONFERE) {
    if (nivel == HIGH) {
      // No meio do start bit a linha deveria estar BAIXA. Se esta alta, a
      // borda era ruido: aborta e volta a esperar, sem sujar o proximo frame.
      ruidos++;
      TIMSK1 &= ~(1 << OCIE1A);
      estado  = PARADO;
      EIFR    = MASCARA_FLAG;          // ver comentario no fim desta ISR
      EIMSK  |= MASCARA_INT;
      return;
    }
    // Start valido. Daqui para a frente, uma leitura por periodo de bit,
    // sempre no meio de cada um.
    TCNT1  = 0;
    OCR1A  = OCR_BIT;
    estado = RECEBENDO;
    return;
  }

  // estado == RECEBENDO
  if (amostra < 8) {
    // Remonta o byte com bit shift e OR, como pede o enunciado. Os dados vem
    // com o bit menos significativo primeiro, entao a amostra n entra na
    // posicao n.
    dado |= (uint8_t)(nivel & 0x01) << amostra;
    amostra++;
    return;
  }

  if (amostra == 8) {
    paridadeRx = nivel;                // bit de paridade
    amostra++;
    return;
  }

  // amostra == 9: bit de stop, ultimo do frame
  byteRecebido = dado;
  erroParidade = (paridadeRx != calculaParidadePar(dado));
  erroFrame    = (nivel != HIGH);      // stop bit tem que ser alto
  temByte      = true;

  TIMSK1 &= ~(1 << OCIE1A);            // frame terminou: desliga o Timer1
  estado  = PARADO;

  // As bordas dos bits que acabamos de receber marcaram o flag da INT0 mesmo
  // com ela desabilitada. Se nao limpassemos esse flag (escrevendo 1 nele,
  // que e como se limpa flag de interrupcao no AVR), a INT0 dispararia na
  // hora em que fosse religada e o receptor comecaria a "receber" um frame
  // que nunca existiu.
  EIFR   = MASCARA_FLAG;
  EIMSK |= MASCARA_INT;
}

// ---- Setup / loop ---------------------------------------------------------
void setup() {
  pinMode(PINO_RX, INPUT_PULLUP);   // pull-up segura a linha em repouso (alto)
                                    // caso o fio esteja solto

  // Serial "de verdade" (pinos 0/1, via USB) usada SO para conferir o que
  // chegou, como o enunciado permite.
  Serial.begin(115200);
  Serial.println(F("=== Projeto 5 - RECEPTOR UART por software ==="));
  Serial.print(F("Pino de recepcao : D"));  Serial.println(PINO_RX);
  Serial.print(F("Baudrate         : "));   Serial.println(BAUDRATE);
  Serial.println(F("Frame            : 1 start, 8 dados (LSB primeiro), 1 paridade par, 1 stop"));
  Serial.println();

  // Timer1: CTC, prescaler 8. So passa a interromper quando um frame comeca.
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS11);
  OCR1A  = OCR_BIT;
  TIMSK1 = 0;

  // INT0 (pino 2) na borda de descida = inicio do start bit.
  attachInterrupt(digitalPinToInterrupt(PINO_RX), bordaDeStart, FALLING);
}

void loop() {
  static uint32_t recebidos = 0;
  static uint32_t comErro   = 0;

  if (!temByte) {
    return;
  }

  // Copia o resultado com as interrupcoes desligadas: sao varias variaveis, e
  // um frame novo poderia chegar no meio da leitura e misturar os dois.
  noInterrupts();
  uint8_t d      = byteRecebido;
  bool    erroP  = erroParidade;
  bool    erroF  = erroFrame;
  uint16_t r     = ruidos;   // 16 bits: leitura nao e atomica no AVR
  temByte = false;
  interrupts();

  recebidos++;
  if (erroP || erroF) {
    comErro++;
  }

  Serial.print(F("recebido '"));
  Serial.print((char)d);
  Serial.print(F("'  ASCII "));
  Serial.print(d);
  Serial.print(F("  0b"));
  for (int8_t i = 7; i >= 0; i--) {
    Serial.print((d >> i) & 1);
  }

  if (erroP) {
    Serial.print(F("  <<< ERRO DE PARIDADE"));
  }
  if (erroF) {
    Serial.print(F("  <<< ERRO DE FRAME (stop bit invalido)"));
  }
  if (!erroP && !erroF) {
    Serial.print(F("  ok"));
  }

  Serial.print(F("   [")); Serial.print(recebidos);
  Serial.print(F(" recebidos, ")); Serial.print(comErro);
  Serial.print(F(" com erro, ")); Serial.print(r);
  Serial.print(F(" ruidos]"));
  Serial.println();
}
