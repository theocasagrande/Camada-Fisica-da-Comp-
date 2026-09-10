/*****************************************************
 * Camada Fisica da Computacao
 * Projeto 5 - Serializacao UART "na mao"  --  TRANSMISSOR
 *
 * Produz o frame UART em um pino digital QUALQUER (pino 8), sem usar o chip
 * UART do Arduino. Os pinos 0 e 1 nao podem ser usados porque sao justamente
 * os que ligam o ATmega ao chip USB (e sao usados pelo monitor serial).
 *
 * Frame gerado, 11 bits por caractere (padrao 8E1):
 *
 *   repouso  START   D0 D1 D2 D3 D4 D5 D6 D7   P   STOP   repouso
 *     '1'     '0'    <---- dados, LSB primeiro ---> par    '1'      '1'
 *
 *   - linha em repouso fica em nivel ALTO;
 *   - o START e um BAIXO de 1 bit, que avisa o receptor que o frame comecou;
 *   - os 8 bits do caractere (tabela ASCII) vao do menos significativo para o
 *     mais significativo, que e a ordem do padrao UART;
 *   - a PARIDADE e PAR: o bit vale 1 ou 0 de forma que a quantidade total de
 *     bits '1' (dados + paridade) seja par;
 *   - o STOP e um ALTO de 1 bit, que devolve a linha ao repouso e garante que
 *     o proximo START vai produzir uma borda de descida detectavel.
 *
 * Cada bit dura exatamente 1/BAUDRATE segundos. Quem garante isso e o
 * TIMER1 em modo CTC: ele dispara uma interrupcao a cada periodo de bit e a
 * rotina de interrupcao apenas coloca o proximo bit no pino. Por isso NAO
 * existe delay() nem delayMicroseconds() em lugar nenhum deste codigo -- o
 * tempo e contado pelo hardware, e o processador fica livre.
 *
 * Ligacao: pino 8 deste Arduino -> pino 2 do Arduino receptor
 *          GND deste Arduino    -> GND do Arduino receptor
 *
 * ATENCAO: diferente dos projetos 2, 3 e 4, aqui os pinos RESET *NAO* devem
 * estar ligados no GND -- agora quem trabalha e o processador do Arduino.
 *****************************************************/

// ---- Configuracao ---------------------------------------------------------
const uint8_t  PINO_TX   = 8;      // pino digital generico de saida
const uint32_t BAUDRATE  = 9600;   // bits por segundo na linha bit-bang
const uint16_t INTERVALO = 200;    // ms entre um caractere e o proximo

// Mensagem enviada em loop, um caractere por frame. Para ver sempre o mesmo
// frame no Analog Discovery, troque por algo como "A".
const char MENSAGEM[] = "Insper";

/* ERRO DE PARIDADE PROPOSITAL (hard coded).
 *
 * Com este flag em true, o transmissor inverte o bit de paridade de 1 a cada
 * ERRO_A_CADA caracteres. Os 8 bits de dados vao corretos, so a paridade sai
 * errada -- e e exatamente isso que o receptor tem que acusar. Serve para
 * demonstrar a identificacao de erro de paridade sem precisar mexer nos fios. */
const bool    ERRO_PARIDADE = false;
const uint8_t ERRO_A_CADA   = 4;

// ---- Base de tempo --------------------------------------------------------
// Timer1 em CTC com prescaler 8: a interrupcao acontece a cada
// (OCR1A + 1) * 8 / F_CPU segundos. Igualando isso a 1/BAUDRATE:
//
//     OCR1A = F_CPU / (8 * BAUDRATE) - 1
//
// Para 16 MHz e 9600 baud da 207, ou seja, 208 * 8 / 16e6 = 104,0 us por bit,
// contra os 104,17 us ideais: 0,16% de erro, muito abaixo dos ~5% que uma
// UART tolera ao longo de um frame de 11 bits.
const uint16_t TICKS_POR_BIT = F_CPU / 8UL / BAUDRATE;
const uint16_t OCR_BIT       = TICKS_POR_BIT - 1;

// ---- Estado do frame em transmissao ---------------------------------------
// 'quadro' guarda os 11 bits prontos, na ordem em que serao colocados na
// linha. A cada interrupcao sai o bit menos significativo e o resto desliza
// para a direita -- e por isso que montar o frame com << e |= (como pede o
// enunciado) resolve o problema inteiro, sem precisar de uma maquina de
// estados com um caso para start, outro para dados, outro para paridade...
volatile uint16_t quadro;
volatile uint8_t  bitsRestantes = 0;   // 0 = linha livre

// ---- Paridade -------------------------------------------------------------
// Devolve o bit de paridade PAR do byte: 1 se a quantidade de bits '1' em
// 'dado' for impar (para completar e deixar o total par), 0 se ja for par.
uint8_t calculaParidadePar(uint8_t dado) {
  uint8_t uns = 0;
  for (uint8_t i = 0; i < 8; i++) {
    uns += (dado >> i) & 0x01;
  }
  return uns % 2;
}

