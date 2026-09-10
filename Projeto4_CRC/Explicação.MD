# Projeto 4 — CRC-16 e log da transmissão

Camada Física da Computação — Engenharia da Computação — Insper

Evolução do protocolo de datagramas do Projeto 3. Agora cada pacote carrega no
cabeçalho um **CRC-16 do payload**, o lado que recebe **confere esse CRC** e
responde `OK` ou `ERRO` (pedindo reenvio), e os **dois lados gravam um arquivo
de log** com uma linha para cada pacote enviado ou recebido.

---

## 1. Atenção: o sentido da transmissão inverteu

No Projeto 3 o **servidor enviava** os arquivos e o cliente baixava. No Projeto
4 é o contrário: **o cliente envia (upload) e o servidor recebe e confere**.

Isso não é escolha nossa, é o que o enunciado pede, em dois pontos:

> "Caso o lado que **recebe** o pacote (**server**) detecte uma incoerência
> entre o CRC enviado e o CRC calculado após o recebimento..."

> "Transmissão com erro na ordem dos pacotes **enviados pelo client**."

Então quem lê o arquivo do disco, fragmenta e transmite é o `cliente.py`; quem
valida o CRC, monta o arquivo de volta e salva é o `servidor.py`.

---

## 2. Arquivos

```
Projeto4_CRC/
├── cliente.py           <- NOVO: envia os arquivos, injeta os erros propositais
├── servidor.py          <- NOVO: recebe, confere o CRC-16 e responde OK / ERRO
├── protocolo.py         <- do Projeto 3, com CRC-16 e o log embutidos
├── enlace.py            <- do Projeto 1, sem alteração
├── enlaceRx.py          <- do Projeto 1, com uma correção (seção 8)
├── enlaceTx.py          <- do Projeto 1, com uma correção (seção 8)
├── interfaceFisica.py   <- do Projeto 3, sem alteração
├── arquivosCliente/     <- os arquivos que o cliente oferece para enviar
├── arquivosRecebidos/   <- onde o servidor grava o que recebeu
└── logs/                <- log_cliente_<cenario>.txt e log_servidor_<cenario>.txt
```

Cada computador leva os 6 arquivos `.py`. O cliente leva também a pasta
`arquivosCliente/`. Precisa apenas do `pyserial`:

```
python -m pip install pyserial
```

O CRC-16 **não é implementado à mão** (o enunciado pede para usar uma
biblioteca): usamos `binascii.crc_hqx`, da biblioteca padrão do Python. Não
precisa instalar mais nada.

A ligação dos Arduinos é exatamente a mesma do Projeto 2 e do Projeto 3 (jumper
RESET–GND em cada placa, pinos 0↔1 cruzados e GND comum).

---

## 3. O datagrama

O formato é o mesmo do Projeto 3; o que mudou foi o conteúdo do campo de
verificação, que agora é um CRC-16 em vez da soma simples.

```
+------------------------ HEAD (10 bytes) ------------------------+- payload -+- EOP -+
| tipo | fileId | seq | total | payloadLen |  crc  | rsv          |  0..100 B |  4 B  |
|  1B  |   1B   | 2B  |  2B   |     1B     |  2B   |  1B          |           |       |
+-----------------------------------------------------------------+-----------+-------+
```

Tamanho máximo: 10 + 100 + 4 = **114 bytes**.

O campo `crc` são os **2 bytes do CRC-16 do payload — só do payload**, como o
enunciado exige, e **todo** pacote leva o CRC do seu payload (inclusive os de
controle, cujo payload é o texto da mensagem).

### Por que CRC-16 e não a soma do Projeto 3

A soma de verificação do Projeto 3 não enxerga certos erros comuns: trocar dois
bytes de lugar, por exemplo, dá exatamente a mesma soma. O CRC-16 trata a
mensagem como um polinômio e pega, entre outras coisas, **qualquer** erro de 1
ou 2 bits e qualquer rajada de erro de até 16 bits — que é justo o tipo de
estrago que uma linha serial ruim produz.

Usamos o **CRC-16/XMODEM** (polinômio `0x1021`, valor inicial `0x0000`), que é
o que a função `binascii.crc_hqx(payload, 0)` calcula. Conferência de
referência: `crc_hqx(b"123456789", 0)` = `0x31C3`.

