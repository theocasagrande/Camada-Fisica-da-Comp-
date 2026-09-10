# Projeto 5 — Serialização UART em pino digital genérico

Camada Física da Computação — Engenharia da Computação — Insper

Dois Arduinos trocam um caractere por vez **sem usar o chip UART**. O frame
UART é produzido bit a bit em um pino digital comum (pino 8) e lido bit a bit
em outro pino digital comum (pino 2). A serial "de verdade" (pinos 0 e 1, via
USB) é usada **apenas para monitorar** o que está sendo enviado e recebido,
como o enunciado permite.

---

## 1. Este projeto não usa nada dos projetos 1 a 4

Os projetos 1 a 4 eram Python rodando no PC, com o Arduino servindo só de
conversor USB-serial — o chip UART fazia todo o trabalho de serialização.
Aqui é o oposto: o código é C++ rodando **dentro** do Arduino, e o trabalho
que o chip UART fazia escondido passa a ser feito na mão.

É a mesma camada física dos outros projetos, vista um nível abaixo: nos
projetos anteriores o byte era a unidade indivisível, aqui ele é desmontado
em bits e remontado do outro lado.

---

## 2. Arquivos

```
Projeto5_Serializacao/
├── transmissor/transmissor.ino   <- gera o frame UART no pino 8
├── receptor/receptor.ino         <- lê o frame UART no pino 2
├── Explicação.MD
└── Enunciado projeto 05.pdf
```

Cada `.ino` precisa ficar dentro de uma pasta com o mesmo nome — é exigência da
IDE do Arduino, e é por isso que são duas subpastas. Abra
`transmissor/transmissor.ino`, grave em uma placa; abra
`receptor/receptor.ino`, grave na outra.

Não precisa instalar nenhuma biblioteca.

---

## 3. Ligação das placas

> **Tire os jumpers RESET–GND.** Nos projetos 2, 3 e 4 o RESET ficava aterrado
> para desligar o ATmega e usar só o chip USB. Aqui é o contrário: quem faz
> todo o trabalho é o processador do Arduino. Com o RESET aterrado nada
> funciona — e também não é possível gravar o sketch.

São **2 jumpers** entre as placas:

```
   COMPUTADOR 1                              COMPUTADOR 2
        |                                          |
       USB                                        USB
        |                                          |
   +--------------+                        +--------------+
   | TRANSMISSOR  |                        |   RECEPTOR   |
   |              |                        |              |
   |   D8  -------|------------------------|-----> D2     |
   |   GND -------|------------------------|-----  GND    |
   +--------------+                        +--------------+
                             |
                             +---- DIO0 do Analog Discovery
                                   (GND do AD no GND comum)
```

| Transmissor | Receptor |
|---|---|
| pino **8** (saída) | pino **2** (entrada) |
| **GND** | **GND** |

O **GND comum é obrigatório**: sem ele os dois lados não têm referência de
tensão e o receptor lê lixo.

Por que esses pinos:

- **pino 8 no transmissor** — é um pino digital qualquer, que é justamente o
  que o enunciado exige. Os pinos 0 e 1 estão proibidos porque são os que ligam
  o ATmega ao chip USB (e ao monitor serial).
- **pino 2 no receptor** — precisa ser 2 ou 3, porque no Uno só esses dois têm
  **interrupção externa** (INT0 e INT1), e é a interrupção que detecta a borda
  do start bit no instante exato. Continua sendo um pino digital genérico, não
  o RX da UART.

Os dois Arduinos podem estar no mesmo computador (duas portas COM) ou em
computadores diferentes; tanto faz, porque a comunicação entre eles não passa
pelo USB.

---

## 4. O frame UART

11 bits por caractere, no padrão **8E1** (8 bits de dados, paridade par, 1 stop):

```
 repouso   START    D0 D1 D2 D3 D4 D5 D6 D7    P     STOP    repouso
   '1'      '0'     <--- dados, LSB primeiro --->  par  '1'      '1'
  ‾‾‾‾‾|________|-----------------------------|-----|‾‾‾‾‾‾|‾‾‾‾‾
       ^
   borda de descida: é o "tiro de largada" do receptor
```

| Campo | Valor | Para que serve |
|---|---|---|
| repouso | `1` | linha parada fica em nível alto |
| **start** | `0` | produz a **borda de descida** que sincroniza o receptor |
| **dados** | 8 bits | o caractere em ASCII, **do bit menos significativo para o mais significativo** (ordem do padrão UART) |
| **paridade** | par | vale 1 ou 0 de forma que o total de bits `1` (dados + paridade) seja **par** |
| **stop** | `1` | devolve a linha ao repouso, garantindo que o próximo start produza uma borda detectável |

Cada bit dura exatamente `1/9600 s ≈ 104 µs`.

### Por que o start é 0 e o stop é 1

Não é arbitrário. Como o repouso é `1`, um start em `0` é a única forma de
criar uma borda de descida no começo de todo caractere. E o stop em `1`
garante que a linha volte ao repouso — sem ele, um caractere terminado em bit
`0` deixaria a linha baixa e o próximo start não geraria borda nenhuma.

