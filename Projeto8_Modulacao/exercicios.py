
# Projeto 8 (parte 1) - Exercícios 1 a 7 do enunciado
#
#   python exercicios.py                 -> todos, em sequência (abre os gráficos no fim)
#   python exercicios.py 3               -> só o exercício 3
#   python exercicios.py 5 --sem-audio   -> exercício 5 sem tocar os áudios
#   python exercicios.py --sem-janela    -> só as contas; os gráficos vão para graficos/exercicios/
#   python exercicios.py 5 --arquivo minha_voz.wav
#
# Cada exercício imprime as contas no terminal e, quando faz sentido, desenha.

import argparse
import os
import sys

import numpy as np
from scipy.signal import find_peaks

from am import (FS, banda_ocupada, carregar_audio, correlacao, criar_estacao, db_potencia, demodular,
                espectro, fora_da_faixa, limitar_banda, modular, portadora, rebater, senoide, tempo)
from graficos import CINZA, CORES, TINTA, TINTA_2, eixo_khz, estilo, khz, legenda, num, reduzir

PASTA = os.path.dirname(os.path.abspath(__file__))
AUDIO_PADRAO = os.path.join(PASTA, "audios", "originais", "estacao_1.wav")
PASTA_FIGURAS = os.path.join(PASTA, "graficos", "exercicios")

FM, FC = 2000, 15000        # exercícios 1 a 3: informação de 2 kHz, portadora de 15 kHz
DURACAO = 2                 # s (o exercício 3 pede 2 s; o 1 usa o mesmo)

plt = None                  # importado em main(), depois de escolher o backend
sd = None
figuras = []


def nova_figura(nome, linhas=2, **kw):
    fig = plt.figure(nome, figsize=(11, 3.2 * linhas), layout="constrained")
    figuras.append((nome, fig))
    return fig.subplots(linhas, 1, **kw)


def picos(x, fs=FS, limiar=0.02):
    """Frequências e amplitudes dos picos da FFT acima de `limiar` x o maior."""
    f, X = espectro(x, fs)
    i, _ = find_peaks(X, height=limiar * np.max(X))
    return [(f[k], X[k]) for k in i]


def mostrar_picos(x, faixa):
    for f, amp in picos(x):
        dentro = faixa[0] <= f <= faixa[1]
        print(f"     {f:8.1f} Hz   amplitude {num(amp, 3)}   {'dentro' if dentro else 'FORA'} da faixa")


def tocar(rotulo, x, fs=FS):
    if sd is None:
        return
    print(f"   ▶ tocando: {rotulo}  ({num(len(x) / fs, 1)} s)")
    sd.play(0.9 * x / np.max(np.abs(x)), fs)
    sd.wait()


def sombra(ax, faixa, cor=CORES[0], rotulo=None):
    ax.axvspan(*faixa, color=cor, alpha=0.12, linewidth=0, label=rotulo)


# ---------------------------------------------------------------- exercício 1

def exercicio1():
    print("\n=== Exercício 1 - SOMAR informação e portadora não é modular")
    faixa = (12000, 18000)
    n = DURACAO * FS
    m = senoide(FM, n)
    c = portadora(FC, n)
    soma = m + c
    print(f"m(t) = sen(2π·{FM}t), C(t) = sen(2π·{FC}t), soma com {n} pontos a {FS} Hz.")
    print(f"Picos da FFT de m(t) + C(t) (banda permitida {faixa[0]}-{faixa[1]} Hz):")
    mostrar_picos(soma, faixa)
    fora = fora_da_faixa(soma, faixa)
    print(f"   -> {num(100 * fora, 1)}% da energia está FORA da banda: a soma mantém os 2 kHz "
          f"originais, então NÃO pode ser transmitida.")

    ax_t, ax_f = nova_figura("Exercício 1 - soma")
    t = tempo(n) * 1000
    ax_t.plot(t[:120], soma[:120], color=CORES[0], linewidth=1.2, label="m(t) + C(t)")
    ax_t.plot(t[:120], m[:120], color=TINTA, linestyle="--", linewidth=1, label="m(t) (2 kHz)")
    estilo(ax_t, "Soma no tempo: a portadora 'anda em cima' da senoide de 2 kHz (a 44,1 kHz há só "
                 "~3 pontos por ciclo de 15 kHz, por isso o traço é quebrado)", "Tempo (ms)", "amplitude")
    legenda(ax_t, loc="upper right")
    sombra(ax_f, faixa, CORES[2], "banda permitida 12–18 kHz")
    f, X = espectro(soma)
    ax_f.plot(f, X, color=CORES[0], linewidth=1)
    ax_f.annotate("2 kHz: FORA da banda", (FM, 1), (FM + 1200, 0.8), fontsize=8, color=TINTA_2,
                  arrowprops=dict(arrowstyle="->", color=TINTA_2))
    eixo_khz(ax_f, 0, FS / 2)
    estilo(ax_f, "FFT da soma: a soma tem as frequências dos DOIS sinais", "Frequência (kHz)", "|X(f)|")
    legenda(ax_f, loc="upper right")


