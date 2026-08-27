# Projeto 2 — Desafios Client/Server

Camada Física da Computação — Engenharia da Computação — Insper

O cliente envia uma sequência de números em ponto flutuante IEEE-754 de 32 bits
pela serial UART. O servidor recebe, mostra os números na tela (um por linha) e
devolve a soma. O cliente confere a soma e avisa se estiver errada, ou mostra
uma mensagem de *time out* se nada voltar em 5 segundos.

---

## 1. Arquivos

São **7 arquivos no total**, e apenas dois foram criados neste projeto
(`cliente.py` e `servidor.py`). Os outros quatro são os arquivos do Projeto 1,
**sem nenhuma alteração**.

```
proj2/
├── cliente.py           <- criado neste projeto
├── servidor.py          <- criado neste projeto
├── enlace.py            <- do Projeto 1, sem alteração
├── enlaceRx.py          <- do Projeto 1, sem alteração
├── enlaceTx.py          <- do Projeto 1, sem alteração
├── interfaceFisica.py   <- do Projeto 1, sem alteração
├── Explicação.MD
└── enunciado_ponto_flutuante.pdf
```

Como o enunciado pede, **cada computador fica com 5 arquivos**:

| Computador | Arquivos |
|---|---|
| 1 (cliente) | `cliente.py` + `enlace.py` + `enlaceRx.py` + `enlaceTx.py` + `interfaceFisica.py` |
| 2 (servidor) | `servidor.py` + `enlace.py` + `enlaceRx.py` + `enlaceTx.py` + `interfaceFisica.py` |

Na prática o mais fácil é copiar a pasta inteira para as duas máquinas e rodar
`servidor.py` em uma e `cliente.py` na outra.

Precisa apenas do `pyserial`:

```
python -m pip install pyserial
```

---

## 2. Ligação dos Arduinos

Cada Arduino é usado só como um conversor USB para serial. Para isso o
ATmega328P (o microcontrolador) precisa ficar fora do caminho, senão ele disputa
a linha com o chip USB.

### Passo 1 — desligar o microcontrolador

Em **cada** placa, ligue um jumper de **RESET** ao **GND**. Isso segura o
ATmega328P em reset permanente e deixa os pinos dele em alta impedância, ou
seja, ele não interfere na linha.

Não é um curto perigoso: o RESET tem um pull-up de 10 kΩ para 5 V, então passa
só cerca de 0,5 mA. O chip USB é independente e continua funcionando normalmente.

> Com esse jumper posto **não dá para fazer upload de sketch**. Tire o jumper
> antes de gravar qualquer coisa na placa.

Alternativa: em vez do jumper, gravar um **sketch vazio**
(`void setup(){} void loop(){}`) nas duas placas. Funciona igual, mas depende do
que está gravado; o jumper de reset é mais garantido.

### Passo 2 — ligar as duas placas

São 3 jumpers entre as placas, **cruzando TX com RX** (que são os pinos 1 e 0):

```
   COMPUTADOR 1                              COMPUTADOR 2
        |                                          |
       USB                                        USB
        |                                          |
   +----------+                              +----------+
   | ARDUINO A|                              | ARDUINO B|
   |   RESET  |--+                           |  RESET   |--+
   |   GND    |--+                           |  GND     |--+
   |          |                              |          |
   |   D1 (TX)|------------------------------|D0 (RX)   |
   |   D0 (RX)|------------------------------|D1 (TX)   |
   |   GND    |------------------------------|GND       |
   +----------+                              +----------+
```

| Arduino A | Arduino B |
|-----------|-----------|
| pino **1** (TX) | pino **0** (RX) |
| pino **0** (RX) | pino **1** (TX) |
| **GND** | **GND** |

São **5 jumpers no total**: 1 de RESET–GND em cada placa, mais os 3 que ligam
uma placa na outra.

Cada placa é alimentada pelo próprio cabo USB. **Não ligue 5 V nem 3,3 V entre
as duas placas** — só o GND.

O **GND comum é obrigatório**; sem ele os dois lados não têm referência de
tensão e só chega lixo.

### Por que cruzado

