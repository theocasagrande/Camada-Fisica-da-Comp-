
# Biblioteca de apoio do Projeto 6 (DTMF).
#
# Reescrita da "suaBibSignal" cedida em aula, mantendo a mesma interface
# (classe signalMeu com generateSin, calcFFT e plotFFT), com três correções:
#   - a janela de Hamming vem de np.hamming (scipy.signal.hamming foi removida
#     do SciPy a partir da versão 1.13 e quebra o código original);
#   - o eixo de frequências usa np.fft.rfftfreq, que dá exatamente k*fs/N
#     (o linspace(0, fs/2, N//2) original fica levemente desalinhado);
#   - o vetor de tempo usa passo exato 1/fs (np.arange(n)/fs).

import numpy as np
import matplotlib.pyplot as plt


# ------------------------------------------------------------------ tabela DTMF
#
# Valores do padrão DTMF (ITU-T Q.23). A tabela do enunciado mostra 679 Hz e
# 825 Hz, que são 697 Hz e 852 Hz com os dígitos trocados: o próprio exemplo de
# saída do enunciado usa "1209 + 852" para a tecla 7.
# A tecla "X" do enunciado é o asterisco do teclado telefônico.

FREQS_BAIXAS = (697, 770, 852, 941)        # linhas do teclado
FREQS_ALTAS = (1209, 1336, 1477, 1633)     # colunas do teclado

TECLADO = (
    ("1", "2", "3", "A"),
    ("4", "5", "6", "B"),
    ("7", "8", "9", "C"),
    ("*", "0", "#", "D"),
)

# tecla -> (frequência baixa, frequência alta)
TABELA_DTMF = {
    TECLADO[i][j]: (FREQS_BAIXAS[i], FREQS_ALTAS[j])
    for i in range(4)
    for j in range(4)
}

# (frequência baixa, frequência alta) -> tecla
TECLA_POR_FREQS = {freqs: tecla for tecla, freqs in TABELA_DTMF.items()}


class signalMeu:

    def __init__(self):
        self.init = 0

    def generateSin(self, freq, amplitude, time, fs):
        """Senoide A*sin(2*pi*f*t) com `time` segundos amostrada a `fs` Hz."""
        n = int(round(time * fs))
        t = np.arange(n) / fs
        s = amplitude * np.sin(2 * np.pi * freq * t)
        return (t, s)

    def calcFFT(self, signal, fs):
        """Módulo da FFT (só frequências positivas) do sinal janelado.

        Retorna (xf, yf): xf são as frequências em Hz (passo fs/N) e yf o
        módulo |X(f)| correspondente. A janela de Hamming reduz o vazamento
        espectral causado por cortar o sinal num trecho finito.
        """
        signal = np.asarray(signal, dtype=float)
        N = len(signal)
        W = np.hamming(N)
        yf = np.fft.rfft(signal * W)
        xf = np.fft.rfftfreq(N, 1 / fs)
        return (xf, np.abs(yf))

    def plotFFT(self, signal, fs, titulo="Fourier", fmax=None):
        xf, yf = self.calcFFT(signal, fs)
        plt.figure()
        plt.plot(xf, yf, color="#2a78d6", linewidth=1)
        plt.title(titulo)
        plt.xlabel("Frequência (Hz)")
        plt.ylabel("|X(f)|")
        if fmax is not None:
            plt.xlim(0, fmax)
        plt.grid(True, color="#e1e0d9", linewidth=0.8)
        return xf, yf
