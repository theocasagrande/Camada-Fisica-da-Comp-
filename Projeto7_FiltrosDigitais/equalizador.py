
# Projeto 7 - Equalizador digital de áudio de 12 bandas
#
# O usuário escolhe o ganho de cada banda (-10 a +10 dB) nos sliders. Com isso o
# programa monta uma função de transferência peaking EQ por banda, aplica os 12
# filtros um a um ao áudio e toca o original seguido do equalizado. Em cima fica
# o diagrama de Bode do equalizador completo (atualiza enquanto o slider mexe);
# embaixo, o espectro do áudio antes e depois.
#
#   python equalizador.py                          -> abre audios/teste.wav
#   python equalizador.py --arquivo minha_voz.wav  -> abre outro .wav
#
# Os áudios de teste saem de "python gerar_audio_teste.py".

import argparse
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from scipy.signal import welch

from filtros import (BANDAS, FS, GANHO_MAX, GANHO_MIN, aplicar_filtros, em_db,
                     ler_wav, projetar_equalizador, resposta_total, salvar_wav)

try:
    import sounddevice as sd
except ImportError:         # sem placa de som o resto ainda funciona
    sd = None

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_AUDIOS = os.path.join(PASTA, "audios")
AUDIO_PADRAO = os.path.join(PASTA_AUDIOS, "teste.wav")
CAMINHO_GRAVACAO = os.path.join(PASTA_AUDIOS, "gravacao.wav")

MAX_SEGUNDOS = 15           # áudios maiores são cortados: o enunciado pede um áudio curto
DURACAO_GRAVACAO = 5        # segundos gravados pelo microfone
PAUSA = 0.6                 # segundos de silêncio entre o original e o equalizado
ESPERA_PROCESSAR = 250      # ms parado no slider antes de refiltrar o áudio
TETO = 0.99                 # maior amplitude enviada para a placa de som

AZUL, LARANJA, CINZA, PRETO, GRADE = "#2a78d6", "#eb6834", "#a3a29a", "#0b0b0b", "#e1e0d9"

# Ajustes prontos. "Figura do enunciado" imita a posição dos sliders da figura do PDF.
PRESETS = {
    "Plano (tudo 0 dB)":   [0] * 12,
    "Figura do enunciado": [4, 3, 2, 1, 0, -1, -1, 0, 1, 2, 3, 4],
    "Reforço de graves":   [8, 8, 7, 6, 3, 0, 0, 0, 0, 0, 0, 0],
    "Reforço de agudos":   [0, 0, 0, 0, 0, 0, 0, 2, 5, 7, 8, 8],
    "Só médios (voz)":     [-10, -10, -10, -8, -3, 3, 5, 5, 3, -3, -10, -10],
    "Telefone":            [-10, -10, -10, -10, -6, 0, 2, 2, 0, -10, -10, -10],
}


def rotulo(f):
    return f"{f // 1000} kHz" if f >= 1000 else f"{f} Hz"


def mono(audio):
    return audio.mean(axis=1) if audio.ndim > 1 else audio


def eixo_de_frequencias(ax, inicio, fs):
    """Eixo x em escala log, com uma marca em cada banda que existe para esse fs."""
    bandas = [f for f in BANDAS if f < fs / 2]
    # 16 e 20 kHz ficam colados no eixo log: o rótulo da segunda desce uma linha
    rotulos = [("\n" if i and f / bandas[i - 1] < 1.5 else "") + rotulo(f)
               for i, f in enumerate(bandas)]
    ax.set_xticks(bandas, rotulos, fontsize=8)
    ax.minorticks_off()
    ax.set_xlim(inicio, fs / 2)     # depois de set_xticks, que pode alargar o eixo
    ax.grid(True, color=GRADE, linewidth=0.8)