---

## 5. Como o transmissor gera o frame

O truque que deixa o código curto está em montar os 11 bits de uma vez, em um
`uint16_t`, na ordem em que vão sair:

```cpp
uint16_t frame = 0;
//   bit 0                             -> START, já é zero
frame |= (uint16_t)dado     << 1;   // bits 1..8  -> dados, LSB primeiro
frame |= (uint16_t)paridade << 9;   // bit 9      -> paridade
frame |= (uint16_t)1        << 10;  // bit 10     -> STOP
```

Depois disso, cada interrupção do timer faz só duas coisas:

```cpp
digitalWrite(PINO_TX, quadro & 0x01);   // bit atual vai para o pino
quadro >>= 1;                           // o próximo assume a posição 0
```

Ou seja: os operadores `<<` e `|=` que o enunciado manda estudar resolvem o
problema inteiro. Não é preciso uma máquina de estados com um caso para o
start, outro para os dados, outro para a paridade.

---

## 6. Como o receptor se sincroniza

Este é o ponto central do projeto, e o que o enunciado destaca: **não se pode
ler o pino nos instantes de transição do nível lógico**.

1. A linha está em repouso (alto). A interrupção externa **INT0** está armada
   na borda de descida.
2. Chega o start bit → borda de descida → a INT0 dispara e marca o instante
   exato do início do frame. A INT0 é então **desligada**, para que as bordas
   dos bits de dados não sejam confundidas com um novo caractere.
3. O Timer1 é programado para disparar depois de **meio período de bit**. Isso
   joga a primeira leitura para o **meio do start bit**.
4. Dali em diante o Timer1 dispara de **um período em um período**, e cada
   leitura cai no meio de um bit — o ponto mais distante possível das duas
   bordas vizinhas.

```
linha  ‾‾‾‾|____ START ____|--- D0 ---|--- D1 ---| ...
            ^              ^          ^
            |              |          |
       borda: dispara   meio do    meio do        <- momentos de leitura,
          a INT0         start        D0             marcados pelo Timer1
            |<- 1/2 bit ->|<- 1 bit ->|
```

Com bit de 104 µs, cada leitura acontece a **52 µs de distância** de qualquer
borda. É folga de sobra: a latência de entrada na interrupção mais o
`digitalRead` somam menos de 10 µs.

A leitura do meio do start bit ainda serve de **conferência**: se naquele
instante a linha já voltou para alto, aquela borda era ruído, e o frame é
descartado sem estragar a sincronização dos próximos.

O byte é remontado exatamente como o enunciado sugere:

```cpp
dado |= (uint8_t)(nivel & 0x01) << amostra;   // LSB primeiro
```

---

## 7. Por que não há `delay` nem `delayMicroseconds`

O enunciado dá nota melhor para quem não usa função de espera bloqueante, e a
razão é técnica, não estética: `delay()` e `delayMicroseconds()` prendem o
processador em um laço vazio, e qualquer coisa que aconteça durante a espera
(uma interrupção da serial, por exemplo) desloca todos os bits seguintes.

Aqui **quem conta o tempo é o hardware**. O Timer1 roda em modo **CTC**
(*Clear Timer on Compare*): ele conta sozinho até `OCR1A`, dispara a
interrupção e zera. O processador só é incomodado uma vez por bit, no instante
certo, e fica livre no resto do tempo.

O período do bit sai da conta:

```
OCR1A = F_CPU / (prescaler × BAUDRATE) − 1 = 16.000.000 / (8 × 9600) − 1 = 207
```

Um período = 208 ticks × 0,5 µs = **104,00 µs**, contra os 104,17 µs ideais:
**0,16% de erro**, muito abaixo dos ~5% que uma UART tolera ao longo de um
frame de 11 bits.

O único lugar onde há espera é o intervalo entre um caractere e o próximo, no
`loop()` do transmissor — e ela é feita comparando `millis()`, sem bloquear:

```cpp
if (millis() - ultimoEnvio < INTERVALO) return;
```

### Baudrates que funcionam com essa conta

| Baudrate | ticks/bit | bit real | erro | cabe na interrupção? |
|---|---|---|---|---|
| **9600** | 208 | 104,00 µs | −0,16% | sim (padrão) |
| 19200 | 104 | 52,00 µs | −0,16% | sim |
| 38400 | 52 | 26,00 µs | −0,16% | sim |
| 57600 | 34 | 17,00 µs | −2,08% | apertado |
| 115200 | 17 | 8,50 µs | −2,08% | não |

Para mudar, troque `BAUDRATE` **nos dois sketches** — os `OCR1A` são
recalculados sozinhos. Acima de 38400 o erro de arredondamento cresce e a
interrupção passa a não ter tempo de terminar dentro de um bit.

---

## 8. Demonstrando a identificação de erro de paridade

