
# Projeto 7 - Exercícios 1 a 6 do enunciado (filtros_digitais.pdf)
#
#   python exercicios.py            -> todos, em sequência
#   python exercicios.py 1          -> só o exercício 1 (passa-baixa num sinal com harmônicos)
#   python exercicios.py 1 --sem-audio  -> exercício 1 sem tocar os áudios
#
# Cada exercício imprime as contas no terminal e, quando faz sentido, abre os
# gráficos. As respostas comentadas estão em Explicação.MD.

import argparse

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq
from scipy.signal import TransferFunction, butter, freqz, iirnotch, iirpeak, lfilter

from filtros import FS, em_db, filtro_IIR_ordem2

try:
    import sounddevice as sd
except ImportError:         # sem placa de som o exercício 1 só não toca
    sd = None

AZUL, LARANJA, CINZA, PRETO, GRADE = "#2a78d6", "#eb6834", "#a3a29a", "#0b0b0b", "#e1e0d9"
FC = 500                    # frequência de corte do passa-baixa do enunciado
TONS = (300, 1500, 5000)    # Hz: um abaixo e dois acima do corte
AMPLITUDE = 0.3             # de cada tom; a soma fica abaixo de 1
DURACAO = 3                 # segundos
VALORES_Q = (1, 2, 5, 10, 30)


def passa_baixa():
    """O filtro do enunciado: Butterworth de ordem 2, corte em 500 Hz."""
    return butter(N=2, Wn=FC / (FS / 2), btype="low")


def espectro(x, fs=FS):
    """Amplitude de cada senoide que compõe x (janela de Hann, só freqs positivas).

    A escala 2/soma(janela) faz um tom A sen(2 pi f t) aparecer com altura A.
    """
    janela = np.hanning(len(x))
    X = np.fft.rfft(x * janela)
    return np.fft.rfftfreq(len(x), 1 / fs), 2 * np.abs(X) / janela.sum()


def ganho_em(b, a, f, fs=FS):
    _, h = freqz(b, a, worN=[f], fs=fs)
    return abs(h[0])


def largura_de_banda(b, a, dentro, fs=FS):
    """Largura (Hz) do trecho em que `dentro(ganho_db)` é verdadeiro."""
    freqs = np.linspace(1, fs / 2, 400000)
    _, h = freqz(b, a, worN=freqs, fs=fs)
    sel = freqs[dentro(em_db(h))]
    return (sel[-1] - sel[0], sel[0], sel[-1]) if len(sel) else (0, None, None)


def estilo(ax, titulo, xlabel, ylabel):
    ax.set_title(titulo, loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, which="both", color=GRADE, linewidth=0.8)


# ---------------------------------------------------------------- exercício 1

def exercicio1(tocar=True):
    print("\n=== Exercício 1 - passa-baixa de 500 Hz num sinal com componentes acima de 500 Hz")
    b, a = passa_baixa()
    print(f"b = {np.round(b, 8)}\na = {np.round(a, 8)}")
    print(f"G(z) = ({b[0]:.8f} z² + {b[1]:.8f} z + {b[2]:.8f}) / (z² {a[1]:+.8f} z {a[2]:+.8f})")
    print(f"y[n] = {-a[1]:.8f} y[n-1] {-a[2]:+.8f} y[n-2] + {b[0]:.8f} x[n] "
          f"+ {b[1]:.8f} x[n-1] + {b[2]:.8f} x[n-2]")

    t = np.arange(int(DURACAO * FS)) / FS
    x = sum(AMPLITUDE * np.sin(2 * np.pi * f * t) for f in TONS)
    y = filtro_IIR_ordem2(x, b, a)          # a equação de diferenças, na mão
    diferenca = np.max(np.abs(y - lfilter(b, a, x)))
    print(f"\nSinal: soma de senoides de {TONS} Hz, amplitude {AMPLITUDE} cada, {DURACAO} s a {FS} Hz")
    print(f"Maior diferença entre a equação na mão e scipy.signal.lfilter: {diferenca:.1e}")

    fx, Ax = espectro(x)
    fy, Ay = espectro(y)
    print(f"\n{'tom':>8} {'amp. entrada':>13} {'amp. saída':>11} {'ganho medido':>13} {'ganho do Bode':>14}")
    for f in TONS:
        k = np.argmin(np.abs(fx - f))
        print(f"{f:6d} Hz {Ax[k]:13.4f} {Ay[k]:11.4f} {20 * np.log10(Ay[k] / Ax[k]):10.1f} dB "
              f"{20 * np.log10(ganho_em(b, a, f)):11.1f} dB")

    fig, ax = plt.subplots(3, 1, figsize=(9, 9), layout="constrained")
    fig.suptitle("Exercício 1 - passa-baixa Butterworth de 500 Hz")
    n = int(0.02 * FS)
    meio = len(t) // 2                      # longe do começo, onde o filtro ainda acomoda
    ax[0].plot(t[meio:meio + n] * 1000, x[meio:meio + n], color=CINZA, linewidth=1.2, label="original")
    ax[0].plot(t[meio:meio + n] * 1000, y[meio:meio + n], color=AZUL, linewidth=1.8, label="filtrado")
    ax[0].legend(loc="upper right")
    estilo(ax[0], "No tempo (20 ms)", "tempo (ms)", "amplitude")
    for eixo, A, cor, nome in ((ax[1], Ax, CINZA, "original"), (ax[2], Ay, AZUL, "filtrado")):
        eixo.plot(fx, A, color=cor, linewidth=1.5)
        eixo.axvline(FC, color=LARANJA, linestyle="--", linewidth=1.2, label="corte: 500 Hz")
        eixo.set_xlim(0, 6000)
        eixo.set_ylim(0, AMPLITUDE * 1.15)
        eixo.legend(loc="upper right")
        estilo(eixo, f"FFT do sinal {nome}", "Frequência (Hz)", "amplitude")

    if tocar and sd is None:
        print("\nsounddevice não instalado: pip install sounddevice")
    elif tocar:
        pausa = np.zeros(int(0.6 * FS))
        print(f"\nTocando: original ({DURACAO} s), pausa, filtrado ({DURACAO} s)")
        sd.play(np.concatenate([x, pausa, y]), FS)     # não bloqueia: toca com os gráficos abertos


