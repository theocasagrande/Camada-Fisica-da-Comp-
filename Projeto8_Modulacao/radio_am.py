
# Projeto 8 (parte 1) - Rádio AM com 3 estações
#
# Emissor e receptor no mesmo programa (o enunciado permite):
#
#   EMISSOR   audios/originais/estacao_N.wav ─► passa-baixa ─► × portadora ─► audios/modulados/
#   CANAL     soma dos 3 modulados ─► audios/soma.wav
#   RECEPTOR  passa-faixa ─► audios/extraidos/ ─► × portadora ─► passa-baixa ─► audios/demodulados/
#
#   python radio_am.py                -> janela: gravar, tocar cada etapa e ver os gráficos
#   python radio_am.py --sem-janela   -> só o relatório no terminal + wavs + PNGs em graficos/
#
# Os áudios de teste saem de "python gerar_audios_teste.py"; o botão "● Gravar"
# troca o áudio de uma estação por uma gravação do microfone.

import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from am import (ESTACOES, FS, analisar, carregar_audio, normalizar, salvar_wav, simular,
                suavizar_bordas)
from graficos import CORES, GRAFICOS, desenhar, faixa_txt, khz, num

try:
    import sounddevice as sd
except ImportError:         # sem placa de som o resto ainda funciona
    sd = None

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_AUDIOS = os.path.join(PASTA, "audios")
PASTA_GRAFICOS = os.path.join(PASTA, "graficos")

DURACAO_GRAVACAO = 4        # segundos gravados pelo microfone
PAUSA = 0.5                 # s de silêncio entre áudios tocados em sequência
PICO = 0.9                  # volume dos áudios tocados e salvos (pico)

ETAPAS = ("originais", "modulados", "extraidos", "demodulados")


def caminho_original(numero):
    return os.path.join(PASTA_AUDIOS, "originais", f"estacao_{numero}.wav")


def carregar_originais():
    faltando = [caminho_original(e.numero) for e in ESTACOES
                if not os.path.exists(caminho_original(e.numero))]
    if faltando:
        raise FileNotFoundError("Faltam os áudios originais:\n  " + "\n  ".join(faltando) +
                                "\nRode antes:  python gerar_audios_teste.py")
    return [carregar_audio(caminho_original(e.numero)) for e in ESTACOES]


def sinais_da_etapa(cadeia, etapa):
    return {"originais": cadeia.originais, "modulados": cadeia.modulados,
            "extraidos": cadeia.extraidos, "demodulados": cadeia.demodulados}[etapa]


# ------------------------------------------------------------------ relatório

def relatorio(c, a):
    """Imprime no terminal os números de cada etapa (para mostrar na apresentação)."""
    linha = "-" * 78
    print(f"\n{linha}\nEMISSOR  (fs = {c.fs} Hz, {len(c.soma)} amostras = {num(len(c.soma) / c.fs, 2)} s)")
    for e, r in zip(c.estacoes, a):
        print(f"  Estação {e.numero}: faixa {e.f_ini}-{e.f_fim} Hz | portadora {e.fc:.0f} Hz | "
              f"mensagem: 99% da energia até {r.banda_original:.0f} Hz -> cortada em {e.corte:.0f} Hz")
        print(f"             modulado ocupa {e.fc - e.corte:.0f} a {e.fc + e.corte:.0f} Hz "
              f"(largura 2 x {e.corte:.0f} = {2 * e.corte:.0f} Hz)")

    print(f"\nENERGIA DE CADA SINAL MODULADO EM CADA FAIXA (dB; 0 dB = toda a energia)")
    print("              " + "".join(f"{f'faixa {e.numero}':>12}" for e in c.estacoes) + f"{'fora da sua':>14}")
    for e, r in zip(c.estacoes, a):
        print(f"  Estação {e.numero}  " + "".join(f"{num(v):>12}" for v in r.energia_faixas_db) +
              f"{num(r.fora_db):>14}")
    pior = max(r.fora_db for r in a)
    print(f"  -> {'NENHUM' if pior < -40 else 'ALGUM'} sinal invadiu outra faixa "
          f"(pior caso: {num(pior)} dB fora da própria faixa)")

    print(f"\nCANAL: soma dos 3 modulados, pico {num(np.max(np.abs(c.soma)), 3)}")

    print("\nRECEPTOR (passa-faixa -> x portadora -> passa-baixa -> x 2)")
    for e, r in zip(c.estacoes, a):
        print(f"  Estação {e.numero}: o passa-faixa deixa passar {num(r.vazamento_db)} dB das outras "
              f"estações; depois do passa-baixa sobram {num(r.interferencia_db)} dB")
        print(f"             demodulado x transmitido: correlação {num(r.correlacao, 6)} | "
              f"SNR {num(r.snr_db)} dB")
    print(f"  (correlação com o original SEM o passa-baixa do emissor: "
          + ", ".join(num(r.correlacao_original, 3) for r in a)
          + " - o que falta é o que foi cortado acima de "
          + f"{khz(c.estacoes[0].corte)} para caber na faixa)")
    print(linha)