# ---------------------------------------------------------------- exercício 2

def exercicio2():
    print("\n=== Exercício 2 - banda mínima do AM por multiplicação")
    print(f"sen(2π·fc·t)·sen(2π·fm·t) = ½[cos(2π(fc−fm)t) − cos(2π(fc+fm)t)]")
    print(f"   fc − fm = {FC} − {FM} = {FC - FM} Hz")
    print(f"   fc + fm = {FC} + {FM} = {FC + FM} Hz")
    print(f"   -> banda mínima: de {FC - FM} a {FC + FM} Hz, largura 2·fm = {2 * FM} Hz "
          f"(cabe nos 12-18 kHz do exercício 1)")


# ---------------------------------------------------------------- exercício 3

def exercicio3():
    print("\n=== Exercício 3 - AM pela multiplicação ponto a ponto")
    n = DURACAO * FS
    m = senoide(FM, n)
    c = portadora(FC, n)
    s = m * c                       # multiplicação ponto a ponto das duas listas
    faixa = (FC - FM, FC + FM)
    print(f"m e C com {DURACAO} s a {FS} Hz ({n} pontos cada). Picos da FFT de S(t) = m(t)·C(t):")
    mostrar_picos(s, faixa)
    print(f"   -> só {FC - FM} e {FC + FM} Hz, cada um com amplitude 0,5 (o ½ da identidade). "
          f"Energia fora de {faixa[0]}-{faixa[1]} Hz: {num(db_potencia(fora_da_faixa(s, (faixa[0] - 1, faixa[1] + 1))), 0)} dB")

    ax_t, ax_f = nova_figura("Exercício 3 - multiplicação")
    t = tempo(n) * 1000
    k = int(0.0015 * FS)
    ax_t.plot(t[:k], s[:k], color=CORES[0], linewidth=1.2, label="S(t) = m(t)·C(t)")
    ax_t.plot(t[:k], m[:k], color=TINTA, linestyle="--", linewidth=1, label="±m(t)")
    ax_t.plot(t[:k], -m[:k], color=TINTA, linestyle="--", linewidth=1)
    estilo(ax_t, "No tempo: a amplitude da portadora segue m(t) e inverte quando m(t) < 0 "
                 "(~3 pontos por ciclo de 15 kHz)", "Tempo (ms)", "amplitude")
    legenda(ax_t, loc="upper right")
    sombra(ax_f, (12000, 18000), CORES[2], "banda permitida 12–18 kHz")
    sombra(ax_f, faixa, CORES[0], f"banda mínima {khz(faixa[0])}–{khz(faixa[1])}")
    f, X = espectro(s)
    ax_f.plot(f, X, color=CORES[0], linewidth=1)
    for fr in faixa:
        ax_f.text(fr, 0.55, khz(fr), ha="center", fontsize=8, color=TINTA_2)
    ax_f.set_ylim(0, 0.65)
    eixo_khz(ax_f, 0, FS / 2)
    estilo(ax_f, "FFT do produto: nada em 2 kHz nem em 15 kHz, só fc ± fm", "Frequência (kHz)", "|X(f)|")
    legenda(ax_f, loc="upper left")


# ---------------------------------------------------------------- exercício 4

def exercicio4():
    print("\n=== Exercício 4 - mensagem de 20 a 2000 Hz, portadora de 15 kHz, banda 14-16 kHz")
    print("Modulando direto, a mensagem até 2000 Hz ocuparia 15000 ± 2000 = 13 a 17 kHz:")
    print("4 kHz de largura, o dobro dos 2 kHz permitidos. Para caber em 14-16 kHz é preciso")
    print("fm_max ≤ 1000 Hz: passar m(t) por um FILTRO PASSA-BAIXA de 1 kHz antes de modular")
    print("(perde-se o trecho de 1 a 2 kHz da mensagem: é o preço de caber na banda).")
    print("Na prática o filtro não corta 'de uma vez' em 1 kHz, então cortamos um pouco antes")
    estacao = criar_estacao(4, (14000, 16000))
    print(f"(aqui {estacao.corte:.0f} Hz, 80% de 1 kHz) para sobrar margem de atenuação.")

    n = DURACAO * FS
    rng = np.random.default_rng(4)
    freqs = np.linspace(20, 2000, 40)
    m = sum(senoide(f, n, fase=rng.uniform(0, 2 * np.pi)) for f in freqs) / len(freqs)
    sem_filtro = modular(m, estacao.fc)
    com_filtro = modular(limitar_banda(m, estacao), estacao.fc)
    faixa = (estacao.f_ini, estacao.f_fim)
    print(f"Medido com 40 senoides de 20 a 2000 Hz:")
    print(f"   sem filtro: {num(100 * fora_da_faixa(sem_filtro, faixa), 1)}% da energia fora de 14-16 kHz")
    print(f"   com passa-baixa de {estacao.corte:.0f} Hz: "
          f"{num(db_potencia(fora_da_faixa(com_filtro, faixa)), 0)} dB fora (praticamente nada)")

    eixos = nova_figura("Exercício 4 - filtrar antes de modular", sharex=True)
    for ax, x, titulo in ((eixos[0], sem_filtro, "Sem filtro: ocupa 13–17 kHz e invade fora da banda"),
                          (eixos[1], com_filtro, f"Com passa-baixa de {khz(estacao.corte)} antes: "
                                                 f"cabe em 14–16 kHz")):
        sombra(ax, faixa, CORES[2], "banda permitida 14–16 kHz")
        f, X = espectro(x)
        ax.plot(f, X, color=CORES[0], linewidth=0.9)
        estilo(ax, titulo, ylabel="|X(f)|")
        legenda(ax, loc="upper right")
    eixo_khz(eixos[1], 11000, 19000)
    eixos[1].set_xlabel("Frequência (kHz)", fontsize=8, color=TINTA_2)


