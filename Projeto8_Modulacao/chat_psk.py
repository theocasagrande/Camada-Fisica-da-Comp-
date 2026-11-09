
# Projeto 8 (parte 2) - Chat entre 2 computadores por áudio modulado em PSK
#
#   python chat_psk.py emissor    -> digite a frase e Enter: ela sai pelo alto-falante a 100 bit/s
#   python chat_psk.py receptor   -> escuta o microfone e escreve as frases que chegam
#   python chat_psk.py chat       -> as duas coisas no mesmo computador (manda e recebe)
#   python chat_psk.py simular    -> sem som: o áudio passa por um canal simulado (ruído, eco,
#                                    relógios diferentes) e é demodulado no mesmo computador
#
# Opções (iguais nos dois computadores!): --taxa 100  --portadora 4000
# Outras: --volume 0.6  --bits (mostra os bits)  --snr 20 --ppm 50 (só no simular)
#
# Comandos no prompt (comece com /):
#   /grafico        FFT do último sinal emitido/recebido, bits, inversão de fase, constelação
#                   (/grafico enviado  ou  /grafico recebido  escolhe qual)
#   /taxa N         muda a taxa (bit/s)            /portadora F   muda a portadora (Hz)
#   /bits           liga/desliga a impressão dos bits
#   /nivel          volume que o microfone está captando na banda da portadora
#   /info           parâmetros atuais              /sair
#
# Os últimos áudios ficam em audios_psk/enviado.wav e audios_psk/recebido.wav.

import argparse
import os
import queue
import sys
import threading
import time
from collections import deque

import numpy as np
from scipy.signal import butter, sosfilt

from am import salvar_wav
from psk import (ABERTURA, AMPLITUDE, BARKER, BITS_CABECALHO, BITS_CRC, FC, FIM, FS, TAXA, Receptor,
                 banda_medida, banda_teorica, canal, crc16, modular_bpsk, montar_quadro, receber)

try:
    import sounddevice as sd
except ImportError:
    sd = None

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_AUDIOS = os.path.join(PASTA, "audios_psk")
PASTA_GRAFICOS = os.path.join(PASTA, "graficos_psk")
BLOCO = 0.1                 # s de microfone por pedaço entregue ao receptor
SILENCIO_DEPOIS = 0.3       # s esperando o eco da sala acabar antes de voltar a escutar


def num(x, casas=2):
    return f"{x:.{casas}f}".replace(".", ",")


def curto(x):
    """441.0 -> '441'; 220.5 -> '220,5'."""
    return f"{x:g}".replace(".", ",")


def em_grupos(bits, tamanho=8):
    return " ".join("".join(map(str, bits[i:i + tamanho])) for i in range(0, len(bits), tamanho))