def salvar_audios(c):
    """Salva cada etapa em audios/<etapa>/estacao_N.wav e a soma em audios/soma.wav.

    Todos são normalizados para pico 0,9 (só para ouvir: a soma real chega a ~2).
    """
    for etapa in ETAPAS[1:]:
        os.makedirs(os.path.join(PASTA_AUDIOS, etapa), exist_ok=True)
        for e, x in zip(c.estacoes, sinais_da_etapa(c, etapa)):
            salvar_wav(os.path.join(PASTA_AUDIOS, etapa, f"estacao_{e.numero}.wav"),
                       normalizar(x, PICO), c.fs)
    salvar_wav(os.path.join(PASTA_AUDIOS, "soma.wav"), normalizar(c.soma, PICO), c.fs)


def salvar_graficos(c, a, pasta=PASTA_GRAFICOS):
    os.makedirs(pasta, exist_ok=True)
    fig = Figure(figsize=(12, 7.5))
    caminhos = []
    for i, (chave, _, _) in enumerate(GRAFICOS, start=1):
        desenhar(fig, chave, c, a)
        caminho = os.path.join(pasta, f"{i}_{chave}.png")
        fig.savefig(caminho, dpi=110)
        caminhos.append(caminho)
    return caminhos


def processar():
    cadeia = simular(carregar_originais())
    analise = analisar(cadeia)
    relatorio(cadeia, analise)
    salvar_audios(cadeia)
    return cadeia, analise


# ------------------------------------------------------------------ janela