Cruzar TX com RX é o esperado, mas o motivo é diferente do que os rótulos
sugerem. Os nomes TX e RX impressos na placa são do ponto de vista do
ATmega328P, que aqui está desligado. Quem está falando é o chip USB, e para ele
os papéis são invertidos:

- o pino **0** é a **saída** do chip USB (por onde os dados do PC saem);
- o pino **1** é a **entrada** do chip USB (por onde os dados entram no PC).

Ou seja, o que sai do PC 1 (pino 0 do A) tem que chegar na entrada do PC 2
(pino 1 do B). As duas inversões se cancelam e dá no mesmo que cruzar TX com RX.
É também o mesmo jumper 0–1 do loopback do Projeto 1, só que agora entre duas
placas em vez de uma.

> **Não ligue o pino 0 de uma placa no pino 0 da outra.** Isso juntaria as duas
> saídas dos chips USB, uma brigando contra a outra. Se a comunicação não
> funcionar, o problema costuma ser o GND ou o jumper de reset, e não a
> orientação dos fios de dados.

### Descobrir a porta

```
python -m serial.tools.list_ports
```

No Windows o Gerenciador de Dispositivos também mostra, em *Portas (COM e LPT)*.
Coloque a porta encontrada na variável `serialName`, no topo de
`cliente.py` e de `servidor.py`.

---

## 3. Como rodar

> **O servidor sempre começa primeiro.** Ele fica parado esperando os dados do
> cliente. Se você inverter a ordem, o cliente fala sozinho e cai em *time out*.

O servidor fica em laço: depois de responder, volta a esperar. Você pode rodar o
cliente várias vezes sem reiniciar o servidor. Para encerrar, `Ctrl+C`.

### Caso 1 — Sucesso

No **computador do servidor**, com `FORCAR_ERRO = False` e `NAO_RESPONDER = False`:

```
python servidor.py
```

No **computador do cliente**:

```
python cliente.py
```

### Caso 2 — Erro de interpretação no servidor

Em `servidor.py`, mude a linha:

```python
FORCAR_ERRO = True
```

Rode o servidor e depois o cliente, igual ao caso 1. O servidor passa a ler os
4 bytes do primeiro número na ordem trocada: os bits chegaram certos, mas ele
os interpreta errado. O `45.450000` vira `-428255296.000000`, a soma sai errada
e o cliente acusa a inconsistência.

### Caso 3 — Time out

Volte `FORCAR_ERRO = False` e mude:

```python
NAO_RESPONDER = True
```

O servidor recebe e mostra tudo normalmente, mas não devolve a soma. O cliente
espera 5 segundos e mostra a mensagem de *time out*.

---

## 4. Como testar depois de rodar

### Caso 1 — sucesso

No **servidor**, confira que apareceu:

- `O cliente vai enviar 10 números` — ou seja, o servidor **descobriu** a
  quantidade lendo o primeiro byte, não sabia de antemão;
- os **10 números, um por linha**, com 6 casas decimais;
- `Soma: 734.507446`;
- `Enviou 4 bytes com a soma`.

No **cliente**, confira que apareceu:

- `Enviando 41 bytes...` e `Enviou 41 bytes` (1 byte da quantidade + 10 × 4);
- `Soma esperada: 734.507446`;
- `Soma recebida do servidor: 734.507446` — **igual à esperada**;
- `SUCESSO: a soma devolvida pelo servidor está correta`.

Os números impressos pelo servidor têm uma diferença mínima em relação aos do
cliente (`45.450000` aparece como `45.450001`). Isso é esperado e está
explicado na seção 6.

### Caso 2 — erro

- o servidor mostra `-428255296.000000` no lugar do primeiro número;
- a soma do servidor fica completamente diferente;
- o cliente termina com `ERRO: a soma devolvida pelo servidor está incorreta!`.

### Caso 3 — time out

- o servidor mostra os números e `O servidor não vai responder`;
- o cliente, cerca de 5 segundos depois, mostra
  `TIME OUT: o servidor não respondeu em 5 segundos`.

### Testar sem os dois computadores

Dá para ensaiar tudo com **os dois Arduinos ligados no mesmo computador**
(mesma fiação da seção 2). Cada Arduino vira uma porta COM diferente. Coloque
uma porta no `serialName` do servidor e a outra no do cliente, e rode os dois em
**dois terminais separados**.