### Duas conferências independentes

| Mecanismo | O que detecta |
|---|---|
| **EOP** (4 bytes fixos) | se o pacote **terminou no lugar certo** — ou seja, enquadramento |
| **CRC-16** | se os bytes **do meio do payload** chegaram intactos — ou seja, conteúdo |

Um pacote só é aceito se as duas baterem. Elas cobrem falhas diferentes: um
pacote pode terminar no lugar certo e ainda assim ter um byte corrompido no
meio (é exatamente o erro proposital de CRC).

---

## 4. A conversa

Todos os tipos de mensagem, e quem manda cada uma:

| Tipo | Sentido | Significado |
|---|---|---|
| `HELLO` | cliente → servidor | "está vivo?" (o payload leva o nome do cenário, para nomear os logs) |
| `PRONTO` | servidor → cliente | "estou vivo, pode escolher" |
| `SELECIONAR` | cliente → servidor | nome do arquivo que será enviado |
| `CONFIRMAR` | servidor → cliente | "Arquivo 'x' escolhido, deseja adicionar outro? (S/N)" |
| `RESPOSTA` | cliente → servidor | "S" ou "N" |
| `INICIAR` | servidor → cliente | "entendido, pode iniciar a transmissão simultânea" |
| `DADOS` | cliente → servidor | um pedaço de um arquivo |
| `OK` | servidor → cliente | "**não houve incoerências**, pode mandar o próximo" |
| `ERRO` | servidor → cliente | "**incoerência de CRC / de ordem**, reenvie o pacote N" |
| `SUCESSO` | servidor → cliente | tudo chegou inteiro |
| `PAUSAR` / `RETOMAR` / `ABORTAR` | cliente → servidor | controle pelo teclado |

A transmissão é **um pacote de cada vez, alternando entre os arquivos**
(round-robin), e o cliente só manda o próximo depois de receber o `OK` — igual
ao Projeto 3, só que com os papéis trocados.

### O campo `seq` do pacote `ERRO` é a chave da recuperação

Quando o servidor recusa um pacote, ele coloca em `seq` **o número do pacote
que está esperando**. O cliente obedece (`arq["seq"] = resposta.seq`) e reenvia
a partir dali. É esse detalhe que faz o erro de ordem se consertar sozinho: se
o cliente pulou o pacote 3 e mandou o 4, o servidor responde `ERRO` com
`seq = 3`, e o cliente volta para o 3.

---

## 5. O arquivo de log

Cada lado grava `logs/log_<lado>_<cenario>.txt`. O nome do cenário vem no
`HELLO`, então **os dois logs de uma mesma transmissão têm o mesmo nome** e dá
para lê-los lado a lado.

O registro é feito **dentro de `enviarPacote()` e `receberPacote()`**, no
`protocolo.py` — não em cada ponto do código. Assim é impossível um pacote
passar sem aparecer no log.

Formato de cada linha (o do enunciado, com o nome do tipo junto do código para
ficar legível):

```
instante / envio-receb / tipo / bytes totais / pacote / total / CRC / observação
```

Os três campos `pacote / total / CRC` só aparecem em pacotes do tipo `DADOS`,
como o enunciado pede. Exemplo real, do cenário de erro de CRC:

**Cliente:**
```
10/09/2026 15:20:59.185 / envio / DADOS(0x07) / 114 / 3 / 12 / FAA2 / ERRO PROPOSITAL: payload corrompido (CRC nao vai bater)
10/09/2026 15:20:59.205 / receb / ERRO(0x09) / 17
10/09/2026 15:20:59.208 / envio / DADOS(0x07) / 114 / 3 / 12 / FAA2
10/09/2026 15:20:59.229 / receb / OK(0x08) / 14
```

**Servidor:**
```
10/09/2026 15:20:59.185 / receb / DADOS(0x07) / 114 / 3 / 12 / FAA2 / CRC INVALIDO (recebido FAA2, calculado A01F)
10/09/2026 15:20:59.187 / envio / ERRO(0x09) / 17
10/09/2026 15:20:59.207 / receb / DADOS(0x07) / 114 / 3 / 12 / FAA2
10/09/2026 15:20:59.209 / envio / OK(0x08) / 14
```

