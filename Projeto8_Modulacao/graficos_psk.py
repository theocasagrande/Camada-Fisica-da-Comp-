
# Projeto 8 (parte 2) - gráficos do chat PSK.
#
# Como em graficos.py, cada função desenha numa Figure (ou num eixo) recebido
# como argumento: servem para a janela do /grafico do chat e para salvar PNG.

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

from am import espectro
from graficos import CINZA, CORES, TINTA, TINTA_2, eixo_khz, estilo, legenda, num, reduzir
from psk import BARKER, FS, banda_medida, banda_teorica, simbolos

ENVIADO, RECEBIDO = CORES[0], CORES[1]


def espectro_db(x, fs=FS):
    f, X = reduzir(*espectro(x, fs), pontos=6000)
    return f, 20 * np.log10(np.maximum(X / np.max(X), 1e-9))


def desenhar_espectros(fig, fc, taxa, enviado=None, recebido=None, fs=FS):
    """FFT do sinal emitido e do recebido: inteira (dB) e ampliada em volta da portadora.

    `enviado` e `recebido` são (áudio, (início, fim dos bits)); a banda medida usa
    só o trecho dos bits (sem a abertura de portadora pura).
    """
    ax_todo, ax_zoom = fig.subplots(2, 1, height_ratios=(1, 1.2))
    teorica = banda_teorica(taxa)
    titulos = []
    for nome, cor, item in (("emitido", ENVIADO, enviado), ("recebido", RECEBIDO, recebido)):
        if item is None:
            continue
        audio, (ini, fim) = item
        f, X = espectro_db(audio, fs)
        ax_todo.plot(f, X, color=cor, linewidth=0.8, label=nome)
        bits = audio[ini:fim]
        f, X = reduzir(*espectro(bits, fs), pontos=20000)
        perto = np.abs(f - fc) <= 6 * taxa
        ax_zoom.plot(f[perto], X[perto] / np.max(X[perto]), color=cor, linewidth=1.1, label=nome)
        b90 = banda_medida(bits, fc, fs, 0.9, vizinhanca=10 * taxa)
        titulos.append(f"{nome}: 90% em {num(b90, 0)} Hz")
    ax_todo.axvline(fc, color=TINTA_2, linewidth=0.8, linestyle="--")
    eixo_khz(ax_todo, 0, min(fs / 2, fc + 4000))
    ax_todo.set_ylim(-90, 5)
    estilo(ax_todo, f"FFT inteira (dB): a energia fica em volta da portadora de {num(fc, 0)} Hz" +
                    ("; no recebido, os picos longe dela são ruído da sala" if recebido is not None else ""),
           "Frequência (kHz)", "dB (pico = 0)")
    legenda(ax_todo, loc="upper right")

    ax_zoom.axvspan(fc - taxa, fc + taxa, color=CORES[2], alpha=0.14, linewidth=0,
                    label=f"lóbulo principal: fc ± taxa = {num(teorica, 0)} Hz")
    ax_zoom.axvline(fc, color=TINTA_2, linewidth=0.8, linestyle="--")
    ax_zoom.set_xlim(fc - 6 * taxa, fc + 6 * taxa)
    ax_zoom.set_ylim(0, 1.15)
    estilo(ax_zoom, f"Em volta da portadora (só os bits): banda necessária ≈ 2 × {taxa} = "
                    f"{num(teorica, 0)} Hz  ·  " + "  ·  ".join(titulos) +
                    f"  (energia contada até fc ± {num(10 * taxa, 0)} Hz)",
           "Frequência (Hz)", "|X(f)| (pico = 1 perto de fc)")
    legenda(ax_zoom, loc="upper right")


def desenhar_bits(ax, bits, taxa, n=26):
    """Os primeiros bits do quadro como onda quadrada d(t) = ±1 (sincronia + tamanho)."""
    n = min(n, len(bits))
    d = simbolos(bits[:n])
    t = np.arange(n + 1) / taxa * 1000
    ax.step(t, np.append(d, d[-1]), where="post", color=TINTA, linewidth=1.3)
    for k in range(n):
        ax.text((k + 0.5) / taxa * 1000, 1.25, str(bits[k]), ha="center", fontsize=7.5,
                color=TINTA_2 if k < len(BARKER) else TINTA)
    ax.axvline(len(BARKER) / taxa * 1000, color=TINTA_2, linewidth=0.8, linestyle="--")
    ax.set_ylim(-1.6, 1.6)
    ax.set_yticks([-1, 1], ["−1 (180°)", "+1 (0°)"])
    ax.set_xlim(0, t[-1])
    estilo(ax, f"Primeiros bits: 13 de sincronia + tamanho · 1 bit = {num(1000 / taxa, 0)} ms",
           "Tempo (ms)")


def primeira_inversao(bits):
    for k in range(1, len(bits)):
        if bits[k] != bits[k - 1]:
            return k
    return 1