class Chat:

    def __init__(self, modo, taxa, fc, volume, mostrar_bits, snr, ppm):
        self.modo, self.taxa, self.fc, self.volume = modo, taxa, fc, volume
        self.mostrar_bits, self.snr, self.ppm = mostrar_bits, snr, ppm
        self.enviado = None         # (áudio, bits, dados, trecho, texto) da última frase enviada
        self.recebida = None        # Mensagem da última frase recebida
        self.ultimo = None          # "enviado" ou "recebido": o que aconteceu por último
        self.transmitindo = False
        self.trava = threading.Lock()
        self.receptor = Receptor(fc, taxa)
        self.ultimo_segundo = deque(maxlen=int(1 / BLOCO))
        self.stream = None
        os.makedirs(PASTA_AUDIOS, exist_ok=True)

    # ---------------------------------------------------------- escuta

    def escutar(self):
        """Abre o microfone. O callback só enfileira; o trabalho pesado é numa thread."""
        self.fila = queue.Queue()
        self.stream = sd.InputStream(samplerate=FS, channels=1, blocksize=int(BLOCO * FS),
                                     callback=self._callback)
        self.stream.start()
        threading.Thread(target=self._trabalhar, daemon=True).start()

    def _callback(self, indata, frames, tempo, status):
        bloco = indata[:, 0].copy()
        self.ultimo_segundo.append(bloco)
        if not self.transmitindo:               # no modo chat, não "ouve" a própria mensagem
            self.fila.put(bloco)

    def _trabalhar(self):
        while True:
            bloco = self.fila.get()
            with self.trava:
                mensagens = self.receptor.alimentar(bloco)
                avisos = [a for a in self.receptor.pegar_avisos() if "falsa" not in a]
            for aviso in avisos:
                self.escrever(f"  [{aviso}]")
            for m in mensagens:
                self.mostrar_recebida(m)

    def escrever(self, texto):
        """Escreve por cima do prompt e devolve o prompt (a escuta roda em outra thread)."""
        if self.stream is None:                 # simular: não há outra thread, o prompt volta sozinho
            print(texto)
        else:
            print(f"\r{texto}\n> ", end="", flush=True)

    def mostrar_recebida(self, m):
        self.recebida, self.ultimo = m, "recebido"
        salvar_wav(os.path.join(PASTA_AUDIOS, "recebido.wav"), m.audio / max(1e-9, np.max(np.abs(m.audio))) * 0.9)
        detalhes = (f"{len(m.dados)} bytes · CRC {'ok' if m.ok else 'NÃO CONFERE'} · SNR {num(m.snr_db, 0)} dB · "
                    f"fase {num(m.fase, 0)}° · desvio {m.desvio_hz:+.2f} Hz".replace(".", ","))
        if m.ok:
            texto = f"◀ {m.texto}\n    ({detalhes})"
        else:
            texto = f"◀ ⚠ mensagem com erro: {m.texto!r}\n    ({detalhes})"
        if self.mostrar_bits:
            texto += "\n" + self.bits_formatados(m.bits)
        self.escrever(texto)

    # ---------------------------------------------------------- envio

    def bits_formatados(self, bits):
        n_sinc, n_cab = len(BARKER), len(BARKER) + BITS_CABECALHO
        return (f"    sincronia  {''.join(map(str, bits[:n_sinc]))}\n"
                f"    tamanho    {em_grupos(bits[n_sinc:n_cab])}\n"
                f"    dados      {em_grupos(bits[n_cab:-BITS_CRC])}\n"
                f"    CRC        {em_grupos(bits[-BITS_CRC:])}")

    def enviar(self, texto):
        try:
            bits, dados = montar_quadro(texto)
        except ValueError as erro:
            print(f"  {erro}")
            return
        audio, trecho = modular_bpsk(bits, self.fc, self.taxa, FS, self.volume)
        self.enviado, self.ultimo = (audio, bits, dados, trecho, texto), "enviado"
        n_dados = 8 * len(dados)
        ini, fim = trecho
        print(f"  {len(texto)} caracteres -> {len(dados)} bytes UTF-8: {dados.hex(' ').upper()}")
        print(f"  quadro: {len(BARKER)} (sincronia) + {BITS_CABECALHO} (tamanho) + {n_dados} (dados) + "
              f"{BITS_CRC} (CRC 0x{crc16(dados):04X}) = {len(bits)} bits")
        print(f"  {self.taxa} bit/s: {curto(FS / self.taxa)} amostras e {curto(self.fc / self.taxa)} ciclos "
              f"da portadora por bit; {num(len(bits) / self.taxa)} s de bits + {num(ABERTURA + FIM)} s "
              f"de abertura e fim = {num(len(audio) / FS)} s")
        print(f"  banda: lóbulo principal {self.fc - self.taxa}-{self.fc + self.taxa} Hz "
              f"(2 × {self.taxa} = {banda_teorica(self.taxa)} Hz); medida com 90% da energia: "
              f"{num(banda_medida(audio[ini:fim], self.fc, vizinhanca=10 * self.taxa), 0)} Hz")
        if self.mostrar_bits:
            print(self.bits_formatados(bits))
        salvar_wav(os.path.join(PASTA_AUDIOS, "enviado.wav"), audio)

        if self.modo == "simular":
            self.simular(audio)
            return
        print(f"  ▶ tocando {num(len(audio) / FS)} s...", end="", flush=True)
        self.transmitindo = True
        try:
            sd.play(audio, FS)
            sd.wait()
            time.sleep(SILENCIO_DEPOIS)
        finally:
            with self.trava:
                self.receptor = Receptor(self.fc, self.taxa)     # esquece o que ouviu durante o envio
            self.transmitindo = False
        print(" enviado")

    def simular(self, audio):
        recebido = canal(audio, snr_db=self.snr, ppm=self.ppm, semente=int(time.time()))
        print(f"  [canal simulado: atraso 0,4 s, eco, zumbido de 120 Hz, voz de fundo, "
              f"SNR {num(self.snr, 0)} dB, relógios {self.ppm:+.0f} ppm]")
        mensagens = receber(recebido, self.fc, self.taxa)
        if not mensagens:
            print("  ◀ nada recebido (a sincronia não foi encontrada)")
        for m in mensagens:
            self.mostrar_recebida(m)

    # ---------------------------------------------------------- comandos

    def mudar(self, taxa=None, fc=None):
        taxa = taxa or self.taxa
        fc = fc or self.fc
        if not 2000 <= fc <= 6000:
            print(f"  atenção: o enunciado pede portadora entre 2000 e 6000 Hz ({fc} Hz está fora)")
        if fc - taxa <= 0 or fc + taxa >= FS / 2:
            print("  essa combinação não cabe entre 0 e 22050 Hz")
            return
        with self.trava:
            self.taxa, self.fc = taxa, fc
            self.receptor = Receptor(fc, taxa)
        print(f"  agora: {taxa} bit/s, portadora {fc} Hz (mude igual no outro computador!)")

    def nivel(self):
        if not self.ultimo_segundo:
            print("  o microfone não está aberto (use os modos receptor ou chat)")
            return
        x = np.concatenate(list(self.ultimo_segundo))
        sos = butter(4, [max(20, self.fc - 4 * self.taxa), min(FS / 2 - 20, self.fc + 4 * self.taxa)],
                     btype="bandpass", fs=FS, output="sos")
        total = 20 * np.log10(max(np.sqrt(np.mean(x ** 2)), 1e-9))
        banda = 20 * np.log10(max(np.sqrt(np.mean(sosfilt(sos, x) ** 2)), 1e-9))
        print(f"  microfone no último segundo: {num(total, 0)} dBFS no total, {num(banda, 0)} dBFS "
              f"na banda {self.fc - 4 * self.taxa}-{self.fc + 4 * self.taxa} Hz")

    def grafico(self, qual=None):
        """Abre o painel de gráficos da última mensagem (enviada ou recebida).

        No modo simular, a recebida é a mesma frase enviada: aparecem as duas FFTs.
        Nos outros, o receptor não tem o áudio do outro computador, mas sabe os
        bits que chegaram: modulando os mesmos bits sai exatamente o sinal emitido.
        """
        import matplotlib.pyplot as plt
        from graficos_psk import desenhar_mensagem
        qual = qual or self.ultimo
        enviado = recebido = simbolos_rx = None
        if qual == "recebido" and self.recebida is not None:
            m = self.recebida
            fc, taxa, bits = m.fc, m.taxa, m.bits
            recebido, simbolos_rx = (m.audio, m.trecho), m.simbolos
            if self.modo == "simular" and self.enviado is not None:
                enviado = (self.enviado[0], self.enviado[3])
            else:
                audio, trecho = modular_bpsk(bits, fc, taxa)
                enviado = (audio, trecho)
        elif self.enviado is not None:
            audio, bits, _, trecho, _ = self.enviado
            fc, taxa, enviado = self.fc, self.taxa, (audio, trecho)
        else:
            print("  ainda não há nada para mostrar")
            return
        fig = plt.figure("Chat PSK", figsize=(13, 8.5), layout="constrained")
        desenhar_mensagem(fig, fc, taxa, bits, enviado, recebido, simbolos_rx)
        os.makedirs(PASTA_GRAFICOS, exist_ok=True)
        caminho = os.path.join(PASTA_GRAFICOS, f"chat_{self.modo}_{qual}_{taxa}bps_{fc}Hz.png")
        fig.savefig(caminho, dpi=110)
        print(f"  gráfico salvo em {os.path.relpath(caminho, PASTA)} (feche a janela para voltar ao chat)")
        if plt.get_backend().lower() != "agg":
            plt.show()
        plt.close(fig)

    def info(self):
        print(f"  modo {self.modo} · {self.taxa} bit/s · portadora {self.fc} Hz · volume {self.volume} · "
              f"{curto(FS / self.taxa)} amostras por bit · banda ≈ {banda_teorica(self.taxa)} Hz")

    def comando(self, linha):
        partes = linha.split()
        nome = partes[0].lower()
        try:
            if nome == "/taxa":
                self.mudar(taxa=int(partes[1]))
            elif nome == "/portadora":
                self.mudar(fc=int(partes[1]))
            elif nome == "/bits":
                self.mostrar_bits = not self.mostrar_bits
                print(f"  bits {'ligados' if self.mostrar_bits else 'desligados'}")
            elif nome == "/grafico":
                self.grafico(partes[1] if len(partes) > 1 else None)
            elif nome == "/nivel":
                self.nivel()
            elif nome == "/info":
                self.info()
            elif nome in ("/sair", "/q"):
                return False
            else:
                print("  comandos: /grafico [enviado|recebido]  /taxa N  /portadora F  /bits  /nivel  /info  /sair")
        except (IndexError, ValueError):
            print("  uso: /taxa 100  ou  /portadora 4000")
        return True

    # ---------------------------------------------------------- laço principal

    def rodar(self):
        titulos = {"emissor": "EMISSOR: digite a frase e aperte Enter",
                   "receptor": "RECEPTOR: escutando o microfone (só comandos aqui)",
                   "chat": "CHAT: digite para enviar; o que chegar aparece sozinho",
                   "simular": "SIMULAR: a frase passa por um canal simulado e é demodulada aqui"}
        print(f"Chat PSK · {titulos[self.modo]}")
        self.info()
        print("  /ajuda para os comandos, /sair para sair\n")
        if self.modo in ("receptor", "chat"):
            self.escutar()
        while True:
            try:
                linha = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not linha:
                continue
            if linha.startswith("/"):
                if not self.comando(linha):
                    break
            elif self.modo == "receptor":
                print("  no modo receptor não se envia: use o modo chat ou emissor")
            else:
                self.enviar(linha)
        if self.stream is not None:
            self.stream.stop()


def main():
    parser = argparse.ArgumentParser(description="Chat por áudio com modulação BPSK")
    parser.add_argument("modo", nargs="?", default="chat", choices=["emissor", "receptor", "chat", "simular"])
    parser.add_argument("--taxa", type=int, default=TAXA, help="bits por segundo (padrão 100)")
    parser.add_argument("--portadora", type=int, default=FC, help="Hz, entre 2000 e 6000 (padrão 4000)")
    parser.add_argument("--volume", type=float, default=AMPLITUDE, help="pico do sinal, 0 a 1 (padrão 0,6)")
    parser.add_argument("--bits", action="store_true", help="mostra os bits de cada mensagem")
    parser.add_argument("--snr", type=float, default=20, help="só no simular: SNR do canal em dB")
    parser.add_argument("--ppm", type=float, default=50, help="só no simular: diferença dos relógios")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")       # acentos no terminal do Windows
        sys.stdin.reconfigure(encoding="utf-8")
    if args.modo != "simular" and sd is None:
        sys.exit("Instale o sounddevice:  pip install sounddevice  (ou use o modo simular)")
    Chat(args.modo, args.taxa, args.portadora, args.volume, args.bits, args.snr, args.ppm).rodar()


if __name__ == "__main__":
    main()
