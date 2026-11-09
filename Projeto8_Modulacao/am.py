
# Projeto 8 (parte 1) - Modulação AM: biblioteca usada pelo rádio, pelos
# exercícios e pelos testes.
#
# Nada aqui depende de interface gráfica nem de placa de som, para poder ser
# testado sozinho (python testes.py).
#
# A cadeia completa, para cada uma das 3 estações:
#
#   EMISSOR   áudio ─► passa-baixa (cabe na faixa) ─► × portadora ─► modulado
#   CANAL     modulado 1 + modulado 2 + modulado 3 = soma (o "ar")
#   RECEPTOR  soma ─► passa-faixa (sintoniza) ─► × portadora ─► passa-baixa ─► × 2 ─► áudio

from collections import namedtuple
from math import gcd

import numpy as np
from scipy.fft import next_fast_len
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfiltfilt, sosfreqz, welch

FS = 44100

# As 3 faixas do enunciado, em Hz: uma por estação de rádio.
FAIXAS = ((9000, 12000), (12000, 15000), (15000, 18000))

ORDEM_PB = 12       # passa-baixa da mensagem (emissor) e da demodulação (receptor)
ORDEM_PF = 10       # passa-faixa do receptor: o projeto final tem ordem 2 x 10 = 20
FOLGA = 0.8         # a mensagem é cortada em 80% da meia-largura da faixa
RAMPA = 0.02        # s de subida/descida no começo e no fim da mensagem

# Uma estação: faixa permitida [f_ini, f_fim], portadora fc no centro, corte do
# passa-baixa da mensagem e meia-largura da faixa (corte do passa-baixa do receptor).
Estacao = namedtuple("Estacao", "numero f_ini f_fim fc corte meia_largura")


def criar_estacao(numero, faixa, folga=FOLGA):
    """Monta a estação a partir da faixa.

    Multiplicar a mensagem (até B Hz) pela portadora fc cria componentes de
    fc - B até fc + B. Para caber em [f_ini, f_fim], a portadora fica no centro
    e B tem que ser no máximo a meia-largura da faixa. Usamos 80% dela: o
    passa-baixa não corta "de uma vez", e os 20% restantes são a margem em que
    ele atenua o resto (-47 dB na borda, ver testes.py).
    """
    f_ini, f_fim = faixa
    meia = (f_fim - f_ini) / 2
    return Estacao(numero, f_ini, f_fim, f_ini + meia, folga * meia, meia)


ESTACOES = tuple(criar_estacao(i + 1, f) for i, f in enumerate(FAIXAS))


# ------------------------------------------------------------------ sinais

def tempo(n, fs=FS):
    """Vetor de tempo com n pontos e passo exato 1/fs."""
    return np.arange(n) / fs


def senoide(freq, n, fs=FS, amplitude=1.0, fase=0.0):
    """A sen(2 pi f t + fase), com n pontos. A fase é em radianos."""
    return amplitude * np.sin(2 * np.pi * freq * tempo(n, fs) + fase)


def portadora(fc, n, fs=FS, fase=0.0):
    """C(t) = sen(2 pi fc t + fase) com EXATAMENTE n pontos (o mesmo número do sinal)."""
    return senoide(fc, n, fs, 1.0, fase)


def normalizar(x, pico=1.0):
    maior = np.max(np.abs(x))
    return x * (pico / maior) if maior > 0 else x


