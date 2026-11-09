
# Projeto 8 (parte 1) - os gráficos do rádio AM.
#
# Cada função recebe uma Figure do matplotlib e desenha nela. A mesma função
# serve para a janela do rádio (FigureCanvasTkAgg) e para salvar os PNGs em
# graficos/ (python radio_am.py --sem-janela).

import numpy as np
from matplotlib.ticker import FuncFormatter

from am import densidade_db, espectro, passa_baixa, passa_faixa, rebater, resposta_db, tempo

CORES = ("#2a78d6", "#eb6834", "#1baf7a")   # estação 1, 2, 3 (azul, laranja, verde-água)
TINTA, TINTA_2, APAGADO, CINZA = "#0b0b0b", "#52514e", "#898781", "#a3a29a"
GRADE, EIXO = "#e1e0d9", "#c3c2b7"


# ------------------------------------------------------------------ formatação

def num(x, casas=1):
    """Número com vírgula decimal: 10.5 -> '10,5'. (+ 0.0 evita escrever '-0,0')"""
    return f"{round(x, casas) + 0.0:.{casas}f}".replace(".", ",")


def khz(f):
    """10500 -> '10,5 kHz'; 9000 -> '9 kHz'."""
    return f"{f / 1000:g}".replace(".", ",") + " kHz"


def faixa_txt(e):
    return f"{f'{e.f_ini / 1000:g}'.replace('.', ',')}–{khz(e.f_fim)}"


def legenda(ax, **kw):
    """Legenda com fundo da cor da superfície: não deixa a curva atrás atrapalhar a leitura."""
    kw.setdefault("fontsize", 7.5)
    ax.legend(frameon=True, facecolor="white", edgecolor="none", framealpha=0.92, **kw)


def estilo(ax, titulo=None, xlabel=None, ylabel=None):
    if titulo:
        ax.set_title(titulo, loc="left", fontsize=9, color=TINTA)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8, color=TINTA_2)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8, color=TINTA_2)
    ax.grid(True, color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TINTA_2, labelsize=7.5)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EIXO)


def eixo_khz(ax, inicio, fim):
    """Eixo x de frequências em kHz."""
    ax.set_xlim(inicio, fim)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:g}".replace(".", ",")))


def sombrear_faixas(ax, estacoes, destaque=None, rotulos=False):
    """Pinta as 3 faixas. A da estação `destaque` fica mais forte."""
    for i, e in enumerate(estacoes):
        alfa = 0.14 if destaque in (None, i) else 0.05
        ax.axvspan(e.f_ini, e.f_fim, color=CORES[i], alpha=alfa, linewidth=0)
        if rotulos:
            ax.text((e.f_ini + e.f_fim) / 2, 0.97, f"Estação {e.numero}\n{faixa_txt(e)}",
                    transform=ax.get_xaxis_transform(), ha="center", va="top",
                    fontsize=7.5, color=TINTA_2)


