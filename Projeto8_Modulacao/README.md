# Projeto 8 — parte 1: modulação AM (3 estações de rádio)

Camada Física da Computação — Insper. Entrega: 12/11/2026.

Três áudios são modulados em AM, cada um na sua faixa (9–12, 12–15 e 15–18 kHz),
somados (o "ar") e depois separados por filtros e demodulados. Emissor e receptor
estão no mesmo programa.

## Como rodar

Neste notebook o Python com tudo instalado é o **3.11** (`numpy`, `scipy`,
`matplotlib`, `sounddevice`). Em outro computador: `pip install numpy scipy matplotlib sounddevice`.

```
cd Projeto8_Modulacao
py -3.11 gerar_audios_teste.py      # cria audios/originais/estacao_{1,2,3}.wav (se não existirem)
py -3.11 radio_am.py                # O PROJETO: janela com gravar, tocar e os 8 gráficos
py -3.11 exercicios.py              # exercícios 1 a 7 (contas no terminal + gráficos)
py -3.11 testes.py                  # 14 testes automáticos
```

- `radio_am.py --sem-janela`: só o relatório no terminal; salva os wavs e os PNGs em `graficos/`.
- `exercicios.py 5 --sem-audio`: só um exercício, sem tocar som.
- O enunciado pede áudios **gravados**: na janela, **● Gravar 4 s** de cada estação
  troca o áudio de teste pela sua voz (ou use **Abrir .wav…**).

## Arquivos

| arquivo | o que faz |
|---|---|
| `am.py` | biblioteca: estações, filtros, modular, sintonizar, demodular, medições |
| `radio_am.py` | o projeto: relatório, wavs de cada etapa e a janela |
| `graficos.py` | os 8 gráficos (mesmas funções para a janela e para os PNGs) |
| `exercicios.py` | exercícios 1 a 7 |
| `testes.py` | testes automáticos da matemática |
| `gerar_audios_teste.py` | 2 vozes sintetizadas (Windows, pt-BR) + 1 melodia |
| `audios/` | `originais/`, `modulados/`, `soma.wav`, `extraidos/`, `demodulados/` |

## O que apresentar (roteiro na janela)

1. **▶ Os 3 originais**.
2. Gráfico **3 Modulados**: FFT dos 3 modulados, cada um dentro da faixa.
   O **4 Faixas (dB)** prova que nenhum invadiu a vizinha (tudo abaixo de −60 dB).
3. Gráfico **5 Soma**: FFT da soma (o sinal no meio físico).
4. Gráfico **7 Extraídos**: FFT dos 3 sinais tirados da soma pelos passa-faixas.
5. **▶ Os 3 demodulados** + gráfico **8 Demodulação**.

## Respostas curtas

| ex. | resposta |
|---|---|
| 1 | a soma tem picos em 2 kHz (fora de 12–18 kHz) e 15 kHz → não pode ser transmitida |
| 2 | 13 a 17 kHz (fc ± fm), largura 2·fm = 4 kHz |
| 3 | o produto tem só 13 e 17 kHz, amplitude 0,5 cada |
| 4 | passa-baixa de 1 kHz em m(t) antes de modular (na prática um pouco abaixo, 800 Hz) |
| 5 | portadora 16 kHz, mensagem cortada em 1,6 kHz, modulado em 14,4–17,6 kHz, correlação 1,000 |
| 6 | 64 símbolos = 6 bits; 2,4 GHz / 2 = 1,2·10⁹ símbolos/s → **7,2 Gbit/s** |
| 7 | 256 símbolos = 8 bits; 2,4 GHz / 10 = 2,4·10⁸ símbolos/s → 1,92 Gbit/s; 480 MB = 3,84·10⁹ bits → **2,0 s** (2,1 s se MB = 2²⁰ bytes) |

---

# Projeto 8 — parte 2: chat por áudio com PSK

Entrega: 19/11/2026. Um computador digita uma frase; ao apertar Enter ela sai pelo
alto-falante em BPSK (bit 0 = fase 0°, bit 1 = fase 180°) a **100 bit/s** com portadora
de **4 kHz**. O outro computador escuta pelo microfone, demodula e escreve a frase.

## Como rodar

Os dois computadores precisam da mesma taxa e da mesma portadora.

```
py -3.11 chat_psk.py emissor        # computador A: digite e Enter
py -3.11 chat_psk.py receptor       # computador B: as frases aparecem sozinhas
py -3.11 chat_psk.py chat           # os dois lados no mesmo computador (conversa nos dois sentidos)
py -3.11 chat_psk.py simular        # sem som: canal simulado (eco, ruído, relógios diferentes)
py -3.11 experimentos_psk.py        # mudar a taxa e a portadora: tabelas + FFTs
py -3.11 testes_psk.py              # 17 testes automáticos
```

Opções: `--taxa 100 --portadora 4000 --volume 0.6 --bits`. No prompt:

| comando | o que faz |
|---|---|
| `/grafico` | FFT do sinal emitido e do recebido, com a banda; bits; a inversão de 180°; constelação |
| `/taxa 200`, `/portadora 3000` | muda ao vivo (mude igual no outro computador) |
| `/bits` | mostra os bits de cada mensagem (sincronia, tamanho, dados, CRC) |
| `/nivel` | quanto som o microfone está captando na banda da portadora |
| `/info`, `/sair` | parâmetros atuais; sair |

**Dicas para funcionar pelo ar:** use o alto-falante e o microfone do notebook (fone Bluetooth
no modo "headset" amostra a 8–16 kHz e estraga o sinal); volume do sistema alto; se não
receber nada, rode `/nivel` no receptor durante o envio; se o Windows tiver "supressão de
ruído"/"melhorias de áudio" no microfone, desligue (ela pode tratar o tom como ruído).

**Corrigido em 16/11 (teste pelo ar):** o Windows cortava os últimos ~210 ms do som tocado, e o fim
do CRC se perdia (texto certo, "CRC NÃO CONFERE"). O chat agora toca 0,5 s de silêncio depois do
quadro (`SOBRA_NO_FIM` em `chat_psk.py`). Testado num notebook só, com `receptor` e `emissor` em dois
terminais: duas frases com acento chegaram com CRC ok e SNR de 16 dB.

## Arquivos da parte 2

| arquivo | o que faz |
|---|---|
| `psk.py` | biblioteca: quadro de bits + CRC, modulação BPSK, `Receptor`, banda, canal simulado |
| `chat_psk.py` | o chat (emissor, receptor, chat, simular) e os comandos |
| `graficos_psk.py` | o painel do `/grafico` e as figuras de taxa/portadora |
| `experimentos_psk.py` | "altere a taxa / altere a portadora e observe a FFT" |
| `testes_psk.py` | testes automáticos |
| `audios_psk/`, `graficos_psk/` | último áudio enviado/recebido e os gráficos salvos |

## Números para a apresentação

- 100 bit/s a 44,1 kHz: **441 amostras** e **40 ciclos** da portadora por bit (10 ms).
- Quadro: 13 bits de sincronia (Barker) + 16 de tamanho + 8 por byte + 16 de CRC.
  "Olá, mundo!" = 12 bytes → 141 bits → 1,41 s (+0,35 s de abertura e fim).
- **Banda necessária ≈ 2 × taxa = 200 Hz** (lóbulo principal, 3900–4100 Hz). Com bits
  aleatórios, 90% da energia fica em 1,6 × taxa; 99% em ~20 × taxa (lóbulos laterais).
- Dobrar a taxa dobra a banda; mudar a portadora só muda o espectro de lugar.
