
# Projeto 6 - DTMF - lado RECEPTOR
#
# Grava o som do microfone, calcula a transformada de Fourier, encontra os
# picos (pelo menos 5) e descobre qual tecla DTMF gerou o som.
#
#   python decode.py                          -> grava 2 s pelo microfone
#   python decode.py --duracao 3 --espera 5   -> grava 3 s depois de 5 s
#   python decode.py --arquivo tons/tecla_7.wav -> decodifica um .wav

import argparse
import time

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from scipy.signal import find_peaks

from suaBibSignal import FREQS_ALTAS, FREQS_BAIXAS, TECLA_POR_FREQS, signalMeu

try:
    import peakutils
except ImportError:         # sem peakutils, usa o find_peaks do SciPy
    peakutils = None

FS = 44100          # taxa de amostragem
CANAIS = 1          # mono: uma lista só de amostras
DURACAO = 2         # segundos de gravação
ESPERA = 3          # segundos de contagem antes de gravar

F_MIN, F_MAX = 500, 2000    # faixa onde procuramos os picos (DTMF: 697-1633 Hz)
MIN_PICOS = 5               # o enunciado pede pelo menos 5 picos
MAX_PICOS = 10              # mostramos e usamos só os 10 mais fortes
DIST_PICOS_HZ = 5           # picos a menos de 5 Hz um do outro contam como um só
TOLERANCIA = 0.02           # pico vale como frequência DTMF se estiver a até 2% dela
FATOR_PISO = 5              # pico precisa ser 5x (14 dB) maior que o piso de ruído
# Sensibilidade do detector: começa exigente e afrouxa até achar MIN_PICOS picos.
# O último (0) aceita qualquer máximo local; só é preciso para sinais sem ruído.
LIMIARES = (0.5, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0)


# função para transformar intensidade acústica em dB, caso queira usar
def todB(s):
    sdB = 10 * np.log10(s)
    return sdB


def gravar(duracao=DURACAO, espera=ESPERA, fs=FS):
    sd.default.samplerate = fs
    sd.default.channels = CANAIS
    numAmostras = int(duracao * fs)

    print(f"A captação começará em {espera} segundos. Dispare o emissor!")
    for falta in range(espera, 0, -1):
        print(f"  {falta}...")
        time.sleep(1)

    print("Gravação inicializada")
    audio = sd.rec(int(numAmostras), fs, channels=CANAIS)
    sd.wait()
    print("...     FIM")
    return audio


def ler_wav(caminho):
    fs, audio = wavfile.read(caminho)
    if np.issubdtype(audio.dtype, np.integer):
        audio = audio / np.iinfo(audio.dtype).max
    return audio, fs


def extrair_dados(audio):
    """A gravação pode vir como matriz (amostras x canais). Fica com um canal."""
    dados = np.asarray(audio, dtype=float)
    if dados.ndim > 1:
        dados = dados[:, 0]
    return dados - np.mean(dados)       # tira o nível DC do microfone


def trecho_com_som(dados, fs, quadro=0.02, limiar=0.3):
    """Índices (ini, fim) do trecho com som, descartando silêncio nas pontas.

    Divide a gravação em quadros de 20 ms e mantém do primeiro ao último
    quadro cuja energia (RMS) passa de 30% da maior energia.
    """
    n = int(quadro * fs)
    nq = len(dados) // n
    if nq < 2:
        return 0, len(dados)
    rms = np.sqrt(np.mean(dados[:nq * n].reshape(nq, n) ** 2, axis=1))
    ativos = np.nonzero(rms >= limiar * rms.max())[0]
    return ativos[0] * n, (ativos[-1] + 1) * n


def indices_de_picos(y, thres, min_dist):
    if peakutils is not None:
        return peakutils.indexes(y, thres=thres, min_dist=min_dist)
    altura = y.min() + thres * (y.max() - y.min())
    idx, _ = find_peaks(y, height=altura, distance=min_dist)
    return idx


def detectar_picos(xf, yf, fmin=F_MIN, fmax=F_MAX, min_picos=MIN_PICOS):
    """Picos de |X(f)| na faixa [fmin, fmax], do mais forte para o mais fraco.

    `thres` é a altura mínima do pico como fração do maior valor (0 a 1).
    Começamos exigentes e baixamos até aparecerem pelo menos `min_picos`.
    """
    faixa = (xf >= fmin) & (xf <= fmax)
    xb, yb = xf[faixa], yf[faixa]
    df = xf[1] - xf[0]
    min_dist = max(1, int(round(DIST_PICOS_HZ / df)))

    for thres in LIMIARES:
        idx = np.asarray(indices_de_picos(yb, thres, min_dist), dtype=int)
        if len(idx) >= min_picos:
            break
    idx = idx[np.argsort(yb[idx])[::-1]][:MAX_PICOS]
    piso = np.median(yb)
    return xb[idx], yb[idx], piso, thres


def mais_proxima(f, grupo):
    """Frequência DTMF do grupo mais próxima de f, ou None se longe demais."""
    alvo = min(grupo, key=lambda g: abs(g - f))
    return alvo if abs(alvo - f) <= TOLERANCIA * alvo else None