def reduzir(f, y, pontos=5000):
    """Deixa o espectro com ~`pontos` pontos guardando o MÁXIMO de cada grupo.

    Um áudio de 4 s tem ~90 mil frequências; desenhar todas é lento e a tela
    não tem tantos pixels. Pegar o máximo de cada grupo mantém os picos.
    """
    k = max(1, len(f) // pontos)
    n = len(f) // k * k
    return f[:n].reshape(-1, k).mean(axis=1), y[:n].reshape(-1, k).max(axis=1)


def plot_espectro(ax, x, fs, cor, largura=0.8, rotulo=None, relativo=False, **kw):
    f, X = reduzir(*espectro(x, fs))
    if relativo:
        X = X / np.max(X)
    ax.plot(f, X, color=cor, linewidth=largura, label=rotulo, **kw)


def nyquist(c):
    return c.fs / 2


# ------------------------------------------------------------------ gráficos

def desenhar_originais(fig, c, a):
    eixos = fig.subplots(3, 1, sharex=True)
    for i, (ax, e) in enumerate(zip(eixos, c.estacoes)):
        plot_espectro(ax, c.originais[i], c.fs, CINZA, 1.4, "original", relativo=True)
        plot_espectro(ax, c.mensagens[i], c.fs, CORES[i], 0.9,
                      f"limitado a {khz(e.corte)} (vai para o ar)", relativo=True)
        ax.axvline(e.corte, color=TINTA_2, linestyle="--", linewidth=0.9)
        estilo(ax, f"Estação {e.numero} — original: 99% da energia até {a[i].banda_original:.0f} Hz"
                   f"  ·  transmitido: até {khz(e.corte)}",
               ylabel="|X(f)| (pico = 1)")
        legenda(ax, loc="upper right")
    eixo_khz(eixos[-1], 0, 6000)
    eixos[-1].set_xlabel("Frequência (kHz)", fontsize=8, color=TINTA_2)


def desenhar_tempo(fig, c, a, janela=0.015):
    eixos = fig.subplots(3, 1)
    n = int(janela * c.fs)
    for i, (ax, e) in enumerate(zip(eixos, c.estacoes)):
        m, s = c.mensagens[i], c.modulados[i]
        centro = int(np.argmax(np.abs(m)))
        ini = min(max(0, centro - n // 2), len(m) - n)
        t = tempo(n, c.fs) * 1000 + ini / c.fs * 1000
        ax.plot(t, s[ini:ini + n], color=CORES[i], linewidth=0.6, label="S(t) = m(t)·C(t)")
        ax.plot(t, m[ini:ini + n], color=TINTA, linestyle="--", linewidth=1, label="±m(t) (envoltória)")
        ax.plot(t, -m[ini:ini + n], color=TINTA, linestyle="--", linewidth=1)
        ax.set_xlim(t[0], t[-1])
        ax.set_ylim(-1.15, 1.6)             # folga em cima para a legenda não cobrir a curva
        estilo(ax, f"Estação {e.numero} — portadora de {khz(e.fc)}: {num(e.fc * janela, 0)} ciclos "
                   f"em {num(janela * 1000, 0)} ms; a amplitude segue a mensagem",
               ylabel="amplitude")
        legenda(ax, loc="upper right", ncols=2)
    eixos[-1].set_xlabel("Tempo (ms)", fontsize=8, color=TINTA_2)


def desenhar_modulados(fig, c, a):
    eixos = fig.subplots(3, 1, sharex=True)
    for i, (ax, e) in enumerate(zip(eixos, c.estacoes)):
        sombrear_faixas(ax, c.estacoes, destaque=i)
        plot_espectro(ax, c.modulados[i], c.fs, CORES[i])
        estilo(ax, f"Estação {e.numero} — portadora {khz(e.fc)}, ocupa "
                   f"{khz(e.fc - e.corte)} a {khz(e.fc + e.corte)}  ·  energia fora de "
                   f"{faixa_txt(e)}: {num(a[i].fora_db, 0)} dB",
               ylabel="|S(f)|")
    eixo_khz(eixos[-1], 0, nyquist(c))
    eixos[-1].set_xlabel("Frequência (kHz)", fontsize=8, color=TINTA_2)


def desenhar_verificacao(fig, c, a):
    ax = fig.subplots()
    sombrear_faixas(ax, c.estacoes, rotulos=True)
    for i, e in enumerate(c.estacoes):
        f, p = densidade_db(c.modulados[i], c.fs)
        fora = (f < e.f_ini) | (f >= e.f_fim)
        ax.plot(f, p, color=CORES[i], linewidth=1.1,
                label=f"Estação {e.numero} · fora da faixa ≤ {num(np.max(p[fora]), 0)} dB")
    for borda in sorted({b for e in c.estacoes for b in (e.f_ini, e.f_fim)}):
        ax.axvline(borda, color=TINTA_2, linewidth=0.8, linestyle="--")
    ax.set_ylim(-140, 25)
    eixo_khz(ax, 6000, 21000)
    estilo(ax, "Verificação em dB: cada sinal modulado fica dentro da sua faixa "
               "(o resto está muito abaixo do pico, 0 dB)",
           "Frequência (kHz)", "densidade espectral (dB, pico = 0)")
    legenda(ax, fontsize=8, loc="lower right")


def desenhar_soma(fig, c, a):
    ax_t, ax_f = fig.subplots(2, 1, height_ratios=(1, 2))
    t = tempo(len(c.soma), c.fs)
    ax_t.plot(t, c.soma, color=TINTA_2, linewidth=0.3)
    ax_t.set_xlim(0, t[-1])
    estilo(ax_t, "Soma dos 3 sinais modulados no tempo: o que existe no meio físico",
           "Tempo (s)", "amplitude")
    sombrear_faixas(ax_f, c.estacoes, rotulos=True)
    f, X = reduzir(*espectro(c.soma, c.fs))
    ax_f.plot(f, X, color=TINTA_2, linewidth=0.6)
    for i, e in enumerate(c.estacoes):                 # o trecho de cada faixa na cor da estação
        dentro = (f >= e.f_ini) & (f <= e.f_fim)
        ax_f.plot(f[dentro], X[dentro], color=CORES[i], linewidth=0.8)
    ax_f.set_ylim(0, np.max(X) * 1.35)
    eixo_khz(ax_f, 0, nyquist(c))
    estilo(ax_f, "FFT da soma: as 3 estações lado a lado, sem se sobrepor",
           "Frequência (kHz)", "|X(f)|")


def desenhar_filtros(fig, c, a):
    ax_pf, ax_pb = fig.subplots(1, 2, width_ratios=(3, 2))
    freqs = np.linspace(6000, 21000, 3000)
    sombrear_faixas(ax_pf, c.estacoes)
    for i, e in enumerate(c.estacoes):
        ax_pf.plot(freqs, resposta_db(passa_faixa(e.f_ini, e.f_fim, c.fs), freqs, c.fs),
                   color=CORES[i], linewidth=1.3, label=f"Estação {e.numero}: {faixa_txt(e)}")
    ax_pf.set_ylim(-120, 8)
    eixo_khz(ax_pf, 6000, 21000)
    estilo(ax_pf, "Passa-faixas do receptor (Butterworth ordem 20, ida e volta)",
           "Frequência (kHz)", "ganho (dB)")
    legenda(ax_pf, loc="lower center")

    e = c.estacoes[0]
    freqs = np.linspace(10, 4000, 2000)
    ax_pb.plot(freqs, resposta_db(passa_baixa(e.corte, c.fs), freqs, c.fs), color=TINTA,
               linewidth=1.3, label=f"emissor: corta a mensagem em {khz(e.corte)}")
    ax_pb.plot(freqs, resposta_db(passa_baixa(e.meia_largura, c.fs), freqs, c.fs), color=TINTA_2,
               linewidth=1.3, linestyle="--", label=f"receptor: após × portadora, {khz(e.meia_largura)}")
    ax_pb.set_ylim(-120, 8)
    eixo_khz(ax_pb, 0, 4000)
    estilo(ax_pb, "Passa-baixas (Butterworth ordem 12, ida e volta)", "Frequência (kHz)")
    legenda(ax_pb, loc="lower left")


def desenhar_extraidos(fig, c, a):
    eixos = fig.subplots(3, 1, sharex=True)
    for i, (ax, e) in enumerate(zip(eixos, c.estacoes)):
        sombrear_faixas(ax, c.estacoes, destaque=i)
        plot_espectro(ax, c.soma, c.fs, CINZA, 0.6, "soma (entrada do receptor)")
        plot_espectro(ax, c.extraidos[i], c.fs, CORES[i], 0.8, "depois do passa-faixa")
        estilo(ax, f"Estação {e.numero} — passa-faixa {faixa_txt(e)}: o que passou das outras "
                   f"estações = {num(a[i].vazamento_db, 0)} dB (em relação à estação {e.numero})",
               ylabel="|X(f)|")
        legenda(ax, loc="upper left")
    eixo_khz(eixos[-1], 0, nyquist(c))
    eixos[-1].set_xlabel("Frequência (kHz)", fontsize=8, color=TINTA_2)


def desenhar_demodulacao(fig, c, a):
    eixos = fig.subplots(3, 2, width_ratios=(3, 2))
    for i, e in enumerate(c.estacoes):
        ax_p, ax_d = eixos[i]
        plot_espectro(ax_p, c.produtos[i], c.fs, CORES[i])
        ax_p.axvspan(0, e.meia_largura, color=TINTA, alpha=0.06, linewidth=0)
        dobro = 2 * e.fc
        onde = rebater(dobro, c.fs)
        texto = (f"cópia em 2fc = {khz(dobro)}" if dobro <= nyquist(c) else
                 f"cópia em 2fc = {khz(dobro)}\n> Nyquist: aparece em {khz(onde)}")
        ax_p.text(e.meia_largura + 300, 0.93, "informação", transform=ax_p.get_xaxis_transform(),
                  fontsize=7.5, color=TINTA_2, va="top")
        ax_p.text(onde, 0.93, texto, transform=ax_p.get_xaxis_transform(), fontsize=7.5,
                  color=TINTA_2, va="top", ha="right" if onde > 15000 else "center")
        eixo_khz(ax_p, 0, nyquist(c))
        estilo(ax_p, f"Estação {e.numero} — extraído × portadora ({khz(e.fc)})", ylabel="|X(f)|")

        plot_espectro(ax_d, c.mensagens[i], c.fs, CINZA, 2.4, "transmitido", relativo=True)
        plot_espectro(ax_d, c.demodulados[i], c.fs, CORES[i], 0.9, "demodulado", relativo=True)
        eixo_khz(ax_d, 0, 3000)
        estilo(ax_d, f"após o passa-baixa: corr. {num(a[i].correlacao, 5)} · SNR {num(a[i].snr_db, 0)} dB")
        legenda(ax_d, loc="upper right")
    for ax in eixos[-1]:
        ax.set_xlabel("Frequência (kHz)", fontsize=8, color=TINTA_2)


# (chave, rótulo do botão, função) na ordem da apresentação
GRAFICOS = (
    ("originais", "1 Originais", desenhar_originais),
    ("tempo", "2 Tempo", desenhar_tempo),
    ("modulados", "3 Modulados", desenhar_modulados),
    ("verificacao", "4 Faixas (dB)", desenhar_verificacao),
    ("soma", "5 Soma", desenhar_soma),
    ("filtros", "6 Filtros", desenhar_filtros),
    ("extraidos", "7 Extraídos", desenhar_extraidos),
    ("demodulacao", "8 Demodulação", desenhar_demodulacao),
)


def desenhar(fig, chave, cadeia, analise):
    fig.clear()
    fig.set_layout_engine("constrained")
    dict((k, f) for k, _, f in GRAFICOS)[chave](fig, cadeia, analise)
