
# Projeto 8 (parte 2) - Modulação digital PSK: biblioteca usada pelo chat, pelos
# experimentos e pelos testes.
#
# Nada aqui toca som nem abre janela, para poder ser testado sozinho
# (python testes_psk.py).
#
# EMISSOR   texto ─► bytes UTF-8 ─► quadro de bits ─► BPSK: bit 0 = fase 0°, bit 1 = fase 180°
# RECEPTOR  microfone ─► passa-faixa ─► × portadora (I e Q) ─► média em cada bit
#           ─► acha a sincronia ─► corrige a fase ─► decide cada bit ─► confere o CRC ─► texto
#
# O quadro (o que vai no ar, nesta ordem):
#   abertura   0,25 s só de portadora (bits 0): dá tempo do alto-falante e do microfone "acordarem"
#   sincronia  13 bits (código de Barker): marca o início e serve de referência de fase
#   tamanho    1 byte com o número de bytes da mensagem + 1 byte com o mesmo número invertido
#   dados      a mensagem em UTF-8 (8 bits por byte, o mais significativo primeiro)
#   CRC-16     2 bytes (o mesmo CRC-16/XMODEM do Projeto 4) para detectar erros
#   fim        0,1 s de portadora

import binascii
from collections import namedtuple

import numpy as np
from scipy.signal import butter, hilbert, sosfilt

from am import espectro, suavizar_bordas

FS = 44100
TAXA = 100              # bits por segundo (pedido no enunciado)
FC = 4000               # Hz; o enunciado pede portadora entre 2 e 6 kHz
AMPLITUDE = 0.6         # pico do sinal enviado à placa de som
ABERTURA = 0.25         # s de portadora antes da sincronia
FIM = 0.10              # s de portadora depois do CRC
LIMIAR = 0.9            # correlação mínima (0 a 1) para aceitar a sincronia
ACIMA_DO_RUIDO = 4      # a sincronia tem que ser 4x (12 dB) mais forte que o ruído antes dela
UNIFORMIDADE = 0.25     # o bit mais fraco da sincronia tem pelo menos 1/4 da força do mais forte
DERIVA_MAXIMA = 0.002   # o instante dos bits pode escorregar no máximo 0,2% (relógios 2000 ppm diferentes)
AMPLITUDE_MINIMA = 1e-4  # abaixo disso é silêncio digital, não sinal
ALFA, BETA = 0.3, 0.02  # ganhos da correção de fase (fase e velocidade da fase) a cada bit
GAMA, ETA = 0.15, 0.005  # ganhos da correção do instante de leitura de cada bit
FOLGA_TEMPO = 2          # bits a mais esperados no fim (o tempo pode ter escorregado)

# Código de Barker de 13: a correlação com ele mesmo deslocado nunca passa de 1/13
# do pico, então o receptor acha o começo exato do quadro. Em símbolos: +1 = fase 0°.
BARKER = np.array([+1, +1, +1, +1, +1, -1, -1, +1, +1, -1, +1, -1, +1])
SINCRONIA = [0 if s > 0 else 1 for s in BARKER]        # os mesmos 13 como bits
BITS_CABECALHO = 16
BITS_CRC = 16


# ------------------------------------------------------------------ bits

def bytes_para_bits(dados):
    """Cada byte vira 8 bits, do mais significativo para o menos: 'A' = 0x41 = 01000001."""
    return [(byte >> (7 - i)) & 1 for byte in dados for i in range(8)]


def bits_para_bytes(bits):
    bits = list(bits)
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - 7, 8))


def crc16(dados):
    """CRC-16/XMODEM (polinômio 0x1021), o mesmo do Projeto 4."""
    return binascii.crc_hqx(bytes(dados), 0)


def montar_quadro(texto):
    """Texto -> lista de bits do quadro (sincronia + tamanho + dados + CRC).

    Retorna (bits, dados): os dados são os bytes UTF-8 do texto. "á" ocupa 2
    bytes em UTF-8, então "Olá" tem 3 caracteres e 4 bytes.
    """
    dados = texto.encode("utf-8")
    if len(dados) > 255:
        raise ValueError(f"mensagem com {len(dados)} bytes: o máximo é 255")
    crc = crc16(dados)
    corpo = bytes([len(dados), len(dados) ^ 0xFF]) + dados + bytes([crc >> 8, crc & 0xFF])
    return SINCRONIA + bytes_para_bits(corpo), dados