class Equalizador:

    def __init__(self, raiz):
        self.raiz = raiz
        self.audio = None           # original em float, (N,) ou (N, canais)
        self.equalizado = None      # saída dos filtros para os ganhos atuais
        self.fs = FS
        self.nome = ""
        self.filtros = []
        self._agendado = None       # refiltragem esperando o slider parar
        self._avisos = []           # mudanças de status programadas durante a reprodução

        raiz.title("Projeto 7 - Equalizador de 12 bandas")
        # cabe em notebook com escala de 125-150% (sobra espaço para a barra de
        # tarefas): os gráficos, últimos no pack, encolhem para caber
        raiz.geometry(f"960x{min(820, raiz.winfo_screenheight() - 120)}+40+10")
        raiz.minsize(900, 600)
        self._montar_sliders()
        self._montar_botoes()
        self._montar_graficos()
        self.atualizar_bode()

    # ------------------------------------------------------------ interface

    def _montar_sliders(self):
        topo = ttk.Frame(self.raiz, padding=(8, 8, 8, 0))
        topo.pack(side=tk.TOP, fill=tk.X)

        quadro = ttk.LabelFrame(topo, text="Ganho de cada banda (dB)", padding=4)
        quadro.pack(side=tk.LEFT)
        self.ganhos = []
        for i, f in enumerate(BANDAS):
            var = tk.IntVar(value=0)
            tk.Scale(quadro, from_=GANHO_MAX, to=GANHO_MIN, resolution=1,
                     orient=tk.VERTICAL, length=150, width=14, variable=var,
                     command=self._ganho_mudou).grid(row=0, column=i, padx=1)
            ttk.Label(quadro, text=rotulo(f)).grid(row=1, column=i)
            self.ganhos.append(var)

        presets = ttk.LabelFrame(topo, text="Ajustes prontos", padding=4)
        presets.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        for nome, valores in PRESETS.items():
            ttk.Button(presets, text=nome, width=20,
                       command=lambda v=valores: self.aplicar_preset(v)).pack(fill=tk.X, pady=1)

    def _montar_botoes(self):
        barra = ttk.Frame(self.raiz, padding=(8, 6))
        barra.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(barra, text="Abrir .wav…", command=self.abrir).pack(side=tk.LEFT)
        self.botao_gravar = ttk.Button(barra, text=f"Gravar {DURACAO_GRAVACAO} s", command=self.gravar)
        self.botao_gravar.pack(side=tk.LEFT, padx=(4, 14))
        ttk.Button(barra, text="▶ Original → Equalizado",
                   command=lambda: self.tocar("ambos")).pack(side=tk.LEFT)
        ttk.Button(barra, text="▶ Original", command=lambda: self.tocar("original")).pack(side=tk.LEFT, padx=4)
        ttk.Button(barra, text="▶ Equalizado", command=lambda: self.tocar("equalizado")).pack(side=tk.LEFT)
        ttk.Button(barra, text="■ Parar", command=self.parar).pack(side=tk.LEFT, padx=(4, 14))
        ttk.Button(barra, text="Salvar…", command=self.salvar).pack(side=tk.LEFT)
        ttk.Button(barra, text="Imprimir G(z)", command=self.imprimir_funcoes).pack(side=tk.LEFT, padx=4)

        self.texto_arquivo = tk.StringVar(value="Nenhum áudio aberto")
        self.texto_status = tk.StringVar(value="")
        info = ttk.Frame(self.raiz, padding=(8, 0))
        info.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(info, textvariable=self.texto_arquivo).pack(side=tk.LEFT)
        ttk.Label(info, textvariable=self.texto_status, foreground=AZUL).pack(side=tk.RIGHT)

    def _montar_graficos(self):
        self.figura = Figure(figsize=(9.5, 5.4), dpi=96, layout="constrained")
        self.ax_bode, self.ax_espectro = self.figura.subplots(2, 1)
        self.canvas = FigureCanvasTkAgg(self.figura, master=self.raiz)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def status(self, texto):
        self.texto_status.set(texto)

    # ------------------------------------------------------------ filtros

    def ler_ganhos(self):
        return [v.get() for v in self.ganhos]

    def _ganho_mudou(self, _valor=None):
        """Slider mexeu: Bode na hora, refiltragem do áudio quando o slider parar."""
        self.atualizar_bode()
        self.equalizado = None
        if self._agendado is not None:
            self.raiz.after_cancel(self._agendado)
        self._agendado = self.raiz.after(ESPERA_PROCESSAR, self.processar)

    def aplicar_preset(self, valores):
        for var, v in zip(self.ganhos, valores):
            var.set(v)
        self._ganho_mudou()

    def processar(self):
        """Obtém as G(z) dos ganhos atuais e aplica os filtros um a um ao áudio."""
        if self._agendado is not None:
            self.raiz.after_cancel(self._agendado)
            self._agendado = None
        if self.audio is None:
            return
        self.filtros = projetar_equalizador(self.ler_ganhos(), self.fs)
        self.equalizado = aplicar_filtros(self.audio, self.filtros)
        self.atualizar_espectro()

    def atualizar_bode(self):
        self.filtros = projetar_equalizador(self.ler_ganhos(), self.fs)
        freqs = np.logspace(np.log10(10), np.log10(self.fs / 2), 1500, endpoint=False)
        ax = self.ax_bode
        ax.clear()
        for i, f in enumerate(self.filtros):
            ax.semilogx(freqs, em_db(resposta_total([f], freqs, self.fs)), color=CINZA,
                        linewidth=0.8, label="cada banda" if i == 0 else None)
        total = em_db(resposta_total(self.filtros, freqs, self.fs))
        ax.semilogx(freqs, total, color=AZUL, linewidth=2.2, label="equalizador completo")
        ax.plot([f.f0 for f in self.filtros], [f.ganho for f in self.filtros], "o",
                color=LARANJA, markersize=7, label="ganho escolhido no slider")
        ax.axhline(0, color=PRETO, linewidth=0.6)
        # título no alto e legenda numa linha entre ele e o gráfico: dentro do
        # gráfico as curvas podem passar por baixo da legenda
        ax.set_title("Bode do equalizador completo:  G(z) = G₁(z)·G₂(z)·…·G₁₂(z)", loc="left", pad=20)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1), ncol=3, fontsize=8, frameon=False,
                  borderaxespad=0.2)
        ax.set_ylabel("Ganho (dB)")
        ax.set_ylim(min(-16, total.min() - 1), max(16, total.max() + 1))
        ax.set_yticks(range(-15, 16, 5))
        eixo_de_frequencias(ax, freqs[0], self.fs)
        self.canvas.draw_idle()

    def atualizar_espectro(self):
        ax = self.ax_espectro
        ax.clear()
        ax.set_title("Espectro do áudio (antes e depois dos filtros)", loc="left", pad=20)
        ax.set_xlabel("Frequência (Hz)")
        ax.set_ylabel("dB (0 = pico do original)")
        if self.audio is not None:
            n = min(8192, len(self.audio))
            f, p_orig = welch(mono(self.audio), self.fs, nperseg=n)
            ref = max(p_orig[1:].max(), 1e-30)      # áudio mudo não divide por zero
            ax.semilogx(f[1:], 10 * np.log10(p_orig[1:] / ref + 1e-15), color=CINZA,
                        linewidth=1.2, label="original")
            if self.equalizado is not None:
                _, p_eq = welch(mono(self.equalizado), self.fs, nperseg=n)
                ax.semilogx(f[1:], 10 * np.log10(p_eq[1:] / ref + 1e-15), color=AZUL,
                            linewidth=1.2, label="equalizado")
            ax.set_ylim(-90, 15)
            eixo_de_frequencias(ax, 20, self.fs)
            ax.legend(loc="lower left", bbox_to_anchor=(0, 1), ncol=2, fontsize=8, frameon=False,
                      borderaxespad=0.2)
        self.canvas.draw_idle()

    def imprimir_funcoes(self):
        filtros = projetar_equalizador(self.ler_ganhos(), self.fs)
        print(f"\nFunções de transferência do equalizador (fs = {self.fs} Hz)")
        print("Cada banda: G(z) = (b0 z² + b1 z + b2) / (z² + a1 z + a2)\n")
        print(f"{'banda':>7} {'ganho':>6} {'Q':>5} {'b0':>12} {'b1':>12} {'b2':>12} {'a1':>12} {'a2':>12}")
        for f in filtros:
            b0, b1, b2 = f.b
            print(f"{rotulo(f.f0):>7} {f.ganho:+4d}dB {f.Q:5.2f} {b0:12.8f} {b1:12.8f} "
                  f"{b2:12.8f} {f.a[1]:12.8f} {f.a[2]:12.8f}")
        print(f"\nEqualizador completo: G(z) = G1(z)·G2(z)·...·G{len(filtros)}(z) "
              f"(ordem {2 * len(filtros)}), aplicado em cascata, um filtro de cada vez.")

    # ------------------------------------------------------------ áudio

    def carregar(self, caminho):
        try:
            audio, fs = ler_wav(caminho)
        except Exception as erro:
            messagebox.showerror("Erro ao abrir", f"Não consegui ler {caminho}:\n{erro}")
            return
        aviso = ""
        if len(audio) > MAX_SEGUNDOS * fs:
            audio = audio[:MAX_SEGUNDOS * fs]
            aviso = f"  (usando só os primeiros {MAX_SEGUNDOS} s)"
        self.audio, self.fs, self.nome = audio, fs, os.path.basename(caminho)
        canais = "estéreo" if audio.ndim > 1 else "mono"
        self.texto_arquivo.set(f"Áudio: {self.nome} - {len(audio) / fs:.1f} s, {fs} Hz, {canais}{aviso}")
        ignoradas = [rotulo(f) for f in BANDAS if f >= fs / 2]
        self.status(f"Bandas acima de {fs // 2} Hz ignoradas: {', '.join(ignoradas)}" if ignoradas else "")
        self.atualizar_bode()
        self.processar()

    def abrir(self):
        caminho = filedialog.askopenfilename(initialdir=PASTA_AUDIOS, title="Abrir áudio",
                                             filetypes=[("Áudio WAV", "*.wav")])
        if caminho:
            self.carregar(caminho)

    def _tem_placa(self):
        if sd is None:
            messagebox.showerror("Sem sounddevice", "Instale com:  pip install sounddevice")
            return False
        return True

    def gravar(self):
        if not self._tem_placa():
            return
        self.parar()
        try:
            self._gravacao = sd.rec(int(DURACAO_GRAVACAO * FS), samplerate=FS, channels=1)
        except Exception as erro:
            messagebox.showerror("Erro no microfone", str(erro))
            return
        self.botao_gravar.state(["disabled"])
        self.status(f"Gravando {DURACAO_GRAVACAO} s… fale ou toque uma música perto do microfone")
        self.raiz.after(DURACAO_GRAVACAO * 1000 + 300, self._fim_gravacao)

    def _fim_gravacao(self):
        sd.wait()
        self.botao_gravar.state(["!disabled"])
        audio = self._gravacao[:, 0] - np.mean(self._gravacao[:, 0])   # tira o nível DC do microfone
        pico = np.max(np.abs(audio))
        if pico < 1e-4:
            messagebox.showwarning("Gravação muda", "O microfone não captou som.")
            return
        # pico em -6 dBFS: microfone baixo fica audível e sobra folga para reforçar bandas
        os.makedirs(PASTA_AUDIOS, exist_ok=True)
        salvar_wav(CAMINHO_GRAVACAO, audio * 0.5 / pico, FS)
        self.carregar(CAMINHO_GRAVACAO)
        self.status(f"Gravação salva em audios/{os.path.basename(CAMINHO_GRAVACAO)}")

    def _volume_comum(self):
        """Original e equalizado multiplicados pelo MESMO fator.

        Reforçar bandas pode passar de 1, e a placa de som corta tudo acima disso
        (clipping), o que distorce o som. Se precisar, abaixamos os dois juntos:
        cabe na faixa e a diferença de volume entre eles continua a real.
        """
        if self.equalizado is None:
            self.processar()
        pico = max(np.max(np.abs(self.audio)), np.max(np.abs(self.equalizado)))
        fator = min(1.0, TETO / pico) if pico > 0 else 1.0
        return self.audio * fator, self.equalizado * fator, fator

    def tocar(self, qual):
        if self.audio is None or not self._tem_placa():
            return
        self.parar()
        original, equalizado, fator = self._volume_comum()
        if qual == "original":
            sinal, texto = original, "Tocando: ORIGINAL"
        elif qual == "equalizado":
            sinal, texto = equalizado, "Tocando: EQUALIZADO"
        else:
            silencio = np.zeros((int(PAUSA * self.fs),) + original.shape[1:])
            sinal = np.concatenate([original, silencio, equalizado])
            texto = "Tocando: 1º ORIGINAL"
            troca = int(1000 * (len(original) + len(silencio)) / self.fs)
            self._avisos.append(self.raiz.after(troca, self.status, "Tocando: 2º EQUALIZADO"))
        if fator < 1:
            texto += f"  (volume dos dois reduzido em {-20 * np.log10(fator):.1f} dB para não saturar)"
        try:
            sd.play(sinal, self.fs)
        except Exception as erro:
            messagebox.showerror("Erro na placa de som", str(erro))
            return
        self.status(texto)
        fim = int(1000 * len(sinal) / self.fs) + 100
        self._avisos.append(self.raiz.after(fim, self.status, "Fim da reprodução"))

    def parar(self):
        for aviso in self._avisos:
            self.raiz.after_cancel(aviso)
        self._avisos = []
        if sd is not None:
            sd.stop()
        self.status("")

    def salvar(self):
        if self.audio is None:
            return
        _, equalizado, _ = self._volume_comum()
        base = os.path.splitext(self.nome)[0]
        caminho = filedialog.asksaveasfilename(initialdir=PASTA_AUDIOS, defaultextension=".wav",
                                               initialfile=f"{base}_equalizado.wav",
                                               filetypes=[("Áudio WAV", "*.wav")])
        if caminho:
            salvar_wav(caminho, equalizado, self.fs)
            self.status(f"Salvo em {caminho}")


def main():
    parser = argparse.ArgumentParser(description="Equalizador de áudio de 12 bandas")
    parser.add_argument("--arquivo", default=AUDIO_PADRAO, help="áudio .wav a equalizar")
    args = parser.parse_args()

    raiz = tk.Tk()
    app = Equalizador(raiz)
    if os.path.exists(args.arquivo):
        app.carregar(args.arquivo)
    else:
        app.status(f"{args.arquivo} não existe: rode gerar_audio_teste.py ou use Abrir/Gravar")
    raiz.protocol("WM_DELETE_WINDOW", lambda: (app.parar(), raiz.destroy()))
    raiz.mainloop()


if __name__ == "__main__":
    main()