# ---------------------------------------------------------------- exercício 5

def exercicio5(arquivo=AUDIO_PADRAO):
    print(f"\n=== Exercício 5 - AM de um áudio: portadora de 16 kHz, faixa 14-18 kHz")
    estacao = criar_estacao(5, (14000, 18000))
    audio = carregar_audio(arquivo)
    n = len(audio)
    print(f"1) Áudio: {os.path.relpath(arquivo, PASTA)}, {n} pontos = {num(n / FS, 2)} s a {FS} Hz")
    print(f"   99% da energia abaixo de {banda_ocupada(audio):.0f} Hz")
    tocar("áudio original", audio)

    c = portadora(estacao.fc, n)
    print(f"2) Portadora de {estacao.fc:.0f} Hz com {len(c)} pontos (o mesmo número do áudio)")

    print(f"3) A faixa 14-18 kHz tem 4 kHz: com a portadora no centro, a mensagem pode ir até "
          f"{estacao.meia_largura:.0f} Hz.")
    print(f"   O áudio passa antes por um passa-baixa de {estacao.corte:.0f} Hz (80% de 2 kHz, ver exercício 4).")
    m = limitar_banda(audio, estacao)
    s = m * c                                   # a modulação: multiplicação ponto a ponto
    fora = db_potencia(fora_da_faixa(s, (estacao.f_ini, estacao.f_fim)))
    print(f"4) Modulado ocupa {estacao.fc - estacao.corte:.0f}-{estacao.fc + estacao.corte:.0f} Hz; "
          f"energia fora de 14-18 kHz: {num(fora, 0)} dB -> dentro da banda")
    tocar("5) sinal modulado (agudo: está entre 14 e 18 kHz)", s)

    demodulado, produto = demodular(s, estacao)
    print(f"6) Demodulação: S(t)·C(t) e passa-baixa de {estacao.meia_largura:.0f} Hz, depois × 2")
    print(f"7) Correlação demodulado x mensagem transmitida: {num(correlacao(m, demodulado), 6)}")
    print(f"   Correlação demodulado x áudio original (sem o passa-baixa): "
          f"{num(correlacao(audio, demodulado), 3)} - falta só o que foi cortado acima de "
          f"{estacao.corte:.0f} Hz")
    tocar("8) sinal demodulado", demodulado)

    ax1, ax2, ax3, ax4 = nova_figura("Exercício 5 - áudio em AM", linhas=4)
    f, X = reduzir(*espectro(audio))
    ax1.plot(f, X / X.max(), color=CINZA, linewidth=0.8)
    eixo_khz(ax1, 0, FS / 2)
    estilo(ax1, "1) FFT do áudio original", ylabel="|X(f)| (pico = 1)")
    sombra(ax2, (estacao.f_ini, estacao.f_fim), CORES[2], "faixa 14–18 kHz")
    f, X = reduzir(*espectro(s))
    ax2.plot(f, X, color=CORES[0], linewidth=0.8)
    eixo_khz(ax2, 0, FS / 2)
    estilo(ax2, f"4) FFT do modulado (portadora 16 kHz): energia fora da faixa = {num(fora, 0)} dB",
           ylabel="|S(f)|")
    legenda(ax2, loc="upper left")
    f, X = reduzir(*espectro(produto))
    ax3.plot(f, X, color=CORES[1], linewidth=0.8)
    eixo_khz(ax3, 0, FS / 2)
    estilo(ax3, f"6) FFT de S(t)·C(t): a informação volta para perto de 0 Hz; a cópia em 2fc = "
                f"{khz(2 * estacao.fc)} passa de Nyquist e aparece em {khz(rebater(2 * estacao.fc))}",
           ylabel="|X(f)|")
    for x, cor, larg, rot in ((m, CINZA, 2.4, "transmitido (original com passa-baixa)"),
                              (demodulado, CORES[0], 0.9, "demodulado")):
        f, X = reduzir(*espectro(x))
        ax4.plot(f, X / X.max(), color=cor, linewidth=larg, label=rot)
    eixo_khz(ax4, 0, 4000)
    estilo(ax4, f"7) FFT do demodulado: correlação {num(correlacao(m, demodulado), 5)} com o transmitido",
           "Frequência (kHz)", "|X(f)| (pico = 1)")
    legenda(ax4, loc="upper right")