class Radio:

    def __init__(self, raiz):
        self.raiz = raiz
        self.cadeia = None
        self.analise = None
        self._avisos = []           # mudanças de status programadas durante a reprodução
        self.grafico = tk.StringVar(value=GRAFICOS[0][0])

        raiz.title("Projeto 8 - Rádio AM: 3 estações")
        largura = min(1180, raiz.winfo_screenwidth() - 40)
        raiz.geometry(f"{largura}x{min(900, raiz.winfo_screenheight() - 100)}+20+10")
        raiz.minsize(min(1000, largura), 600)
        self._montar_estacoes()
        self._montar_seletor()
        self._montar_graficos()
        raiz.update_idletasks()             # alarga a janela se os botões pedirem mais espaço
        if raiz.winfo_reqwidth() > largura:
            raiz.geometry(f"{min(raiz.winfo_reqwidth() + 20, raiz.winfo_screenwidth() - 40)}x"
                          f"{min(900, raiz.winfo_screenheight() - 100)}")
        self.processar()

    def _montar_estacoes(self):
        quadro = ttk.LabelFrame(self.raiz, text="Estações (emissor ─► meio físico ─► receptor)",
                                padding=6)
        quadro.pack(fill=tk.X, padx=8, pady=(8, 0))
        self.botoes_gravar = []
        for i, e in enumerate(ESTACOES):
            tk.Label(quadro, text="■", fg=CORES[i], font=("Segoe UI", 12)).grid(row=i, column=0)
            ttk.Label(quadro, text=f"Estação {e.numero}   {faixa_txt(e)}   portadora {khz(e.fc)}"
                      ).grid(row=i, column=1, sticky="w", padx=(0, 8))
            gravar = ttk.Button(quadro, text=f"● Gravar {DURACAO_GRAVACAO} s",
                                command=lambda n=e.numero: self.gravar(n))
            gravar.grid(row=i, column=2, padx=2, pady=1)
            self.botoes_gravar.append(gravar)
            ttk.Button(quadro, text="Abrir .wav…",
                       command=lambda n=e.numero: self.abrir(n)).grid(row=i, column=3, padx=(2, 14))
            for j, (etapa, texto) in enumerate((("originais", "▶ Original"), ("modulados", "▶ Modulado"),
                                                ("extraidos", "▶ Extraído"), ("demodulados", "▶ Demodulado"))):
                ttk.Button(quadro, text=texto, command=lambda et=etapa, k=i: self.tocar_um(et, k)
                           ).grid(row=i, column=4 + j, padx=2, pady=1)

        barra = ttk.Frame(quadro)
        barra.grid(row=3, column=0, columnspan=8, sticky="w", pady=(8, 0))
        ttk.Button(barra, text="▶ Os 3 originais",
                   command=lambda: self.tocar_etapa("originais")).pack(side=tk.LEFT)
        ttk.Button(barra, text="▶ Soma (meio físico)", command=self.tocar_soma).pack(side=tk.LEFT, padx=4)
        ttk.Button(barra, text="▶ Os 3 demodulados",
                   command=lambda: self.tocar_etapa("demodulados")).pack(side=tk.LEFT)
        ttk.Button(barra, text="■ Parar", command=self.parar).pack(side=tk.LEFT, padx=(4, 16))
        ttk.Button(barra, text="Salvar gráficos (PNG)", command=self.salvar_pngs).pack(side=tk.LEFT)

    def _montar_seletor(self):
        barra = ttk.Frame(self.raiz, padding=(8, 6, 8, 0))
        barra.pack(fill=tk.X)
        ttk.Label(barra, text="Gráfico:").pack(side=tk.LEFT, padx=(0, 6))
        for chave, rotulo, _ in GRAFICOS:
            ttk.Radiobutton(barra, text=rotulo, value=chave, variable=self.grafico,
                            style="Toolbutton", command=self.atualizar_grafico).pack(side=tk.LEFT, padx=1)

    def _montar_graficos(self):
        # status numa linha própria, embaixo: texto longo não pode alargar a grade dos botões
        self.texto_status = tk.StringVar()
        ttk.Label(self.raiz, textvariable=self.texto_status, foreground=CORES[0],
                  padding=(10, 0, 10, 6)).pack(side=tk.BOTTOM, fill=tk.X)
        self.figura = Figure(figsize=(11, 6.5))
        self.canvas = FigureCanvasTkAgg(self.figura, master=self.raiz)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def status(self, texto):
        self.texto_status.set(texto)

    # --------------------------------------------------------------- cálculo

    def processar(self):
        try:
            self.cadeia, self.analise = processar()
        except FileNotFoundError as erro:
            messagebox.showerror("Áudios não encontrados", str(erro))
            return
        self.atualizar_grafico()
        pior = max(r.fora_db for r in self.analise)
        self.status(f"Processado: pior energia fora da faixa {num(pior, 0)} dB · "
                    f"correlações {', '.join(num(r.correlacao, 4) for r in self.analise)}")

    def atualizar_grafico(self):
        if self.cadeia is None:
            return
        desenhar(self.figura, self.grafico.get(), self.cadeia, self.analise)
        self.canvas.draw_idle()

    def salvar_pngs(self):
        if self.cadeia is not None:
            caminhos = salvar_graficos(self.cadeia, self.analise)
            self.status(f"{len(caminhos)} gráficos salvos em graficos/")

    # --------------------------------------------------------------- áudio

    def _tem_placa(self):
        if sd is None:
            messagebox.showerror("Sem sounddevice", "Instale com:  pip install sounddevice")
            return False
        return True

    def _tocar(self, trechos):
        """Toca [(rótulo, sinal), ...] em sequência, com PAUSA s entre eles.

        Cada trecho é normalizado sozinho (pico 0,9): o modulado e o demodulado
        saem com o mesmo volume do original, sem saturar a placa de som.
        """
        if self.cadeia is None or not self._tem_placa():
            return
        self.parar()
        silencio = np.zeros(int(PAUSA * FS))
        partes, inicio = [], 0
        for rotulo, sinal in trechos:
            self._avisos.append(self.raiz.after(int(1000 * inicio / FS), self.status, f"Tocando: {rotulo}"))
            partes += [normalizar(sinal, PICO), silencio]
            inicio += len(sinal) + len(silencio)
        try:
            sd.play(np.concatenate(partes), FS)
        except Exception as erro:
            messagebox.showerror("Erro na placa de som", str(erro))
            return
        self._avisos.append(self.raiz.after(int(1000 * inicio / FS), self.status, "Fim da reprodução"))

    def tocar_um(self, etapa, i):
        nomes = {"originais": "original", "modulados": "modulado", "extraidos": "extraído",
                 "demodulados": "demodulado"}
        self._tocar([(f"estação {i + 1} - {nomes[etapa]}", sinais_da_etapa(self.cadeia, etapa)[i])])

    def tocar_etapa(self, etapa):
        nomes = {"originais": "original", "demodulados": "demodulado"}
        self._tocar([(f"estação {i + 1} - {nomes[etapa]}", x)
                     for i, x in enumerate(sinais_da_etapa(self.cadeia, etapa))])

    def tocar_soma(self):
        self._tocar([("soma dos 3 modulados (meio físico)", self.cadeia.soma)])

    def parar(self):
        for aviso in self._avisos:
            self.raiz.after_cancel(aviso)
        self._avisos = []
        if sd is not None:
            sd.stop()
        self.status("")

    def gravar(self, numero):
        if not self._tem_placa():
            return
        self.parar()
        try:
            self._gravacao = sd.rec(int(DURACAO_GRAVACAO * FS), samplerate=FS, channels=1)
        except Exception as erro:
            messagebox.showerror("Erro no microfone", str(erro))
            return
        for b in self.botoes_gravar:
            b.state(["disabled"])
        self.status(f"Gravando a estação {numero} por {DURACAO_GRAVACAO} s… fale perto do microfone")
        self.raiz.after(DURACAO_GRAVACAO * 1000 + 300, self._fim_gravacao, numero)

    def _fim_gravacao(self, numero):
        sd.wait()
        for b in self.botoes_gravar:
            b.state(["!disabled"])
        audio = self._gravacao[:, 0] - np.mean(self._gravacao[:, 0])    # tira o nível DC do microfone
        if np.max(np.abs(audio)) < 1e-4:
            messagebox.showwarning("Gravação muda", "O microfone não captou som.")
            return
        salvar_wav(caminho_original(numero), suavizar_bordas(normalizar(audio, 0.8)), FS)
        self.processar()
        self.status(f"Gravação salva em audios/originais/estacao_{numero}.wav e processada")

    def abrir(self, numero):
        caminho = filedialog.askopenfilename(initialdir=PASTA_AUDIOS, filetypes=[("Áudio WAV", "*.wav")])
        if not caminho:
            return
        try:
            audio = carregar_audio(caminho)         # mono, 44,1 kHz, até 10 s
        except Exception as erro:
            messagebox.showerror("Não consegui abrir", str(erro))
            return
        salvar_wav(caminho_original(numero), normalizar(audio - np.mean(audio), 0.8), FS)
        self.processar()
        self.status(f"{os.path.basename(caminho)} agora é a estação {numero}")


def main():
    parser = argparse.ArgumentParser(description="Rádio AM: 3 estações moduladas, somadas e demoduladas")
    parser.add_argument("--sem-janela", action="store_true",
                        help="só imprime o relatório e salva os wavs e os gráficos (PNG)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")       # acentos no terminal do Windows

    if args.sem_janela:
        try:
            cadeia, analise = processar()
        except FileNotFoundError as erro:
            sys.exit(str(erro))
        for caminho in salvar_graficos(cadeia, analise):
            print(caminho)
        return

    raiz = tk.Tk()
    Radio(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