---

## 5. Como funciona

### O pacote

Cliente → servidor:

```
+--------------+-----------+-----------+-----+-----------+
| quantidade N | número 1  | número 2  | ... | número N  |
|    1 byte    |  4 bytes  |  4 bytes  |     |  4 bytes  |
+--------------+-----------+-----------+-----+-----------+
```

Servidor → cliente:

```
+-----------+
|   soma    |  4 bytes
+-----------+
```

O primeiro byte é o que permite ao servidor descobrir quantos números vêm, já
que o enunciado diz que ele não sabe a quantidade de antemão. Fora esse byte,
tudo é dado útil: são 41 bytes para 10 números, enviados em uma **única**
chamada `sendData()`, sem nenhuma pausa no meio.

### Ponto flutuante de 32 bits

Cada número vai em IEEE-754 de 32 bits, usando o módulo `struct` da biblioteca
padrão do Python:

```python
struct.pack(">f", numero)      # número  -> 4 bytes
struct.unpack(">f", bytes)[0]  # 4 bytes -> número
```

O `>` indica *big-endian* (byte mais significativo primeiro, que é a ordem de
rede) e o `f` indica *float* de 32 bits. É justamente essa ordem de bytes que o
servidor inverte de propósito quando `FORCAR_ERRO = True`.

### O time out

`enlaceRx.getNData()` fica preso em um `while` até os bytes chegarem, ou seja,
não tem time out. Como o enunciado pede para não mexer nas camadas, o time out
foi feito na aplicação, com uma função que usa apenas métodos que já existem na
camada de enlace:

```python
def recebe(com, quantidade, timeout):
    inicio = time.time()
    while com.rx.getBufferLen() < quantidade:
        if time.time() - inicio > timeout:
            return None
        time.sleep(0.05)
    return com.rx.getBuffer(quantidade)
```

No servidor a mesma função é chamada com `timeout = None`, ou seja, espera para
sempre — é assim que ele "permanece em estado de espera".

---

## 6. Sobre a precisão

O enunciado pede 6 casas de precisão e, para nota A+, ponto flutuante de 32
bits. Os dois pedidos brigam um pouco entre si: o `float` de 32 bits tem 24 bits
de mantissa, o que dá cerca de **7 dígitos significativos no total** — e não 6
casas depois da vírgula em qualquer magnitude.

Por isso:

- `45.450000` é armazenado como `45.450001`;
- `999.999900` é armazenado como `999.999878`.

Para o cliente não acusar erro por causa desse arredondamento, ele calcula a
soma esperada **do mesmo jeito que o servidor calcula**: converte cada número
para 32 bits antes de somar e converte a soma para 32 bits no final. Como as
duas contas são idênticas, numa transmissão correta os 4 bytes da resposta são
exatamente iguais aos 4 bytes esperados, e a comparação pode ser feita byte a
byte, sem precisar inventar nenhuma margem de tolerância.

---

## 7. Problemas comuns

| Problema | O que fazer |
|---|---|
| `could not open port COM3` | Porta errada (rode `python -m serial.tools.list_ports`), cabo solto, ou o **Serial Monitor da IDE do Arduino está aberto** — feche-o. |
| `[ERRO] interfaceFisica, read, decode` | É o lixo que algumas máquinas geram no começo da primeira transmissão. O servidor descarta sozinho e volta a esperar: basta **rodar o cliente de novo**, porque a partir da segunda transmissão a linha fica limpa. |
| O cliente cai em time out no caso 1 | O servidor não foi iniciado antes; ou ficou `NAO_RESPONDER = True`; ou os jumpers 0–1 estão invertidos / falta o GND. |
| `Byte inesperado na linha` no servidor | Dessincronizou. Ele descarta sozinho; se insistir, feche os dois programas e comece de novo pelo servidor. |
| Chega só lixo | Falta o **GND comum** entre os Arduinos, ou o jumper RESET–GND soltou em alguma das placas. |
| A soma acusa erro no caso 1 | Confira se ficou `FORCAR_ERRO = True` no servidor. |