def suavizar_bordas(x, fs=FS, duracao=RAMPA):
    """Sobe de 0 a 1 no começo e desce no fim (meio cosseno de `duracao` s).

    Um áudio que começa ou termina "de repente" tem um degrau, e um degrau tem
    componentes em todas as frequências: depois de modulado, esse espalhamento
    vazaria para as faixas vizinhas. Com a rampa o sinal nasce e morre em zero.
    """
    n = min(int(duracao * fs), len(x) // 2)
    if n == 0:
        return x
    rampa = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    y = np.array(x, dtype=float)
    y[:n] *= rampa
    y[-n:] *= rampa[::-1]
    return y


def igualar_tamanhos(sinais):
    """Completa com zeros no fim para todos terem o mesmo tamanho (para somar).

    O tamanho é o do maior, arredondado para cima até um número que a FFT
    calcula rápido (next_fast_len): 201672 amostras = 2³·3²·2801, e o fator
    primo 2801 deixa a FFT 7 vezes mais lenta. Os zeros a mais são silêncio.
    """
    n = next_fast_len(max(len(s) for s in sinais), real=True)
    return [np.pad(s, (0, n - len(s))) for s in sinais]


# ----------------------------------------------------------------- filtros
#
# Os filtros são Butterworth (o mesmo passa-baixa do exercício 1 do Projeto 7),
# só que de ordem alta. Por isso saem em SOS (second-order sections): uma
# cascata de biquads, cada um uma G(z) de 2ª ordem igual às do Projeto 7.
# Escrever o filtro inteiro como uma fração só (b, a) é a "G(z) expandida" do
# Projeto 7: aqui ainda funciona, mas já perde precisão (o passa-baixa de
# 800 Hz do exercício 4 erra 0,27 dB em (b, a) e 0 em SOS - testes.py mostra).

def passa_baixa(corte, fs=FS, ordem=ORDEM_PB):
    return butter(ordem, corte, btype="lowpass", fs=fs, output="sos")


def passa_faixa(f_ini, f_fim, fs=FS, ordem=ORDEM_PF):
    return butter(ordem, [f_ini, f_fim], btype="bandpass", fs=fs, output="sos")


def filtrar(sos, x):
    """Aplica o filtro duas vezes: para frente e, depois, de trás para frente.

    Na ida o filtro atrasa cada frequência um pouco (fase); na volta atrasa o
    mesmo tanto ao contrário, e os atrasos se cancelam: fase ZERO. Isso importa
    na demodulação, que precisa da portadora na mesma fase do sinal recebido.
    O módulo é aplicado duas vezes: |H|², ou seja, a atenuação em dB dobra.
    """
    return sosfiltfilt(sos, x)


def resposta_db(sos, freqs, fs=FS):
    """Ganho em dB do filtro aplicado com filtrar(): 2 x 20 log10 |H(f)|."""
    _, h = sosfreqz(sos, worN=freqs, fs=fs)
    return 2 * em_db(h)


def em_db(h):
    return 20 * np.log10(np.maximum(np.abs(h), 1e-12))


# ------------------------------------------------------------- modulação AM

def limitar_banda(audio, estacao, fs=FS):
    """Prepara o áudio para caber na faixa da estação.

    Tira o nível DC, corta acima de `estacao.corte` com o passa-baixa,
    normaliza o pico em 1 (as 3 estações com o mesmo volume) e suaviza as bordas.
    """
    m = np.asarray(audio, dtype=float) - np.mean(audio)
    m = filtrar(passa_baixa(estacao.corte, fs), m)
    return suavizar_bordas(normalizar(m), fs)


def modular(m, fc, fs=FS, fase=0.0):
    """AM por multiplicação ponto a ponto: S(t) = m(t) . C(t).

    sen(a) . sen(b) = [cos(a - b) - cos(a + b)] / 2: cada frequência fm da
    mensagem vira duas, fc - fm e fc + fm. A mensagem inteira (0 a B Hz) vai
    para a faixa fc - B até fc + B, e nada sobra perto de 0 Hz.
    """
    return m * portadora(fc, len(m), fs, fase)


def sintonizar(soma, estacao, fs=FS):
    """O "dial" do rádio: passa-faixa na faixa da estação, o resto é rejeitado."""
    return filtrar(passa_faixa(estacao.f_ini, estacao.f_fim, fs), soma)


def demodular(s, estacao, fs=FS, fase=0.0):
    """Demodulação síncrona: multiplica pela portadora de novo e passa-baixa.

    m(t) sen²(2 pi fc t) = m(t)/2 - m(t)/2 . cos(2 pi 2fc t): a informação volta
    para perto de 0 Hz com metade da amplitude, e uma cópia vai para 2fc. O
    passa-baixa remove a cópia (e o que vazou das vizinhas) e o x 2 devolve a
    amplitude. Retorna (áudio demodulado, produto antes do passa-baixa).

    `fase` é o erro de fase da portadora local: a saída fica multiplicada por
    cos(fase) (0° = perfeita, 60° = metade, 90° = silêncio).
    """
    produto = s * portadora(estacao.fc, len(s), fs, fase)
    pb = passa_baixa(estacao.meia_largura, fs)
    return 2 * filtrar(pb, produto), produto


# Tudo o que acontece com uma estação, para os gráficos e os relatórios.
Cadeia = namedtuple("Cadeia", "fs estacoes originais mensagens modulados soma "
                              "extraidos produtos demodulados")


def simular(audios, fs=FS, estacoes=ESTACOES):
    """Emissor + canal + receptor para os 3 áudios (um por estação)."""
    originais = igualar_tamanhos([np.asarray(a, dtype=float) for a in audios])
    mensagens = [limitar_banda(a, e, fs) for a, e in zip(originais, estacoes)]
    modulados = [modular(m, e.fc, fs) for m, e in zip(mensagens, estacoes)]
    soma = np.sum(modulados, axis=0)                      # o meio físico
    extraidos = [sintonizar(soma, e, fs) for e in estacoes]
    saidas = [demodular(x, e, fs) for x, e in zip(extraidos, estacoes)]
    return Cadeia(fs, tuple(estacoes), originais, mensagens, modulados, soma, extraidos,
                  [p for _, p in saidas], [d for d, _ in saidas])


# ---------------------------------------------------------------- medições

def espectro(x, fs=FS):
    """Amplitude de cada senoide que compõe x (janela de Hann, freqs positivas).

    A escala 2/soma(janela) faz um tom A sen(2 pi f t) aparecer com altura A,
    então dá para ler a amplitude direto no gráfico.
    """
    janela = np.hanning(len(x))
    X = np.fft.rfft(x * janela)
    return np.fft.rfftfreq(len(x), 1 / fs), 2 * np.abs(X) / janela.sum()


def densidade_db(x, fs=FS, nperseg=8192):
    """Densidade espectral (Welch) em dB, relativa ao maior valor: para ver -60 dB."""
    f, p = welch(x, fs=fs, nperseg=min(nperseg, len(x)))
    return f, 10 * np.log10(np.maximum(p / np.max(p), 1e-30))


def energia_por_faixa(x, faixas, fs=FS):
    """Fração da energia de x dentro de cada faixa (Parseval sobre a FFT).

    Retorna (frações por faixa, fração fora de todas as faixas).
    """
    potencia = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / fs)
    total = potencia.sum()
    fracoes = [potencia[(f >= a) & (f < b)].sum() / total for a, b in faixas]
    return fracoes, max(0.0, 1 - sum(fracoes))