// ---- Montagem e disparo de um frame ---------------------------------------
void enviaByte(uint8_t dado, bool inverteParidade) {
  uint8_t paridade = calculaParidadePar(dado);
  if (inverteParidade) {
    paridade ^= 1;              // erro proposital: paridade trocada
  }

  // Monta os 11 bits de uma vez, na ordem temporal (bit 0 sai primeiro):
  uint16_t frame = 0;
  //   bit 0        -> START, sempre 0  (nao precisa escrever, ja e zero)
  frame |= (uint16_t)dado     << 1;    // bits 1..8  -> dados, LSB primeiro
  frame |= (uint16_t)paridade << 9;    // bit 9      -> paridade
  frame |= (uint16_t)1        << 10;   // bit 10     -> STOP, sempre 1

  // Escrita protegida: a interrupcao mexe nessas duas variaveis, e elas tem
  // mais de 8 bits, entao uma interrupcao no meio da escrita deixaria o
  // transmissor com meio frame antigo e meio novo.
  noInterrupts();
  quadro        = frame;
  bitsRestantes = 11;
  TCNT1         = 0;                   // comeca a contar o primeiro bit agora
  TIFR1   = (1 << OCF1A);              // descarta comparacao pendente
                                       // (registrador de flag: limpa-se ESCREVENDO 1,
                                       //  por isso e '=' e nao '|=' -- com |= as outras
                                       //  flags que estivessem em 1 seriam limpas junto)
  TIMSK1 |= (1 << OCIE1A);             // liga a interrupcao do Timer1
  interrupts();
}

// ---- Interrupcao: coloca um bit na linha a cada periodo de bit ------------
ISR(TIMER1_COMPA_vect) {
  digitalWrite(PINO_TX, quadro & 0x01);   // bit atual vai para o pino
  quadro >>= 1;                           // proximo bit assume a posicao 0
  bitsRestantes--;

  if (bitsRestantes == 0) {
    TIMSK1 &= ~(1 << OCIE1A);             // frame acabou: desliga a interrupcao
    // O ultimo bit colocado foi o STOP ('1'), entao a linha ja ficou em
    // repouso no nivel correto para o proximo START.
  }
}

// ---- Setup / loop ---------------------------------------------------------
void setup() {
  pinMode(PINO_TX, OUTPUT);
  digitalWrite(PINO_TX, HIGH);   // linha em repouso = nivel alto

  // Serial "de verdade" (pinos 0/1, via USB) usada SO para monitoramento,
  // como o enunciado permite.
  Serial.begin(115200);
  Serial.println(F("=== Projeto 5 - TRANSMISSOR UART por software ==="));
  Serial.print(F("Pino de transmissao : D"));  Serial.println(PINO_TX);
  Serial.print(F("Baudrate            : "));   Serial.println(BAUDRATE);
  Serial.print(F("Frame               : 1 start, 8 dados (LSB primeiro), 1 paridade par, 1 stop"));
  Serial.println();
  Serial.print(F("Erro de paridade    : "));
  Serial.println(ERRO_PARIDADE ? F("LIGADO (1 a cada 4 caracteres)") : F("desligado"));
  Serial.println();

  // Timer1: modo CTC (WGM12), topo em OCR1A, prescaler 8 (CS11).
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS11);
  OCR1A  = OCR_BIT;
  TIMSK1 = 0;                    // interrupcao so e ligada quando ha frame
}

void loop() {
  static uint8_t  indice = 0;         // qual caractere da MENSAGEM vai agora
  static uint8_t  contador = 0;       // para espacar os erros propositais
  static uint32_t ultimoEnvio = 0;

  // Espera nao bloqueante: compara millis() em vez de chamar delay(), para
  // nao travar o processador (requisito do enunciado).
  if (bitsRestantes != 0) {
    return;                            // ainda ha um frame na linha
  }
  if (millis() - ultimoEnvio < INTERVALO) {
    return;
  }
  ultimoEnvio = millis();

  uint8_t caractere = MENSAGEM[indice];
  contador++;
  bool erra = ERRO_PARIDADE && (contador % ERRO_A_CADA == 0);

  enviaByte(caractere, erra);

  // Monitoramento no PC (nao interfere no bit-bang: sai pelo chip UART).
  Serial.print(F("enviado '"));
  Serial.print((char)caractere);
  Serial.print(F("'  ASCII "));
  Serial.print(caractere);
  Serial.print(F("  0b"));
  for (int8_t i = 7; i >= 0; i--) {
    Serial.print((caractere >> i) & 1);
  }
  Serial.print(F("  paridade "));
  Serial.print(calculaParidadePar(caractere));
  if (erra) {
    Serial.print(F("  <<< ENVIADA INVERTIDA DE PROPOSITO"));
  }
  Serial.println();

  indice++;
  if (MENSAGEM[indice] == '\0') {
    indice = 0;
  }
}