Cada linha é gravada com `flush()` na hora. Se o professor arrancar o fio (ou
o programa for interrompido), o log já está no disco.

---

## 6. Como rodar cada cenário

> **O servidor sempre começa primeiro.** Ele fica em laço: depois de atender um
> cliente, volta a esperar outro. Para encerrar, `Ctrl+C`.

Antes de tudo, ajuste `serialName` no topo de `cliente.py` e de `servidor.py`
(descubra com `python -m serial.tools.list_ports`).

### Cenário 1 — transmissão sem nenhuma intercorrência

Em `cliente.py`, deixe:

```python
ERRO_CRC   = False
ERRO_ORDEM = False
CENARIO    = ""
```

```
python servidor.py      # computador A
python cliente.py       # computador B
```

Gera `logs/log_cliente_sucesso.txt` e `logs/log_servidor_sucesso.txt`.

### Cenário 2 — erro de CRC

```python
ERRO_CRC = True
```

O cliente monta o pacote 3 normalmente (com o CRC correto no head) e **depois**
inverte um byte do payload. O servidor recalcula o CRC, vê que não bate,
responde `ERRO` pedindo o pacote 3, e o cliente reenvia — agora correto. A
transmissão **termina com sucesso**, como o enunciado exige.

Gera `logs/*_erro_crc.txt`.

### Cenário 3 — erro na ordem dos pacotes

```python
ERRO_ORDEM = True
```

O cliente **pula o pacote 3** e manda o 4. O servidor vê que esperava o 3,
responde `ERRO` com `seq = 3`, o cliente volta e manda o 3, depois o 4. Termina
com sucesso.

Gera `logs/*_erro_ordem.txt`.

### Cenário 4 — interrupção física (fios retirados e reconectados)

```python
ERRO_CRC   = False
ERRO_ORDEM = False
CENARIO    = "desconexao"
```

Não precisa de flag de erro: **retire um jumper** (ou os dois) no meio da
transmissão, espere alguns segundos e **reconecte**. Os dois lados ficam
avisando "conexão pode estar interrompida" e a transmissão continua sozinha de
onde parou, sem apertar nenhuma tecla.

No log fica visível: o cliente reenviando o mesmo pacote a cada 2 segundos e,
quando o fio volta, o servidor recebendo e respondendo. Exemplo real, do
`log_cliente_desconexao.txt`:

```
10/09/2026 15:22:32.150 / receb / OK(0x08) / 14
10/09/2026 15:22:32.151 / envio / DADOS(0x07) / 114 / 5 / 12 / D112
10/09/2026 15:22:34.165 / envio / DADOS(0x07) / 114 / 5 / 12 / D112   <- fio fora
10/09/2026 15:22:36.177 / envio / DADOS(0x07) / 114 / 5 / 12 / D112
10/09/2026 15:22:38.192 / envio / DADOS(0x07) / 114 / 5 / 12 / D112
10/09/2026 15:22:40.211 / envio / DADOS(0x07) / 114 / 5 / 12 / D112
...
10/09/2026 15:22:42.657 / receb / OK(0x08) / 14                       <- fio de volta
```

### Teclado, durante a transmissão

| Tecla | Efeito |
|---|---|
| `p` | pausa (o cliente para de enviar e avisa o servidor) |
| `r` | retoma |
| `a` | aborta os dois lados |

---

## 7. Como o protocolo se recupera de cada falha

| Falha | Quem detecta | Como se conserta |
|---|---|---|
| byte corrompido no payload | servidor, pelo **CRC-16** | responde `ERRO`/`CRC`, o cliente reenvia |
| pacote fora de ordem / pulado | servidor, comparando `seq` | responde `ERRO`/`ORDEM` com o `seq` que espera |
| pacote truncado no meio | quem recebe, pelo **EOP** | `resincronizar()` procura o próximo EOP e realinha |
| resposta perdida no fio | quem enviou, por **time out** | reenvia o mesmo pacote a cada 2s, indefinidamente |
| pacote repetido (o `OK` se perdeu) | servidor, `seq` já recebido | não duplica os dados, só repete o `OK` |
| mensagem do handshake perdida | cliente, por **time out** | `pedir()` reenvia; o servidor responde de novo (seção 8) |