O receptor recalcula a paridade dos 8 bits que chegaram e compara com o bit de
paridade que veio na linha. Se não baterem, ele imprime `<<< ERRO DE PARIDADE`.

Para mostrar isso funcionando sem precisar mexer nos fios, o transmissor tem um
erro proposital *hard coded*, no mesmo espírito do Projeto 4. Em
`transmissor.ino`:

```cpp
const bool    ERRO_PARIDADE = true;   // era false
const uint8_t ERRO_A_CADA   = 4;
```

Com isso, 1 a cada 4 caracteres sai com **os 8 bits de dados corretos e o bit
de paridade invertido**. No monitor do transmissor aparece
`<<< ENVIADA INVERTIDA DE PROPOSITO`, e no monitor do receptor, no mesmo
caractere, aparece `<<< ERRO DE PARIDADE`.

O receptor também acusa **erro de frame** (`stop bit invalido`) quando o último
bit não vem em nível alto — é o que acontece se o fio for desconectado ou se os
dois lados estiverem em baudrates diferentes.

---

## 9. Observando com o Analog Discovery

1. Ligue **DIO 0** do Analog Discovery no mesmo fio que sai do pino 8, e o
   **GND** do AD no GND comum das placas.
2. No WaveForms, abra o **Logic Analyzer**.
3. Clique em **+** → **UART** e configure:

   | Campo | Valor |
   |---|---|
   | DIO | 0 |
   | Baud rate | **9600** |
   | Bits | **8** |
   | Parity | **Even** (par) |
   | Stop | **1** |

4. Em **Trigger**, escolha borda de **descida** no DIO 0 — é o start bit.
5. Ajuste a base de tempo para algo em torno de **200 µs/div**, para que o
   frame inteiro (11 × 104 µs ≈ 1,15 ms) caiba na tela.

O analisador deve decodificar e mostrar o mesmo caractere que aparece nos dois
monitores seriais. Dá para conferir a olho, no traço, que cada bit tem os
mesmos ~104 µs e identificar o start, os 8 dados, a paridade e o stop.

Com `ERRO_PARIDADE = true`, o WaveForms marca os frames com paridade errada —
é a confirmação independente de que o receptor está certo ao acusar o erro.

---

## 10. O que cada nota pede, e onde está no código

| Nota | Exigência | Como foi atendido |
|---|---|---|
| **C+** | baudrate de 9600 bits/s ou mais | `BAUDRATE = 9600` nos dois sketches, com 0,16% de erro no período do bit |
| **B+** | identificação de erro de paridade | receptor recalcula e compara; flag `ERRO_PARIDADE` no transmissor gera o erro para demonstrar |
| **A** | não usar `delay` nem `sleep` | Timer1 em CTC conta os bits por hardware; o intervalo entre caracteres usa `millis()` |
| **A+** | monitorar com Analog Discovery | seção 9 |

---

## 11. Como isso foi verificado

Não dá para testar o comportamento elétrico sem as placas, mas duas coisas
foram verificadas de verdade antes da entrega:

**Os dois sketches compilam** para `arduino:avr:uno`, sem nenhum warning mesmo
com `--warnings all` (transmissor: 2934 bytes de flash, 9%; receptor: 3316
bytes, 10%).

**A lógica dos dois lados foi simulada no nível do sinal**, reproduzindo a
mesma aritmética dos sketches (mesmos `OCR1A`, mesma ordem de bits, mesma
paridade) e verificando o que o receptor lê de uma onda gerada pelo
transmissor:

| Teste | Resultado |
|---|---|
| os 256 valores possíveis de byte voltam intactos | 256/256 |
| erro de paridade proposital é detectado (e o dado continua correto) | 256/256 |
| stop bit inválido vira erro de frame | 256/256 |
| distância das leituras até a borda mais próxima | 52,0 µs, em bit de 104 µs |
| tolerância a diferença de clock entre as placas | funciona até ±4% (cristais reais ficam em ±0,005%) |
| tolerância a atraso constante da interrupção | funciona até 50 µs (o real é < 10 µs) |

---

## 12. Problemas comuns

| Problema | O que fazer |
|---|---|
| Nada aparece no monitor do receptor | Confira o **GND comum** e se os jumpers RESET–GND foram **retirados** das duas placas. |
| `avrdude: not in sync` ao gravar | O jumper RESET–GND ainda está posto — tire antes de gravar. |
| Só chega lixo, todo caractere com erro | Baudrate diferente entre os dois sketches, ou fio no pino errado (a saída é a D8, a entrada é a D2). |
| Todos os caracteres com erro de paridade | O `ERRO_PARIDADE` ficou `true` no transmissor. |
| Erro de frame de vez em quando | Fio com mau contato. O receptor descarta o frame e se ressincroniza sozinho no próximo start bit. |
| O contador de "ruidos" sobe sozinho | Bordas espúrias na linha (fio comprido ou solto). São falsos starts, já rejeitados pela leitura do meio do start bit. |
| O monitor serial mostra caracteres estranhos | O monitor tem que estar em **115200** (é a serial do USB, não a do bit-bang). |