def bits_no_quadro(n_bytes):
    return len(SINCRONIA) + BITS_CABECALHO + 8 * n_bytes + BITS_CRC


# ------------------------------------------------------------------ emissor

def simbolos(bits):
    """bit 0 -> +1 (fase 0°), bit 1 -> -1 (fase 180°): cos(x + 180°) = -cos(x)."""
    return 1 - 2 * np.asarray(bits, dtype=int)


def modular_bpsk(bits, fc=FC, taxa=TAXA, fs=FS, amplitude=AMPLITUDE, abertura=ABERTURA, fim=FIM):
    """BPSK: s(t) = A · d(t) · cos(2π fc t), com d(t) = +1 ou -1 durante cada bit.

    É a mesma multiplicação da modulação AM da parte 1, com uma mensagem
    digital: d(t) é uma onda quadrada de ±1 que muda a cada 1/taxa segundos.
    Trocar o sinal da portadora é o mesmo que somar 180° na fase.

    Retorna (sinal, (início dos bits, fim dos bits)) com os índices em amostras.
    """
    n_abertura, n_fim = int(round(abertura * taxa)), int(round(fim * taxa))
    todos = np.concatenate([np.zeros(n_abertura, int), np.asarray(bits, int), np.zeros(n_fim, int)])
    n = int(np.ceil(len(todos) * fs / taxa))
    bit_de_cada_amostra = np.minimum(np.arange(n) * taxa // fs, len(todos) - 1)
    d = simbolos(todos)[bit_de_cada_amostra]
    sinal = amplitude * d * np.cos(2 * np.pi * fc * np.arange(n) / fs)
    inicio = int(np.ceil(n_abertura * fs / taxa))
    fim_bits = int(np.ceil((n_abertura + len(bits)) * fs / taxa))
    return suavizar_bordas(sinal, fs, 0.01), (inicio, fim_bits)


def transmitir(texto, fc=FC, taxa=TAXA, fs=FS, amplitude=AMPLITUDE):
    """Atalho: texto -> (áudio, bits, dados, (início, fim dos bits))."""
    bits, dados = montar_quadro(texto)
    audio, trecho = modular_bpsk(bits, fc, taxa, fs, amplitude)
    return audio, bits, dados, trecho


# ------------------------------------------------------------------ receptor

# Uma mensagem recebida e os números que mostram como foi a recepção.
Mensagem = namedtuple("Mensagem", "texto ok dados bits simbolos inicio correlacao amplitude "
                                  "fase desvio_hz snr_db audio trecho fc taxa")


class Receptor:
    """Demodulador BPSK que recebe o áudio aos pedaços (do microfone ou de um arquivo).

    Cada pedaço passa por:
      1. passa-faixa em volta da portadora (tira voz, ruído grave, etc.);
      2. multiplicação por e^(-j2π fc t) = cos(2π fc t) - j sen(2π fc t), ou seja,
         pela portadora (I) e pela portadora atrasada 90° (Q), como na
         demodulação AM, só que guardando também a fase;
      3. média de cada janela de 1 bit (o "passa-baixa" que tira o termo em 2fc).
    O resultado é um número complexo por bit: o módulo é a amplitude e o ângulo é
    a fase. Bit 0 e bit 1 ficam em lados opostos (180°).
    """

    def __init__(self, fc=FC, taxa=TAXA, fs=FS, limiar=LIMIAR):
        self.fc, self.taxa, self.fs, self.limiar = fc, taxa, fs, limiar
        self.amostras_por_bit = fs / taxa
        self.janela = int(fs // taxa)                   # 441 amostras a 100 bit/s
        baixo = max(20.0, fc - 4 * taxa)
        alto = min(fs / 2 - 20, fc + 4 * taxa)
        self.sos = butter(4, [baixo, alto], btype="bandpass", fs=fs, output="sos")
        self.zi = np.zeros((self.sos.shape[0], 2))      # estado do filtro entre um pedaço e outro
        self.total = 0                                  # amostras recebidas desde o começo
        self.inicio = 0                                 # índice absoluto da 1ª amostra guardada
        self.base = np.zeros(0, dtype=complex)          # sinal × e^(-j2π fc t) (sem a média)
        self.bruto = np.zeros(0)                        # áudio como chegou (para os gráficos)
        self.sincronia = None                           # (índice absoluto, fase, velocidade, ...)
        self.rejeitado_ate = 0                          # candidatos antes daqui já foram descartados
        self.procurado_ate = 0                          # posições antes daqui já foram examinadas
        self.avisos = []                                # eventos para o chat mostrar

    # ---------------------------------------------------------- entrada

    def alimentar(self, bloco):
        """Recebe mais um pedaço de áudio e devolve as mensagens que ficaram completas."""
        bloco = np.asarray(bloco, dtype=float).ravel()
        filtrado, self.zi = sosfilt(self.sos, bloco, zi=self.zi)
        n = self.total + np.arange(len(bloco))
        self.total += len(bloco)
        self.base = np.concatenate([self.base, filtrado * np.exp(-2j * np.pi * self.fc * n / self.fs)])
        self.bruto = np.concatenate([self.bruto, bloco])
        mensagens = []
        while True:
            resultado = self._passo()
            if resultado is None:
                break
            if isinstance(resultado, Mensagem):
                mensagens.append(resultado)
        self._aparar()
        return mensagens

    def pegar_avisos(self):
        avisos, self.avisos = self.avisos, []
        return avisos

    # ---------------------------------------------------------- etapas

    def _posicoes(self, n_bits):
        """Onde começa cada bit, em amostras, contando do início do quadro."""
        return np.round(np.arange(n_bits) * self.amostras_por_bit).astype(int)

    def _medias(self):
        """y[i] = média de base[i : i + 1 bit]: o valor complexo de um bit que começa em i."""
        if len(self.base) < self.janela:
            return np.zeros(0, dtype=complex)
        acumulada = np.concatenate([[0], np.cumsum(self.base)])
        return (acumulada[self.janela:] - acumulada[:-self.janela]) / self.janela

    def _procurar(self, y):
        """Acha o começo da sincronia: onde y "parece" o código de Barker.

        Compara cada bit com o anterior: y[k] · conj(y[k-1]) tem o ângulo da
        DIFERENÇA de fase entre os dois bits (0° se o símbolo repetiu, 180° se
        trocou). Multiplicando por BARKER[k]·BARKER[k-1], na sincronia certa os
        12 termos apontam para o mesmo lado e se somam:
            D(s) = soma de BARKER[k]·BARKER[k-1] · y[s + k bits] · conj(y[s + (k-1) bits])
        Em qualquer outro lugar eles se cancelam. correlação = |D| / soma |y[k]|·|y[k-1]|
        vai de 0 a 1 e não depende do volume, da fase da portadora nem de a fase
        girar devagar (relógios diferentes), porque só olha a diferença entre bits vizinhos.
        Cada candidato ainda passa por _confirmar(). Retorna (índice no buffer,
        fase, velocidade, correlação) ou None se ainda não achou.
        """
        pos = self._posicoes(len(BARKER))
        m = len(y) - pos[-1]                            # posições com os 13 bits completos
        a = max(0, self.procurado_ate - self.inicio)    # o que veio antes já foi examinado
        if m - a <= self.janela:
            return None
        D = np.zeros(m - a, dtype=complex)
        soma = np.zeros(m - a)
        for k in range(1, len(BARKER)):
            atual = y[a + pos[k]:pos[k] + m]
            anterior = y[a + pos[k - 1]:pos[k - 1] + m]
            D += BARKER[k] * BARKER[k - 1] * atual * np.conj(anterior)
            soma += np.abs(atual) * np.abs(anterior)
        correlacao = np.abs(D) / np.maximum(soma, 1e-30)
        C = np.sqrt(np.abs(D))                          # da ordem da amplitude de um bit, x √12
        candidatos = a + np.nonzero((correlacao >= self.limiar) &
                                    (C / np.sqrt(len(BARKER) - 1) >= AMPLITUDE_MINIMA))[0]
        candidatos = candidatos[candidatos >= self.rejeitado_ate - self.inicio]
        while len(candidatos):
            c = candidatos[0]
            if c + self.janela >= m:                    # o pico pode estar logo depois: espera
                self.procurado_ate = self.inicio + c
                return None
            s = c + int(np.argmax(C[c - a:c - a + self.janela]))    # o pico, dentro de 1 bit
            confirmado = self._confirmar(y, s)
            if confirmado:
                return (s,) + confirmado
            self.rejeitado_ate = self.inicio + s + self.janela
            candidatos = candidatos[candidatos >= s + self.janela]
        self.procurado_ate = self.inicio + m - self.janela
        return None

    def _confirmar(self, y, s):
        """Segunda conferência de um candidato a sincronia.

        - Os 13 bits têm força parecida: o PSK tem amplitude constante. Sem isso,
          o fim de uma transmissão (uns bits de portadora seguidos de silêncio)
          "parece" sincronia, porque só os poucos termos fortes contam.
        - Com a fase e o giro descontados, os 13 bits se somam quase perfeitamente
          (correlação > 0,9).
        - A sincronia é bem mais forte que o ruído que havia antes da transmissão.
        Ruído que passou na primeira conferência por acaso quase nunca passa nas três.
        Retorna (fase, velocidade, correlação) ou None.
        """
        forca = np.abs(y[s + self._posicoes(len(BARKER))])
        if np.min(forca) < UNIFORMIDADE * np.max(forca):
            return None
        fase, velocidade, correlacao = self._estimar_fase(y, s)
        if correlacao < self.limiar or not self._acima_do_ruido(y, s):
            return None
        return fase, velocidade, correlacao

    def _estimar_fase(self, y, s):
        """Fase da portadora e quanto ela gira por bit, medidas na sincronia.

        Multiplicando cada bit da sincronia pelo símbolo esperado (±1), sobra só a
        fase da portadora. Se os relógios das duas placas de som forem um pouco
        diferentes, essa fase gira devagar: a reta que passa pelos 13 ângulos dá a
        fase inicial e a velocidade (radianos por bit).
        """
        p = y[s + self._posicoes(len(BARKER))] * BARKER
        angulos = np.unwrap(np.angle(p))
        k = np.arange(len(BARKER))
        velocidade, fase = np.polyfit(k, angulos, 1)
        alinhados = p * np.exp(-1j * (fase + velocidade * k))     # sem a fase e sem o giro
        correlacao = np.abs(alinhados.sum()) / np.sum(np.abs(p))
        return fase, velocidade, correlacao

    def _acima_do_ruido(self, y, s):
        """A sincronia é ACIMA_DO_RUIDO vezes mais forte que o ruído antes da abertura?

        O ruído é medido no trecho do buffer que vem antes da portadora de abertura.
        Se esse trecho for curto demais (a transmissão começou junto com a escuta),
        não dá para medir e a conferência é pulada.
        """
        antes = s - int((ABERTURA + 0.05) * self.fs) - self.janela
        if antes < int(0.1 * self.fs):
            return True
        ruido = np.median(np.abs(y[:antes]))
        sinal = np.mean(np.abs(y[s + self._posicoes(len(BARKER))]))
        return sinal >= ACIMA_DO_RUIDO * ruido

    def _decidir(self, y, s, n_bits, fase, velocidade):
        """Decide os n_bits primeiros bits do quadro, corrigindo fase e tempo a cada bit.

        FASE: gira o valor complexo do bit pela fase estimada; o bit é 0 se a parte
        real for positiva (fase 0°) ou 1 se for negativa (180°). O ângulo que sobra
        depois da decisão é o erro de fase: uma fração dele corrige a fase (ALFA) e
        a velocidade da fase (BETA) para o bit seguinte.

        TEMPO: com relógios diferentes, o começo de cada bit também escorrega aos
        poucos (200 ppm = 4 ms em 20 s, quase meio bit). Para cada bit, olha a média
        um pouco ANTES e um pouco DEPOIS do ponto de leitura: se antes ela é maior,
        o ponto está atrasado e anda para trás (e vice-versa). Só funciona onde o
        bit troca; em sequências iguais a média é a mesma e nada muda.

        Na sincronia os bits são conhecidos, então ela só ajusta. Retorna
        (bits, valores corrigidos, posição de leitura do último bit).
        """
        posicoes = s + self._posicoes(n_bits)
        olhar = max(1, self.janela // 4)                # "um pouco": 1/4 de bit
        atraso = deriva = 0.0                           # em amostras e amostras por bit
        bits, corrigidos = [], []
        p = int(posicoes[0])
        for k in range(n_bits):
            p = int(round(posicoes[k] + atraso))
            p = min(max(p, olhar), len(y) - 1 - olhar)
            giro = np.exp(-1j * fase)
            v = y[p] * giro
            d = BARKER[k] if k < len(BARKER) else (1 if v.real >= 0 else -1)
            erro = np.angle(v * d)
            fase += velocidade + ALFA * erro
            velocidade += BETA * erro
            antes, depois = (y[p - olhar] * giro * d).real, (y[p + olhar] * giro * d).real
            erro_tempo = (depois - antes) / max(abs(v), 1e-30)     # > 0: o pico está depois
            atraso += deriva + GAMA * erro_tempo * self.janela
            deriva += ETA * erro_tempo * self.janela
            limite = DERIVA_MAXIMA * (posicoes[k] - s) + olhar     # relógio nenhum escorrega mais que isso
            atraso = min(max(atraso, -limite), limite)
            bits.append(0 if d > 0 else 1)
            corrigidos.append(v)
        return bits, np.array(corrigidos), p

    def _passo(self):
        """Uma tentativa: acha a sincronia, lê o tamanho e, se tudo já chegou, a mensagem.

        Retorna None (precisa de mais áudio), False (descartou uma sincronia falsa:
        tenta de novo) ou a Mensagem.
        """
        y = self._medias()
        if self.sincronia is None:
            achou = self._procurar(y)
            if achou is None:
                return None
            s, fase, velocidade, correlacao = achou
            self.sincronia = (self.inicio + s, fase, velocidade, correlacao)
            self.avisos.append((f"sincronizou em {(self.inicio + s) / self.fs:.2f} s · correlação "
                                f"{correlacao:.2f} · fase da portadora {np.degrees(fase) % 360:.0f}°"
                                ).replace(".", ","))
        absoluto, fase0, velocidade0, correlacao = self.sincronia
        s = absoluto - self.inicio
        n_cabecalho = len(BARKER) + BITS_CABECALHO
        if s + self._posicoes(n_cabecalho + FOLGA_TEMPO)[-1] >= len(y):
            return None
        bits, _, _ = self._decidir(y, s, n_cabecalho, fase0, velocidade0)
        tamanho, conferencia = bits_para_bytes(bits[len(BARKER):])
        if tamanho ^ conferencia != 0xFF:               # não era uma sincronia de verdade
            self.avisos.append("sincronia falsa (tamanho não confere), descartada")
            self.sincronia = None
            self.rejeitado_ate = absoluto + self.janela
            return False
        n_bits = bits_no_quadro(tamanho)
        if s + self._posicoes(n_bits + FOLGA_TEMPO)[-1] >= len(y):
            return None                                 # a mensagem ainda está chegando
        bits, corrigidos, ultimo = self._decidir(y, s, n_bits, fase0, velocidade0)
        corpo = bits_para_bytes(bits[n_cabecalho:])
        dados, crc = corpo[:tamanho], corpo[tamanho:]
        ok = crc16(dados) == int.from_bytes(crc, "big")
        fim = max(ultimo, s + self._posicoes(n_bits)[-1]) + self.janela
        msg = Mensagem(
            texto=dados.decode("utf-8", errors="replace"), ok=ok, dados=dados, bits=bits,
            simbolos=corrigidos, inicio=absoluto / self.fs, correlacao=correlacao,
            amplitude=float(np.mean(np.abs(corrigidos))), fase=float(np.degrees(fase0) % 360),
            desvio_hz=float(velocidade0 * self.taxa / (2 * np.pi)), snr_db=snr_simbolos(corrigidos),
            audio=self.bruto[max(0, s - int(ABERTURA * self.fs)):fim + int(FIM * self.fs)].copy(),
            trecho=(min(s, int(ABERTURA * self.fs)), min(s, int(ABERTURA * self.fs)) + fim - s),
            fc=self.fc, taxa=self.taxa)
        self.sincronia = None
        self._descartar(fim)
        return msg

    def _descartar(self, ate):
        """Joga fora o buffer até o índice `ate` (já usado)."""
        ate = max(0, min(ate, len(self.base)))
        self.base, self.bruto = self.base[ate:], self.bruto[ate:]
        self.inicio += ate

    def _aparar(self):
        """Sem sincronia, guarda só o último ~1 s: o suficiente para achar a próxima."""
        if self.sincronia is None:
            guardar = int(self.fs * (len(BARKER) / self.taxa + ABERTURA + 0.5))
            if len(self.base) > guardar:
                self._descartar(len(self.base) - guardar)


def snr_simbolos(v, vizinhos=15):
    """SNR medida nos bits: (distância até o zero)² / (espalhamento em volta do ponto)².

    Cada bit é dividido antes pela amplitude média dos ~15 bits em volta dele: o
    microfone do Windows muda o volume sozinho no meio da mensagem (controle
    automático de ganho), e isso não é ruído - a decisão só olha o sinal de ±.
    """
    d = np.sign(v.real)
    d[d == 0] = 1
    local = np.convolve(np.abs(v), np.ones(vizinhos) / vizinhos, mode="same")
    local[:vizinhos // 2] = local[vizinhos // 2]                # bordas: sem média incompleta
    local[-(vizinhos // 2):] = local[-(vizinhos // 2) - 1]
    u = v * d / np.maximum(local, 1e-30)
    ruido = u - np.mean(u.real)
    return float(10 * np.log10(np.mean(u.real) ** 2 / max(np.mean(np.abs(ruido) ** 2), 1e-30)))


def receber(audio, fc=FC, taxa=TAXA, fs=FS, bloco=4410):
    """Demodula um áudio inteiro (de arquivo ou simulado), entregando aos pedaços como o microfone."""
    rx = Receptor(fc, taxa, fs)
    mensagens = []
    for i in range(0, len(audio), bloco):
        mensagens += rx.alimentar(audio[i:i + bloco])
    mensagens += rx.alimentar(np.zeros(int(fs * 0.5)))     # um pouco de silêncio no fim
    return mensagens


# ------------------------------------------------------------------ banda

def banda_teorica(taxa):
    """Lóbulo principal do BPSK com bits retangulares: de fc - taxa a fc + taxa = 2 x taxa.

    Cada bit é um pedaço de senoide de duração T = 1/taxa. Um pulso de duração T
    tem espectro sinc com o primeiro zero em 1/T: quanto mais curto o bit, mais
    largo o espectro. A modulação desloca isso para fc (como no AM), dos dois lados.
    """
    return 2 * taxa


def banda_medida(x, fc, fs=FS, fracao=0.9, vizinhanca=None):
    """Largura B do menor intervalo [fc - B/2, fc + B/2] que contém `fracao` da energia de x.

    Com `vizinhanca` (Hz), só conta a energia até essa distância da portadora: no
    sinal recebido, o zumbido da rede e as vozes da sala ficam de fora da conta.
    """
    potencia = np.abs(np.fft.rfft(x)) ** 2
    distancia = np.abs(np.fft.rfftfreq(len(x), 1 / fs) - fc)
    if vizinhanca is not None:
        potencia, distancia = potencia[distancia <= vizinhanca], distancia[distancia <= vizinhanca]
    ordem = np.argsort(distancia)
    acumulada = np.cumsum(potencia[ordem]) / potencia.sum()
    return 2 * distancia[ordem][np.searchsorted(acumulada, fracao)]


def pico_em(x, fs=FS):
    f, X = espectro(x, fs)
    return f[np.argmax(X)]


# ------------------------------------------------------------------ canal simulado

def canal(sinal, fs=FS, atraso=0.4, ganho=0.2, snr_db=20.0, ppm=0.0, desvio_hz=0.0,
          eco=True, ruido_grave=True, semente=0):
    """Imita o caminho alto-falante -> ar -> microfone, para testar sem dois computadores.

    atraso      silêncio antes (o receptor não sabe quando a mensagem começa)
    ganho       o som chega mais fraco
    ppm         relógios diferentes: a placa do receptor amostra 1 + ppm/10⁶ vezes mais rápido
    desvio_hz   desloca toda a frequência (outra forma de os relógios discordarem)
    eco         duas reflexões na sala (4 ms e 17 ms depois)
    ruido_grave um "zumbido" de 120 Hz e uma voz de fundo (300-900 Hz) fora da banda
    snr_db      ruído branco relativo à potência do sinal recebido
    """
    rng = np.random.default_rng(semente)
    x = np.asarray(sinal, dtype=float)
    if desvio_hz:
        t = np.arange(len(x)) / fs
        x = np.real(hilbert(x) * np.exp(2j * np.pi * desvio_hz * t))
    if ppm:
        n = int(len(x) * (1 + ppm * 1e-6))
        x = np.interp(np.arange(n) / (1 + ppm * 1e-6), np.arange(len(x)), x)
    if eco:
        y = x.copy()
        for atraso_eco, g in ((0.004, 0.3), (0.017, 0.12)):
            k = int(atraso_eco * fs)
            y[k:] += g * x[:-k]
        x = y
    x = ganho * np.concatenate([np.zeros(int(atraso * fs)), x, np.zeros(int(0.3 * fs))])
    potencia = np.mean(x[x != 0] ** 2)
    x = x + rng.normal(0, np.sqrt(potencia / 10 ** (snr_db / 10)), len(x))
    if ruido_grave:
        t = np.arange(len(x)) / fs
        x += 0.5 * ganho * np.sin(2 * np.pi * 120 * t)
        x += 0.3 * ganho * np.sin(2 * np.pi * 300 * t) * np.sin(2 * np.pi * 900 * t + 0.5)
    return x
