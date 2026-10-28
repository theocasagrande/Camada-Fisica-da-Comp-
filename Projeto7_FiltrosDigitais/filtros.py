
# Projeto 7 - Filtros digitais: biblioteca usada pelo equalizador, pelos
# exercícios e pelos testes.
#
# Nada aqui depende de interface gráfica nem de placa de som, para poder ser
# testado sozinho (python testes.py).

from collections import namedtuple

import numpy as np
from scipy.io import wavfile
from scipy.signal import freqz, lfilter

FS = 44100

# Frequências centrais das 12 bandas: as da figura do enunciado (PDF).
BANDAS = (20, 32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000, 20000)

GANHO_MIN, GANHO_MAX = -10, 10      # dB, limites pedidos no enunciado

# Um filtro de banda: frequência central, ganho (dB), fator de qualidade e os
# coeficientes de G(z) = (b0 z² + b1 z + b2) / (z² + a1 z + a2).
Filtro = namedtuple("Filtro", "f0 ganho Q b a")


def peaking_eq(f0, gain_db, Q, fs):
    """Filtro de picos (peaking EQ) - mesma fórmula do notebook filtro_peaking_EQ.

    Na frequência f0 o ganho é exatamente gain_db (+ reforça, - atenua) e longe
    de f0 o ganho volta a 0 dB. Q controla a largura: quanto maior, mais estreita
    a faixa afetada. Retorna (b, a) já normalizados para a[0] = 1.
    """
    A = 10**(gain_db / 40)  # amplitude
    omega = 2 * np.pi * f0 / fs
    alpha = np.sin(omega) / (2 * Q)

    b0 = 1 + alpha * A
    b1 = -2 * np.cos(omega)
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * np.cos(omega)
    a2 = 1 - alpha / A

    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0
    return b, a


def fatores_q(bandas=BANDAS):
    """Q de cada banda, calculado a partir da distância até as vizinhas.

    Cada banda "cuida" do trecho que vai do ponto médio (na escala log) com a
    vizinha de baixo até o ponto médio com a vizinha de cima, e Q = f0 / largura.
    Para bandas separadas por uma oitava (125, 250, 500...) isso dá Q = 1,41, o
    valor clássico de equalizador gráfico. As pontas da figura são mais próximas
    entre si (20-32 Hz, 16-20 kHz), então ganham Q maior (faixa mais estreita)
    para não invadir a vizinha. Nas extremidades espelhamos a única vizinha.
    """
    qs = []
    for i, f in enumerate(bandas):
        razao_baixo = f / bandas[i - 1] if i > 0 else bandas[1] / bandas[0]
        razao_cima = bandas[i + 1] / f if i < len(bandas) - 1 else bandas[-1] / bandas[-2]
        f_baixo = f / np.sqrt(razao_baixo)
        f_cima = f * np.sqrt(razao_cima)
        qs.append(f / (f_cima - f_baixo))
    return qs


def projetar_equalizador(ganhos, fs=FS, bandas=BANDAS):
    """Uma função de transferência G(z) por banda, coerente com os ganhos.

    Bandas com f0 acima da metade da taxa de amostragem (Nyquist) não existem no
    sinal digital e são ignoradas - só acontece com arquivos abaixo de 40 kHz.
    """
    filtros = []
    for f0, ganho, Q in zip(bandas, ganhos, fatores_q(bandas)):
        if f0 >= fs / 2:
            continue
        b, a = peaking_eq(f0, ganho, Q, fs)
        filtros.append(Filtro(f0, ganho, Q, b, a))
    return filtros