# ---------------------------------------------------------------- exercícios 2 e 3

def exercicio2():
    print("\n=== Exercício 2 - intensidade sonora em dB:  I_dB = 10 log10(I / 1e-12)")
    for nome, I in (("limiar da audição", 1e-12), ("limiar da dor", 1e0)):
        print(f"{nome:>18}: I = {I:.0e} W/m²  ->  10 log10({I:.0e} / 1e-12) = {10 * np.log10(I / 1e-12):.0f} dB")


def exercicio3():
    print("\n=== Exercício 3 - ganho de U(t) = 20 sen(1000 pi t) para Y(t) = 10 sen(1000 pi t)")
    print(f"G = 20 log10(10 / 20) = 20 log10(0,5) = {20 * np.log10(10 / 20):.2f} dB")
    print("(a frequência é 1000 pi / 2 pi = 500 Hz; a saída tem metade da amplitude)")


# ---------------------------------------------------------------- exercício 4

def exercicio4():
    print("\n=== Exercício 4 - lendo o Bode do passa-baixa do exercício 1")
    b, a = passa_baixa()
    print("4a) O Bode do enunciado está em rad/s: f = omega / (2 pi)")
    pontos = []
    for omega in (1e4, 1e3):
        f = omega / (2 * np.pi)
        g = ganho_em(b, a, f)
        pontos.append((omega, 20 * np.log10(g)))
        print(f"    U(t) = 50 sen({omega:.0f} t): f = {f:.1f} Hz, ganho = {20 * np.log10(g):.2f} dB "
              f"= x{g:.4f}  ->  amplitude de saída = 50 x {g:.4f} = {50 * g:.2f}")

    g6 = 10**(-6 / 20)
    f6 = brentq(lambda f: ganho_em(b, a, f) - g6, 100, 5000)
    f3 = brentq(lambda f: ganho_em(b, a, f) - 1 / np.sqrt(2), 100, 5000)
    print(f"4b) -6 dB em f = {f6:.0f} Hz = {2 * np.pi * f6:.0f} rad/s; "
          f"saída/entrada = 10^(-6/20) = {g6:.3f} (metade da amplitude)")
    print(f"    (referência: o butter foi projetado com -3 dB em {f3:.0f} Hz, saída/entrada = 0,707)")

    freqs = np.logspace(1, np.log10(FS / 2), 2000, endpoint=False)
    _, h = freqz(b, a, worN=freqs, fs=FS)
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    ax.semilogx(2 * np.pi * freqs, em_db(h), color=AZUL, linewidth=2)
    for omega, db in pontos:
        ax.plot(omega, db, "o", color=LARANJA, markersize=8)
        ax.annotate(f"$10^{np.log10(omega):.0f}$ rad/s: {db:.2f} dB", (omega, db),
                    textcoords="offset points", xytext=(10, 6), color=PRETO)
    ax.plot(2 * np.pi * f6, -6, "s", color=PRETO, markersize=7)
    ax.annotate(f"-6 dB em {2 * np.pi * f6:.0f} rad/s ({f6:.0f} Hz)", (2 * np.pi * f6, -6),
                textcoords="offset points", xytext=(10, 6), color=PRETO)
    ax.set_xlim(600, 2 * np.pi * FS / 2)
    ax.set_ylim(-90, 10)
    estilo(ax, "Exercício 4 - Bode do passa-baixa (eixo em rad/s, como no enunciado)",
           "Frequência (rad/s)", "Ganho (dB)")


# ---------------------------------------------------------------- exercícios 5 e 6

def cores_por_q():
    """Q é uma grandeza ordenada: um tom de azul, do claro (Q baixo) ao escuro."""
    return plt.get_cmap("Blues")(np.linspace(0.35, 1.0, len(VALORES_Q)))