def fora_da_faixa(x, faixa, fs=FS):
    """Fração da energia de x FORA de [faixa[0], faixa[1]) - somada direto, sem 1 - dentro."""
    potencia = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / fs)
    return potencia[(f < faixa[0]) | (f >= faixa[1])].sum() / potencia.sum()


def banda_ocupada(x, fs=FS, fracao=0.99):
    """Frequência abaixo da qual está `fracao` da energia de x."""
    potencia = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / fs)
    acumulada = np.cumsum(potencia) / potencia.sum()
    return f[np.searchsorted(acumulada, fracao)]


def db_potencia(fracao):
    return 10 * np.log10(max(fracao, 1e-30))


def snr_db(referencia, estimado):
    """Relação sinal/erro: 10 log10( energia da referência / energia da diferença )."""
    erro = np.sum((referencia - estimado) ** 2)
    return 10 * np.log10(np.sum(referencia ** 2) / max(erro, 1e-30))


def correlacao(a, b):
    return float(np.corrcoef(a, b)[0, 1])


def rebater(f, fs=FS):
    """Onde uma frequência f aparece depois de amostrada a fs (aliasing).

    Só existem frequências de 0 a fs/2 (Nyquist). Acima disso, o sinal amostrado
    é idêntico ao de uma frequência "rebatida" para dentro: 33 kHz amostrado a
    44,1 kHz é igual a 44,1 - 33 = 11,1 kHz.
    """
    return abs((f + fs / 2) % fs - fs / 2)


