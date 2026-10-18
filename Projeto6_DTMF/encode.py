
# Projeto 6 - DTMF - lado EMISSOR
#
# Pergunta uma tecla ao usuário, gera a soma das duas senoides DTMF dessa
# tecla, toca o som pela placa de som e plota o sinal no tempo e na frequência.
#
#   python encode.py                 -> pergunta a tecla (repete até digitar q)
#   python encode.py 7               -> emite direto a tecla 7
#   python encode.py 7 --salvar      -> também grava tons/tecla_7.wav
#   python encode.py --duracao 8     -> muda a duração do tom (padrão 5 s)

import argparse
import os
import signal as sinais
import sys

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
from scipy.io import wavfile

from suaBibSignal import TABELA_DTMF, signalMeu

FS = 44100          # taxa de amostragem (amostras por segundo)
DURACAO = 5         # segundos de som
AMPLITUDE = 1       # amplitude de cada senoide
JANELA_PLOT = 0.02  # segundos mostrados no gráfico do tempo (20 ms)
FMAX_PLOT = 2000    # Hz mostrados no gráfico de Fourier


# funções caso queiram usar para sair...
def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)


# converte intensidade em dB, caso queiram ...
def todB(s):
    sdB = 10 * np.log10(s)
    return sdB


def pedir_tecla():
    """Pergunta a tecla até o usuário digitar uma válida (ou q para sair)."""
    while True:
        tecla = input("Digite a tecla (0-9, A-D, *, #) ou q para sair: ").strip().upper()
        if tecla == "Q":
            return None
        if tecla == "X":            # o enunciado chama o * de X
            tecla = "*"
        if tecla in TABELA_DTMF:
            return tecla
        print("Tecla inválida.")


def gerar_tom(tecla, duracao=DURACAO, fs=FS):
    """Gera o tom DTMF da tecla. Retorna (t, s_baixa, s_alta, tom)."""
    signal = signalMeu()
    f_baixa, f_alta = TABELA_DTMF[tecla]
    t, s_baixa = signal.generateSin(f_baixa, AMPLITUDE, duracao, fs)
    _, s_alta = signal.generateSin(f_alta, AMPLITUDE, duracao, fs)
    tom = s_baixa + s_alta
    return t, s_baixa, s_alta, tom


def plotar(tecla, t, s_baixa, s_alta, tom, fs=FS):
    signal = signalMeu()
    f_baixa, f_alta = TABELA_DTMF[tecla]
    n = int(JANELA_PLOT * fs)
    t_ms = t[:n] * 1000

    # tempo: as duas senoides separadas e a soma, só nos primeiros 20 ms
    fig, ax = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
    fig.suptitle(f"Tecla {tecla} - sinal no tempo (primeiros {JANELA_PLOT * 1000:.0f} ms)")
    ax[0].plot(t_ms, s_baixa[:n], color="#2a78d6", linewidth=1.5)
    ax[0].set_ylabel(f"{f_baixa} Hz")
    ax[1].plot(t_ms, s_alta[:n], color="#eb6834", linewidth=1.5)
    ax[1].set_ylabel(f"{f_alta} Hz")
    ax[2].plot(t_ms, tom[:n], color="#0b0b0b", linewidth=1.5)
    ax[2].set_ylabel("soma")
    ax[2].set_xlabel("tempo (ms)")
    for a in ax:
        a.grid(True, color="#e1e0d9", linewidth=0.8)

    # frequência: Fourier do sinal emitido
    xf, yf = signal.calcFFT(tom, fs)
    plt.figure(figsize=(9, 4))
    plt.plot(xf, yf, color="#2a78d6", linewidth=1.5)
    for f in (f_baixa, f_alta):
        k = np.argmin(np.abs(xf - f))
        plt.annotate(f"{f} Hz", (xf[k], yf[k]), textcoords="offset points",
                     xytext=(8, -4), color="#0b0b0b")
    plt.title(f"Tecla {tecla} - transformada de Fourier do sinal emitido")
    plt.xlabel("Frequência (Hz)")
    plt.ylabel("|X(f)|")
    plt.xlim(0, FMAX_PLOT)
    plt.grid(True, color="#e1e0d9", linewidth=0.8)


def salvar_wav(tecla, tom_saida, fs=FS):
    os.makedirs("tons", exist_ok=True)
    nome_tecla = {"*": "asterisco", "#": "sustenido"}.get(tecla, tecla)
    caminho = os.path.join("tons", f"tecla_{nome_tecla}.wav")
    wavfile.write(caminho, fs, (tom_saida * 32767).astype(np.int16))
    print(f"Sinal salvo em {caminho}")


def emitir(tecla, duracao, salvar):
    f_baixa, f_alta = TABELA_DTMF[tecla]
    print("Gerando Tons base")
    t, s_baixa, s_alta, tom = gerar_tom(tecla, duracao)

    # Cada senoide tem amplitude 1, então a soma vai de -2 a 2. A placa de som
    # só aceita valores entre -1 e 1: acima disso o sinal é cortado (clipping),
    # o que distorce a onda e cria frequências que não existiam. Dividir por 2
    # mantém o formato da onda e cabe na faixa.
    tom_saida = tom / 2

    print(f"Gerando Tom referente ao símbolo : {tecla}")
    print(f"Frequências : {f_baixa} + {f_alta} Hz")
    if salvar:
        salvar_wav(tecla, tom_saida)

    print(f"Executando as senoides (emitindo o som por {duracao} s)")
    sd.play(tom_saida, FS)      # não bloqueia: o som toca enquanto plotamos

    print("Plotando")
    plotar(tecla, t, s_baixa, s_alta, tom)
    plt.show()                  # bloqueia até as janelas serem fechadas

    sd.wait()                   # garante que o áudio terminou


def main():
    sinais.signal(sinais.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description="Emissor DTMF")
    parser.add_argument("tecla", nargs="?", help="tecla a emitir (sem ela, pergunta)")
    parser.add_argument("--duracao", type=float, default=DURACAO, help="segundos de som")
    parser.add_argument("--salvar", action="store_true", help="grava o tom em tons/*.wav")
    args = parser.parse_args()

    print("Inicializando encoder")
    if args.tecla is not None:
        tecla = args.tecla.strip().upper().replace("X", "*")
        if tecla not in TABELA_DTMF:
            sys.exit(f"Tecla inválida: {args.tecla}")
        emitir(tecla, args.duracao, args.salvar)
        return

    while True:
        print("Aguardando usuário")
        tecla = pedir_tecla()
        if tecla is None:
            break
        emitir(tecla, args.duracao, args.salvar)


if __name__ == "__main__":
    main()