# ---------------------------------------------------------------- exercícios 6 e 7

def taxa_qam(niveis_fase, niveis_amplitude, fc, periodos_por_simbolo):
    simbolos = niveis_fase * niveis_amplitude
    bits = int(np.log2(simbolos))
    simbolos_por_s = fc / periodos_por_simbolo
    return simbolos, bits, simbolos_por_s, bits * simbolos_por_s


def exercicio6():
    print("\n=== Exercício 6 - 64-QAM a 2,4 GHz, um símbolo a cada 2 períodos")
    simbolos, bits, baud, taxa = taxa_qam(8, 8, 2.4e9, 2)
    print(f"   8 fases × 8 amplitudes = {simbolos} símbolos -> log2({simbolos}) = {bits} bits por símbolo")
    print(f"   período da portadora = 1/2,4 GHz = {1e9 / 2.4e9:.4f} ns; símbolo a cada 2 períodos")
    print(f"   símbolos por segundo = 2,4·10⁹ / 2 = {baud:.2e}")
    print(f"   taxa = {bits} × {baud:.2e} = {taxa:.2e} bit/s = {num(taxa / 1e9, 1)} Gbit/s")


def exercicio7():
    print("\n=== Exercício 7 - 256-QAM a 2,4 GHz, um símbolo a cada 10 períodos, 480 MB")
    simbolos, bits, baud, taxa = taxa_qam(16, 16, 2.4e9, 10)
    print(f"   16 fases × 16 amplitudes = {simbolos} símbolos -> {bits} bits por símbolo")
    print(f"   símbolos por segundo = 2,4·10⁹ / 10 = {baud:.2e}")
    print(f"   taxa = {bits} × {baud:.2e} = {taxa:.3e} bit/s = {num(taxa / 1e9, 2)} Gbit/s")
    total = 480e6 * 8
    print(f"   480 MB = 480·10⁶ bytes × 8 = {total:.3e} bits")
    print(f"   tempo = {total:.3e} / {taxa:.3e} = {num(total / taxa, 2)} s")
    total_mib = 480 * 2 ** 20 * 8
    print(f"   (se MB = 2²⁰ bytes, MiB: {total_mib:.4e} bits -> {num(total_mib / taxa, 2)} s)")


EXERCICIOS = {1: exercicio1, 2: exercicio2, 3: exercicio3, 4: exercicio4,
              5: exercicio5, 6: exercicio6, 7: exercicio7}


def main():
    global plt, sd
    parser = argparse.ArgumentParser(description="Exercícios 1 a 7 do Projeto 8 (parte 1)")
    parser.add_argument("numero", nargs="?", type=int, choices=sorted(EXERCICIOS))
    parser.add_argument("--sem-audio", action="store_true", help="não toca os áudios do exercício 5")
    parser.add_argument("--sem-janela", action="store_true",
                        help="não abre janelas: salva os gráficos em graficos/exercicios/ (e não toca áudio)")
    parser.add_argument("--arquivo", default=AUDIO_PADRAO, help="áudio do exercício 5")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    import matplotlib
    if args.sem_janela:
        matplotlib.use("Agg")
    import matplotlib.pyplot as pyplot
    plt = pyplot
    if not (args.sem_audio or args.sem_janela):
        try:
            import sounddevice
            sd = sounddevice
        except ImportError:
            print("(sounddevice não instalado: o exercício 5 não toca os áudios)")

    for numero in ([args.numero] if args.numero else sorted(EXERCICIOS)):
        if numero == 5:
            exercicio5(args.arquivo)
        else:
            EXERCICIOS[numero]()

    if args.sem_janela:
        os.makedirs(PASTA_FIGURAS, exist_ok=True)
        for nome, fig in figuras:
            caminho = os.path.join(PASTA_FIGURAS, nome.split(" - ")[0].replace("Exercício ", "ex") + ".png")
            fig.savefig(caminho, dpi=110)
            print(caminho)
    elif figuras:
        plt.show()


if __name__ == "__main__":
    main()
