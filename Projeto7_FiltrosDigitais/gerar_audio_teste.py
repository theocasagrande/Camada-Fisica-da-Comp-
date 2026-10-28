
# Projeto 7 - gera os áudios de teste do equalizador em audios/
#
#   teste.wav      6 s de "música" sintética: bumbo e baixo (graves), acordes e
#                  melodia (médios) e chimbal (agudos). Mexer em qualquer grupo
#                  de bandas muda algo audível.
#   varredura.wav  senoide que sobe de 20 Hz a 20 kHz em 6 s. Passando pelo
#                  equalizador, o volume ao longo do tempo segue o Bode.
#
#   python gerar_audio_teste.py
#
# O enunciado pede um áudio curto gravado: o botão "Gravar" do equalizador grava
# 5 s do microfone em audios/gravacao.wav. Estes arquivos são a alternativa
# reprodutível (o mesmo sinal toda vez).

import os

import numpy as np
from scipy.signal import chirp

from filtros import FS, salvar_wav

PASTA_AUDIOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audios")
DURACAO = 6         # segundos
BATIDA = 0.5        # 120 batidas por minuto
PICO = 0.5          # pico de -6 dBFS: deixa folga para o equalizador reforçar


def nota(freq, duracao, harmonicos, fs=FS):
    """Nota com `harmonicos` harmônicos de amplitude 1/k (timbre de dente de serra)."""
    t = np.arange(int(duracao * fs)) / fs
    s = sum(np.sin(2 * np.pi * k * freq * t) / k
            for k in range(1, harmonicos + 1) if k * freq < fs / 2)
    envelope = np.minimum(1, t / 0.01) * np.exp(-t / (duracao * 0.8))    # ataque de 10 ms
    return s * envelope


def bumbo(fs=FS):
    """Senoide que cai de 120 Hz para 45 Hz em 0,3 s: energia em 40-120 Hz."""
    t = np.arange(int(0.3 * fs)) / fs
    freq = 45 + 75 * np.exp(-t / 0.04)
    fase = 2 * np.pi * np.cumsum(freq) / fs
    return np.sin(fase) * np.exp(-t / 0.12)


def chimbal(rng, fs=FS):
    """Rajada curta de ruído derivado: a derivada realça os agudos (6 dB por oitava)."""
    n = int(0.06 * fs)
    ruido = np.diff(rng.standard_normal(n + 1))
    return ruido * np.exp(-np.arange(n) / fs / 0.015)


def colocar(destino, som, inicio, volume, fs=FS):
    i = int(inicio * fs)
    fim = min(len(destino), i + len(som))
    destino[i:fim] += volume * som[:fim - i]


def gerar_musica(fs=FS):
    rng = np.random.default_rng(7)
    musica = np.zeros(int(DURACAO * fs))
    # um acorde por compasso de 4 batidas: (fundamental do baixo, notas do acorde)
    acordes = [(55.0, (220.0, 261.6, 329.6)),      # Lá menor
               (43.65, (174.6, 220.0, 261.6)),     # Fá
               (65.41, (196.0, 261.6, 329.6))]     # Dó
    melodia = [659.3, 587.3, 523.3, 587.3, 659.3, 784.0, 659.3, 523.3,
               698.5, 659.3, 587.3, 523.3]
    for c, (baixo, acorde) in enumerate(acordes):
        inicio = c * 4 * BATIDA
        colocar(musica, nota(baixo, 4 * BATIDA, 12), inicio, 0.35)
        for f in acorde:
            colocar(musica, nota(f, 4 * BATIDA, 8), inicio, 0.12)
    for b in range(int(DURACAO / BATIDA)):
        colocar(musica, bumbo(), b * BATIDA, 0.9)
        colocar(musica, nota(melodia[b % len(melodia)], BATIDA, 20), b * BATIDA, 0.15)
        for meia in (0, BATIDA / 2):                # chimbal em colcheias
            colocar(musica, chimbal(rng), b * BATIDA + meia, 0.08)
    return musica * PICO / np.max(np.abs(musica))


def gerar_varredura(fs=FS):
    t = np.arange(int(DURACAO * fs)) / fs
    s = chirp(t, f0=20, t1=DURACAO, f1=20000, method="logarithmic")
    rampa = np.minimum(1, np.minimum(t, DURACAO - t) / 0.02)     # sem estalo nas pontas
    return PICO * s * rampa


def main():
    os.makedirs(PASTA_AUDIOS, exist_ok=True)
    for nome, sinal in (("teste.wav", gerar_musica()), ("varredura.wav", gerar_varredura())):
        caminho = os.path.join(PASTA_AUDIOS, nome)
        salvar_wav(caminho, sinal, FS)
        print(f"{caminho}  ({len(sinal) / FS:.1f} s, {FS} Hz, 16 bits, mono)")


if __name__ == "__main__":
    main()