def identificar_tecla(freqs, mags, piso):
    """Escolhe o pico mais forte de cada grupo (baixo e alto) e acha a tecla.

    Toda tecla é exatamente uma frequência baixa (linha) + uma alta (coluna),
    então nunca escolhemos dois picos do mesmo grupo.
    """
    baixa = alta = None
    for f, m in zip(freqs, mags):           # já vem do mais forte ao mais fraco
        if m < FATOR_PISO * piso:
            continue                        # pico de ruído, fraco demais
        if baixa is None and mais_proxima(f, FREQS_BAIXAS):
            baixa = (mais_proxima(f, FREQS_BAIXAS), f, m)
        if alta is None and mais_proxima(f, FREQS_ALTAS):
            alta = (mais_proxima(f, FREQS_ALTAS), f, m)
    tecla = None
    if baixa and alta:
        tecla = TECLA_POR_FREQS[(baixa[0], alta[0])]
    return tecla, baixa, alta


def analisar(dados, fs):
    """Do sinal gravado até a tecla. Usado pelo main e pelos testes."""
    signal = signalMeu()
    ini, fim = trecho_com_som(dados, fs)
    xf, yf = signal.calcFFT(dados[ini:fim], fs)
    freqs, mags, piso, thres = detectar_picos(xf, yf)
    tecla, baixa, alta = identificar_tecla(freqs, mags, piso)
    return {
        "ini": ini, "fim": fim, "xf": xf, "yf": yf, "freqs": freqs,
        "mags": mags, "piso": piso, "thres": thres,
        "tecla": tecla, "baixa": baixa, "alta": alta,
    }


def imprimir(r):
    print(f"\nPicos encontrados (sensibilidade thres={r['thres']}), "
          "do mais forte para o mais fraco:")
    ref = r["mags"][0]
    for f, m in zip(r["freqs"], r["mags"]):
        db = round(20 * np.log10(max(m, 1e-300) / ref), 1) + 0.0  # 0 dB = mais forte
        print(f"   freq de pico = {f:8.1f} Hz   ({db:7.1f} dB)")
    if len(r["freqs"]) < MIN_PICOS:
        print(f"   (o espectro só tem {len(r['freqs'])} máximos locais na faixa: "
              "sinal sem nenhum ruído)")

    for nome, g in (("baixa", r["baixa"]), ("alta ", r["alta"])):
        if g:
            print(f"Frequência {nome}: {g[0]} Hz (pico em {g[1]:.1f} Hz)")
        else:
            print(f"Frequência {nome}: não encontrada")

    if r["tecla"]:
        print(f"\n==> TECLA IDENTIFICADA: {r['tecla']}")
    else:
        print("\n==> Nenhuma tecla DTMF reconhecida")


def plotar(dados, fs, r):
    t = np.linspace(0, len(dados) / fs, len(dados), endpoint=False)
    ini, fim = r["ini"], r["fim"]

    # tempo: gravação inteira (com o trecho usado destacado) e um zoom de 20 ms
    fig, ax = plt.subplots(2, 1, figsize=(9, 6))
    fig.suptitle("Sinal recebido no tempo")
    ax[0].plot(t, dados, color="#2a78d6", linewidth=0.6)
    ax[0].axvspan(t[ini], t[fim - 1], color="#2a78d6", alpha=0.10)
    ax[0].set_title("gravação inteira (faixa azul = trecho usado no Fourier)", fontsize=9)
    ax[0].set_xlabel("tempo (s)")
    meio = (ini + fim) // 2
    n = int(0.02 * fs)
    trecho = slice(meio, min(meio + n, len(dados)))
    ax[1].plot(t[trecho] * 1000, dados[trecho], color="#2a78d6", linewidth=1.5)
    ax[1].set_xlabel("tempo (ms) - zoom de 20 ms")
    for a in ax:
        a.grid(True, color="#e1e0d9", linewidth=0.8)
    fig.tight_layout()

    # frequência: Fourier com os picos encontrados e as 8 frequências DTMF
    xf, yf = r["xf"], r["yf"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    dtmf = FREQS_BAIXAS + FREQS_ALTAS
    for f in dtmf:
        ax.axvline(f, color="#c3c2b7", linewidth=0.8, zorder=0)
    topo = ax.secondary_xaxis("top")    # nomeia as linhas verticais DTMF
    topo.set_xticks(dtmf)
    topo.tick_params(labelsize=7, length=0)
    ax.plot(xf, yf, color="#2a78d6", linewidth=1.2, label="|X(f)|")
    ax.plot(r["freqs"], r["mags"], "o", color="#eb6834", markersize=6,
            label=f"{len(r['freqs'])} picos encontrados")
    for g in (r["baixa"], r["alta"]):
        if g:
            ax.annotate(f"{g[1]:.0f} Hz", (g[1], g[2]), textcoords="offset points",
                        xytext=(8, 0), color="#0b0b0b")
    titulo = f"tecla {r['tecla']}" if r["tecla"] else "nenhuma tecla"
    ax.set_title(f"Fourier do sinal recebido - {titulo}")
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("|X(f)|")
    ax.set_xlim(0, 2000)
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", color="#e1e0d9", linewidth=0.8)


def main():
    parser = argparse.ArgumentParser(description="Receptor DTMF")
    parser.add_argument("--arquivo", help="decodifica um .wav em vez de gravar")
    parser.add_argument("--duracao", type=float, default=DURACAO, help="segundos de gravação")
    parser.add_argument("--espera", type=int, default=ESPERA, help="segundos antes de gravar")
    args = parser.parse_args()

    if args.arquivo:
        audio, fs = ler_wav(args.arquivo)
        print(f"Lendo {args.arquivo} ({fs} Hz)")
    else:
        fs = FS
        audio = gravar(args.duracao, args.espera, fs)

    dados = extrair_dados(audio)
    r = analisar(dados, fs)
    imprimir(r)
    plotar(dados, fs, r)
    plt.show()


if __name__ == "__main__":
    main()