def exercicio5():
    print("\n=== Exercício 5 - passa-faixa (iirpeak) centrado em 2 kHz")
    f0 = 2000
    b, a = iirpeak(w0=f0 / (FS / 2), Q=10)
    print("Código do enunciado com Q = 10:")
    print(TransferFunction(b, a, dt=1 / FS))
    print(f"\n{'Q':>4} {'largura -3 dB':>14} {'f0/Q':>8} {'faixa que passa':>22} {'ganho em 500 Hz':>16}")
    freqs = np.logspace(1, np.log10(FS / 2), 3000, endpoint=False)
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    for Q, cor in zip(VALORES_Q, cores_por_q()):
        b, a = iirpeak(w0=f0 / (FS / 2), Q=Q)
        bw, lo, hi = largura_de_banda(b, a, lambda db: db >= -3.0103)
        print(f"{Q:4d} {bw:11.0f} Hz {f0 / Q:5.0f} Hz {lo:9.0f} a {hi:6.0f} Hz "
              f"{20 * np.log10(ganho_em(b, a, 500)):13.1f} dB")
        _, h = freqz(b, a, worN=freqs, fs=FS)
        ax.semilogx(freqs, em_db(h), color=cor, linewidth=1.8, label=f"Q = {Q}")
    ax.axhline(-3, color=LARANJA, linestyle="--", linewidth=1, label="-3 dB")
    ax.set_xlim(100, FS / 2)
    ax.set_ylim(-50, 3)
    ax.legend(loc="upper right")
    estilo(ax, "Exercício 5 - passa-faixa em 2 kHz: quanto maior Q, mais estreita a faixa",
           "Frequência (Hz)", "Ganho (dB)")


def exercicio6():
    print("\n=== Exercício 6 - rejeita-faixa (iirnotch) centrado em 2 kHz")
    f0 = 2000
    print(f"{'Q':>4} {'largura rejeitada (-3 dB)':>26} {'f0/Q':>8} {'ganho em 1900 Hz':>17}")
    # as próprias frequências centrais entram na grade: senão o fundo do "buraco"
    # cai entre dois pontos e parece ter profundidades diferentes
    freqs = np.sort(np.append(np.logspace(1, np.log10(FS / 2), 4000, endpoint=False),
                              [60, 1000, 2000, 5000]))
    fig, ax = plt.subplots(2, 1, figsize=(9, 8), layout="constrained")
    for Q, cor in zip(VALORES_Q, cores_por_q()):
        b, a = iirnotch(w0=f0 / (FS / 2), Q=Q)
        bw, _, _ = largura_de_banda(b, a, lambda db: db < -3.0103)
        print(f"{Q:4d} {bw:23.0f} Hz {f0 / Q:5.0f} Hz {20 * np.log10(ganho_em(b, a, 1900)):14.1f} dB")
        _, h = freqz(b, a, worN=freqs, fs=FS)
        ax[0].semilogx(freqs, em_db(h), color=cor, linewidth=1.8, label=f"Q = {Q}")
    print("Na própria f0 o ganho é zero (-infinito em dB): o filtro tem um zero em cima de f0.")
    ax[0].axhline(-3, color=LARANJA, linestyle="--", linewidth=1, label="-3 dB")
    ax[0].set_xlim(100, FS / 2)
    ax[0].set_ylim(-60, 5)
    ax[0].legend(loc="lower left")
    estilo(ax[0], "Rejeita-faixa em 2 kHz: Q controla a largura do 'buraco'", "Frequência (Hz)", "Ganho (dB)")

    for f in (60, 1000, 5000):
        b, a = iirnotch(w0=f / (FS / 2), Q=30)
        _, h = freqz(b, a, worN=freqs, fs=FS)
        ax[1].semilogx(freqs, em_db(h), color=AZUL, linewidth=1.8)
        ax[1].annotate(f"{f} Hz", (f, -45), textcoords="offset points", xytext=(6, 0), color=PRETO)
    ax[1].set_xlim(20, FS / 2)
    ax[1].set_ylim(-60, 5)
    estilo(ax[1], "Mudando a frequência central (Q = 30): 60 Hz, 1 kHz e 5 kHz",
           "Frequência (Hz)", "Ganho (dB)")


def main():
    parser = argparse.ArgumentParser(description="Exercícios do Projeto 7")
    parser.add_argument("exercicio", nargs="?", type=int, choices=range(1, 7),
                        help="número do exercício (sem ele, roda todos)")
    parser.add_argument("--sem-audio", action="store_true", help="não toca os áudios do exercício 1")
    args = parser.parse_args()

    exercicios = {1: lambda: exercicio1(not args.sem_audio), 2: exercicio2, 3: exercicio3,
                  4: exercicio4, 5: exercicio5, 6: exercicio6}
    for n in ([args.exercicio] if args.exercicio else exercicios):
        exercicios[n]()
    plt.show()              # bloqueia até as janelas serem fechadas
    if sd is not None:
        sd.wait()           # garante que o áudio do exercício 1 terminou


if __name__ == "__main__":
    main()