# Os números que provam que cada etapa funcionou (por estação).
Analise = namedtuple("Analise", "banda_original banda_mensagem energia_faixas_db dentro fora_db "
                                "vazamento_db interferencia_db correlacao snr_db correlacao_original")


def analisar(cadeia):
    """Mede a cadeia: banda ocupada, energia em cada faixa, interferência e fidelidade.

    O vazamento é o que passa pelo passa-faixa vindo das OUTRAS estações
    (energia relativa à da própria estação depois do filtro). A interferência
    compara o demodulado a partir da SOMA com o demodulado da estação SOZINHA
    no ar: a diferença entre os dois é tudo o que veio das outras estações e
    sobreviveu também ao passa-baixa.
    """
    fs, faixas = cadeia.fs, [(e.f_ini, e.f_fim) for e in cadeia.estacoes]
    resultado = []
    for i, e in enumerate(cadeia.estacoes):
        fracoes, _ = energia_por_faixa(cadeia.modulados[i], faixas, fs)
        propria = sintonizar(cadeia.modulados[i], e, fs)
        vizinhas = sintonizar(cadeia.soma - cadeia.modulados[i], e, fs)
        sozinha, _ = demodular(propria, e, fs)
        resultado.append(Analise(
            banda_original=banda_ocupada(cadeia.originais[i], fs),
            banda_mensagem=banda_ocupada(cadeia.mensagens[i], fs),
            energia_faixas_db=[db_potencia(x) for x in fracoes],
            dentro=fracoes[i],
            fora_db=db_potencia(fora_da_faixa(cadeia.modulados[i], faixas[i], fs)),
            vazamento_db=db_potencia(np.sum(vizinhas ** 2) / np.sum(propria ** 2)),
            interferencia_db=-snr_db(sozinha, cadeia.demodulados[i]),
            correlacao=correlacao(cadeia.mensagens[i], cadeia.demodulados[i]),
            snr_db=snr_db(cadeia.mensagens[i], cadeia.demodulados[i]),
            correlacao_original=correlacao(cadeia.originais[i], cadeia.demodulados[i]),
        ))
    return resultado


# ------------------------------------------------------------------ arquivos

def ler_wav(caminho):
    """Lê um .wav e devolve (audio, fs) com o áudio em float entre -1 e 1."""
    fs, audio = wavfile.read(caminho)
    if audio.dtype == np.uint8:                     # 8 bits é sem sinal, centrado em 128
        audio = (audio.astype(float) - 128) / 128
    elif np.issubdtype(audio.dtype, np.integer):    # 16/24/32 bits com sinal
        audio = audio / float(-np.iinfo(audio.dtype).min)
    return np.asarray(audio, dtype=float), fs


def carregar_audio(caminho, fs=FS, max_segundos=10):
    """Lê um .wav como mono, na taxa `fs` (reamostra se precisar), até `max_segundos`.

    Áudio a 48 kHz, por exemplo, é convertido para 44,1 kHz: as 3 estações
    precisam estar na mesma taxa para serem somadas ponto a ponto.
    """
    audio, fs_arquivo = ler_wav(caminho)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if fs_arquivo != fs:
        g = gcd(int(fs), int(fs_arquivo))
        audio = resample_poly(audio, int(fs) // g, int(fs_arquivo) // g)
    return audio[:int(max_segundos * fs)]


def salvar_wav(caminho, audio, fs=FS):
    """Grava em 16 bits. Valores fora de [-1, 1] são cortados."""
    dados = np.clip(audio, -1, 1) * 32767
    wavfile.write(caminho, fs, dados.astype(np.int16))