def desenhar_inversao(ax, bits, fc, taxa, enviado=None, recebido=None, fs=FS, ciclos=6):
    """A onda em volta da primeira troca de bit: a portadora "dá um pulo" de 180°."""
    k = primeira_inversao(bits)
    meia = ciclos / fc
    for nome, cor, item, filtrar in (("emitido", ENVIADO, enviado, False),
                                     ("recebido (filtrado)", RECEBIDO, recebido, True)):
        if item is None:
            continue
        audio, (ini, _) = item
        x = audio
        if filtrar:
            sos = butter(4, [max(20, fc - 4 * taxa), min(fs / 2 - 20, fc + 4 * taxa)],
                         btype="bandpass", fs=fs, output="sos")
            x = sosfiltfilt(sos, audio)
        centro = ini + int(round(k * fs / taxa))
        a, b = max(0, centro - int(meia * fs)), min(len(x), centro + int(meia * fs))
        trecho = x[a:b] / np.max(np.abs(x[a:b]))
        t = (np.arange(a, b) - centro) / fs * 1000
        ax.plot(t, trecho, color=cor, linewidth=1.3, label=nome)
        if not filtrar:
            sem = np.cos(2 * np.pi * fc * np.arange(a, b) / fs) * (1 if bits[k - 1] == 0 else -1)
            ax.plot(t[t > 0], sem[t > 0], color=CINZA, linewidth=1, linestyle="--",
                    label="se o bit não mudasse")
    ax.axvline(0, color=TINTA_2, linewidth=0.8)
    ax.set_ylim(-1.3, 1.6)
    estilo(ax, f"Bit {k - 1} ({bits[k - 1]}) → bit {k} ({bits[k]}): a fase pula 180°",
           "Tempo em volta da troca (ms)", "amplitude")
    legenda(ax, loc="upper right", ncols=3, fontsize=7)


def desenhar_constelacao(ax, simbolos_rx):
    """Cada bit recebido como um ponto (I, Q), depois de corrigida a fase.

    Bit 0 cai perto de +1 e bit 1 perto de −1. Quanto mais espalhada a nuvem,
    mais ruído; o receptor só olha de que lado do eixo vertical o ponto está.
    """
    v = np.asarray(simbolos_rx)
    v = v / np.mean(np.abs(v))
    zero = v.real >= 0
    ax.scatter(v.real[zero], v.imag[zero], s=10, color=CORES[0], alpha=0.7, label="bit 0 (0°)")
    ax.scatter(v.real[~zero], v.imag[~zero], s=10, color=CORES[1], alpha=0.7, label="bit 1 (180°)")
    ax.axvline(0, color=TINTA_2, linewidth=0.8, linestyle="--")
    ax.axhline(0, color=TINTA_2, linewidth=0.5)
    ax.set_xlim(-1.8, 1.8)
    ax.set_ylim(-1.8, 1.8)
    ax.set_aspect("equal")
    estilo(ax, "Constelação recebida", "I (em fase)", "Q (em quadratura)")
    legenda(ax, loc="upper left", fontsize=7)


def desenhar_mensagem(fig, fc, taxa, bits, enviado=None, recebido=None, simbolos_rx=None, fs=FS):
    """O painel do /grafico: espectros, bits, inversão de fase e constelação."""
    topo, baixo = fig.subfigures(2, 1, height_ratios=(1.15, 1))
    desenhar_espectros(topo, fc, taxa, enviado, recebido, fs)
    if simbolos_rx is not None:
        ax_bits, ax_inv, ax_const = baixo.subplots(1, 3, width_ratios=(2.2, 1.6, 1))
        desenhar_constelacao(ax_const, simbolos_rx)
    else:
        ax_bits, ax_inv = baixo.subplots(1, 2, width_ratios=(2.2, 1.6))
    desenhar_bits(ax_bits, bits, taxa)
    desenhar_inversao(ax_inv, bits, fc, taxa, enviado, recebido, fs)


def desenhar_variacao(fig, resultados, rotulo, fs=FS):
    """Espectro (dB e linear) para várias taxas ou várias portadoras.

    `resultados` = [(valor, áudio dos bits, fc, taxa), ...]. Usa a densidade de
    Welch (média de vários trechos de 8192 amostras): a FFT de bits aleatórios é
    muito "serrilhada", e a média mostra a forma sinc² que a teoria prevê.
    """
    ax_db, ax_lin = fig.subplots(2, 1)
    tons = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
    fmin = max(0, min(fc - 2.5 * t for _, _, fc, t in resultados) - 300)
    fmax = min(fs / 2, max(fc + 2.5 * t for _, _, fc, t in resultados) + 300)
    for (valor, x, fc, taxa), cor in zip(resultados, tons):
        f, p = welch(x, fs=fs, nperseg=8192)
        dentro = (f >= fmin) & (f <= fmax)
        ax_db.plot(f[dentro], 10 * np.log10(np.maximum(p[dentro] / p.max(), 1e-12)), color=cor,
                   linewidth=1.2, label=f"{rotulo} {valor}: 90% em {num(banda_medida(x, fc, fs), 0)} Hz")
        ax_lin.plot(f[dentro], np.sqrt(p[dentro] / p.max()), color=cor, linewidth=1.4,
                    label=f"{rotulo} {valor}: zeros em fc ± {taxa} Hz")
    for ax in (ax_db, ax_lin):
        ax.set_xlim(fmin, fmax)
    ax_db.set_ylim(-50, 3)
    estilo(ax_db, "Densidade espectral em dB: lóbulo principal e lóbulos laterais, com zeros a cada "
                  "'taxa' Hz da portadora", ylabel="dB (pico = 0)")
    estilo(ax_lin, "Escala linear: a largura do lóbulo principal é 2 × taxa", "Frequência (Hz)",
           "amplitude (pico = 1)")
    legenda(ax_db, loc="upper right", fontsize=7.5)
    legenda(ax_lin, loc="upper right", fontsize=7.5)