---

## 8. O que foi corrigido em relação ao Projeto 3

Testando o Projeto 3 com desconexões em vários instantes diferentes, apareceram
quatro problemas reais. Todos estão corrigidos aqui.

**1. Bytes sumindo do buffer de recepção (`enlaceRx.py`).**
A thread de RX faz `self.buffer += rxTemp` enquanto a aplicação faz
`self.buffer = self.buffer[n:]`. As duas operações leem e reescrevem a variável
inteira, então uma podia sobrescrever a outra e perder bytes já recebidos. O
`threadPause()` não resolvia, porque ele só impede a *próxima* volta do laço e a
thread pode estar justamente dentro de `fisica.read()`. Agora há um
`threading.Lock` protegendo o buffer.

**2. Meio byte pendente travava a recuperação para sempre (`protocolo.py`).**
Este era o mais grave. A camada física manda tudo em hexadecimal (2 caracteres
por byte) e guarda em `rxRemain` o caractere ímpar que sobrar. Se a desconexão
corta um byte **pela metade**, esse meio caractere fica preso ali e, dali para
a frente, **todo** byte remontado sai deslocado em 4 bits — nenhum EOP volta a
aparecer e o protocolo nunca mais se realinha. Agora, quando a linha fica em
silêncio sem que o EOP apareça, `resincronizar()` descarta o que estiver
pendente (com a linha em silêncio, só pode ser lixo) e o alinhamento volta.

**3. Um `payloadLen` de lixo custava um time out inteiro (`protocolo.py`).**
Um head vindo de bytes deslocados pode declarar até 255 bytes de payload.
Como nenhum pacote legítimo passa de 100, agora isso é detectado na hora e o
fluxo é realinhado, em vez de esperar bytes que nunca vêm.

**4. Uma mensagem perdida no handshake matava a sessão inteira.**
No Projeto 3, se o fio caísse durante a negociação, um único `CONFIRMAR` ou
`INICIAR` perdido encerrava tudo, mesmo que o fio voltasse logo depois. Agora:

- o cliente usa `pedir()`, que **reenvia** o pedido a cada time out (30
  tentativas de 2s = 60 segundos de paciência);
- o laço de seleção do servidor é **idempotente**: receber o mesmo
  `SELECIONAR` duas vezes não escolhe o arquivo duas vezes, só repete o
  `CONFIRMAR`;
- toda mensagem do cliente tem exatamente uma resposta do servidor (o `"S"`
  agora também é respondido, com `PRONTO`), o que é o que permite reenviar
  qualquer coisa sem os dois lados saírem do passo.

Também foi tirado um *busy-wait* do `enlaceTx.py`, que girava em laço vazio
consumindo 100% de um núcleo e roubava CPU justamente da thread de RX.

As correções 1, 2 e 3 foram portadas de volta para o Projeto 3. A correção 4 é
uma mudança estrutural do handshake e ficou só aqui — o Projeto 3 continua
atendendo o que o enunciado dele pede (desconexão **durante a transmissão**),
mas não sobrevive a uma desconexão durante a negociação.

---

## 9. Problemas comuns

| Problema | O que fazer |
|---|---|
| `could not open port COM3` | Porta errada (`python -m serial.tools.list_ports`), cabo solto, ou o **Serial Monitor da IDE do Arduino está aberto** — feche-o. |
| `[ERRO] interfaceFisica, read, decode` | Lixo que algumas máquinas geram no começo da primeira transmissão. Os 2s de espera + `flush()` na abertura já cobrem quase sempre; se aparecer, rode o cliente de novo. |
| O cliente fica reenviando o mesmo pacote | Jumper solto, jumpers 0–1 não cruzados, ou falta o **GND comum**. Ele continua tentando por tempo indeterminado — é o comportamento esperado. |
| `pacote descartado: EOP inválido` | Normal logo depois de reconectar o fio: é a resincronização fazendo o trabalho dela. Deve parar em uma ou duas linhas. |
| Muitos erros de CRC sem flag ligada | Linha ruim de verdade: confira o GND e o jumper RESET–GND das duas placas. |
| O log não aparece | A pasta `logs/` é criada sozinha; confira se o programa chegou a abrir a porta serial. |