def filtro_IIR_ordem2(x, b, a):
    """Equação de diferenças do enunciado, amostra por amostra.

    De G(z) = (b0 z² + b1 z + b2) / (z² + a1 z + a2) sai
        y[n] = -a1 y[n-1] - a2 y[n-2] + b0 x[n] + b1 x[n-1] + b2 x[n-2]
    Os coeficientes do denominador entram com o sinal TROCADO: no exemplo do PDF
    a = [1, -1.5, 0.7] vira "+1.5 y[n-1] - 0.7 y[n-2]".
    """
    b0, b1, b2 = b
    _, a1, a2 = a
    y = [0.0] * len(x)
    xm1 = xm2 = ym1 = ym2 = 0.0     # x[n-1], x[n-2], y[n-1], y[n-2] (zero antes do início)
    for n in range(len(x)):
        y[n] = -a1 * ym1 - a2 * ym2 + b0 * x[n] + b1 * xm1 + b2 * xm2
        xm2, xm1 = xm1, x[n]
        ym2, ym1 = ym1, y[n]
    return np.array(y)


def aplicar_filtros(x, filtros):
    """Aplica os filtros um a um (em cascata): a saída de um é a entrada do próximo.

    lfilter calcula exatamente a mesma equação de diferenças de
    filtro_IIR_ordem2 (testes.py confere), só que em C: 12 filtros num áudio de
    poucos segundos levam milissegundos em vez de segundos. axis=0 filtra cada
    canal de um áudio estéreo (amostras x canais) separadamente.
    """
    y = np.asarray(x, dtype=float)
    for f in filtros:
        y = lfilter(f.b, f.a, y, axis=0)
    return y


def resposta_total(filtros, freqs, fs=FS):
    """H(f) do equalizador inteiro, para o diagrama de Bode.

    Filtros em cascata têm função de transferência G(z) = G1(z)·G2(z)·...·G12(z),
    então a resposta em frequência é o produto das respostas de cada banda (e o
    ganho em dB é a SOMA dos ganhos em dB). Calcular assim, banda a banda, evita
    o polinômio de ordem 24 de funcao_transferencia_expandida, que perde a
    precisão nos graves.
    """
    H = np.ones(len(freqs), dtype=complex)
    for f in filtros:
        _, h = freqz(f.b, f.a, worN=freqs, fs=fs)
        H *= h
    return H


def funcao_transferencia_expandida(filtros):
    """G(z) total como uma fração só, multiplicando os polinômios.

    Multiplicar polinômios é convoluir seus coeficientes (np.convolve). O
    resultado é matematicamente correto, mas tem ordem 24 e os polos das bandas
    graves (20, 32, 64 Hz) ficam todos amontoados perto de z = 1: o arredondamento
    do float64 já basta para deslocá-los, e filtrar com essa fração dá NaN.
    Serve só para mostrar a equivalência - quem filtra e desenha o Bode é a cascata.
    """
    b_total = np.array([1.0])
    a_total = np.array([1.0])
    for f in filtros:
        b_total = np.convolve(b_total, f.b)
        a_total = np.convolve(a_total, f.a)
    return b_total, a_total


def em_db(h):
    """Ganho em dB de uma razão de amplitudes: 20 log10 |h|."""
    return 20 * np.log10(np.maximum(np.abs(h), 1e-12))


def ler_wav(caminho):
    """Lê um .wav e devolve (audio, fs) com o áudio em float entre -1 e 1.

    Mono vem como vetor (N,), estéreo como matriz (N, canais).
    """
    fs, audio = wavfile.read(caminho)
    if audio.dtype == np.uint8:                     # 8 bits é sem sinal, centrado em 128
        audio = (audio.astype(float) - 128) / 128
    elif np.issubdtype(audio.dtype, np.integer):    # 16/24/32 bits com sinal
        audio = audio / float(-np.iinfo(audio.dtype).min)
    return np.asarray(audio, dtype=float), fs


def salvar_wav(caminho, audio, fs):
    """Grava em 16 bits. Valores fora de [-1, 1] são cortados."""
    dados = np.clip(audio, -1, 1) * 32767
    wavfile.write(caminho, fs, dados.astype(np.int16))
