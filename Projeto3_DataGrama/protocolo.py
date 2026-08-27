# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 3 - Protocolo de datagramas (camada de aplicação)
#
# Formato do datagrama, igual para cliente e servidor:
#
#   +----------------------- HEAD (10 bytes) -----------------------+-- payload --+-- EOP --+
#   | tipo(1) | fileId(1) | seq(2) | total(2) | payloadLen(1) | checksum(2) | rsv(1) |  0..100 bytes | 4 bytes |
#   +---------------------------------------------------------------------------------+--------------+---------+
#
#   tipo       : que mensagem é essa (handshake, seleção, dados, ack, nack...)
#   fileId     : a qual arquivo o pacote pertence (0xFF = mensagem de controle)
#   seq/total  : número do pacote e total de pacotes do arquivo (usado em DADOS)
#   payloadLen : quantos bytes do payload são válidos
#   checksum   : soma de verificação (estilo Internet checksum) do payload
#   EOP        : marca fixa de fim de pacote, usada para conferir se ele chegou inteiro
#
# O head tem 10 bytes fixos, o payload nunca passa de 100 bytes (o máximo
# permitido pelo enunciado) e o EOP tem 4 bytes, então o datagrama nunca
# passa de 10 + 100 + 4 = 114 bytes.
#
# Verificação de integridade: além do EOP (confere se o pacote terminou no
# lugar certo), cada pacote carrega um checksum do payload, recalculado na
# recepção. Um pacote só é aceito se as duas conferências baterem.
#
# Resincronização: se o corpo de um pacote não chegar por completo a tempo
# (ex.: o fio entre os Arduinos foi desconectado no meio da recepção), ou se
# o EOP não bater, os bytes que sobrarem no buffer deixam de ser o início de
# um pacote válido. Nesses casos, resincronizar() descarta bytes até achar a
# próxima marca EOP, para que o head seguinte volte a ser lido do lugar
# certo (veja receberPacote).
####################################################

import time
from collections import namedtuple

# ---- Tamanhos e marca de fim de pacote ------------------------------------
HEAD_SIZE   = 10
EOP         = bytes([0xAA, 0x55, 0xAA, 0x55])
EOP_SIZE    = len(EOP)
PAYLOAD_MAX = 100

FILE_ID_CONTROLE = 0xFF

# ---- Tipos de pacote -------------------------------------------------------
HELLO      = 0x01   # cliente  -> servidor : "está vivo? quais arquivos tem?"
LISTA      = 0x02   # servidor -> cliente  : nomes dos arquivos disponíveis
SELECIONAR = 0x03   # cliente  -> servidor : nome do arquivo escolhido
CONFIRMAR  = 0x04   # servidor -> cliente  : confirma escolha, pergunta se quer mais
RESPOSTA   = 0x05   # cliente  -> servidor : "S" ou "N" para a pergunta acima
INICIAR    = 0x06   # servidor -> cliente  : vai começar a transmissão
DADOS      = 0x07   # servidor -> cliente  : pedaço de um arquivo
ACK        = 0x08   # cliente  -> servidor : pacote de dados recebido com sucesso
NACK       = 0x09   # cliente  -> servidor : pacote de dados veio errado, reenvie
SUCESSO    = 0x0B   # servidor -> cliente  : todos os arquivos foram transmitidos
PAUSAR     = 0x0C   # cliente  -> servidor : pausar a transmissão
RETOMAR    = 0x0D   # cliente  -> servidor : retomar a transmissão pausada
ABORTAR    = 0x0E   # cliente <-> servidor : aborta a transmissão

NOMES_TIPO = {
    HELLO: "HELLO", LISTA: "LISTA", SELECIONAR: "SELECIONAR",
    CONFIRMAR: "CONFIRMAR", RESPOSTA: "RESPOSTA", INICIAR: "INICIAR",
    DADOS: "DADOS", ACK: "ACK", NACK: "NACK", SUCESSO: "SUCESSO",
    PAUSAR: "PAUSAR", RETOMAR: "RETOMAR", ABORTAR: "ABORTAR",
}


def nomeTipo(tipo):
    return NOMES_TIPO.get(tipo, "0x{:02X}".format(tipo))


# ---- Tempos de espera e tentativas -----------------------------------------
TIMEOUT_PACOTE          = 2    # segundos: espera por resposta durante a transmissão
TIMEOUT_HANDSHAKE       = 10   # segundos: espera por resposta durante handshake/seleção
MAX_TENTATIVAS_CONTEUDO = 5    # tentativas de reenvio por NACK antes de desistir


class Abortado(Exception):
    """Sinaliza que a transmissão foi abortada (pelo usuário ou por erro)."""
    pass


Pacote = namedtuple("Pacote", ["tipo", "fileId", "seq", "total", "payload", "eopOk", "checksumOk"])


# ---- Checksum ----------------------------------------------------------------
def calcularChecksum(payload):
    """Internet checksum (soma em complemento de 1, palavras de 16 bits) do
    payload. Mesma ideia do campo 'checksum' do cabeçalho TCP mostrado na
    teoria: detecta corrupção de bytes que o EOP sozinho não pegaria (o EOP
    só confere se o pacote terminou no lugar certo, não se os bytes do meio
    vieram intactos).
    """
    dados = payload if len(payload) % 2 == 0 else payload + b"\x00"
    total = 0
    for i in range(0, len(dados), 2):
        total += (dados[i] << 8) | dados[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


# ---- Montagem e envio de pacotes -------------------------------------------
def montarPacote(tipo, fileId=FILE_ID_CONTROLE, seq=0, total=0, payload=b""):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if len(payload) > PAYLOAD_MAX:
        raise ValueError("payload de {} bytes excede o limite de {} bytes".format(len(payload), PAYLOAD_MAX))

    head = bytes([tipo & 0xFF, fileId & 0xFF])
    head += seq.to_bytes(2, "big")
    head += total.to_bytes(2, "big")
    head += bytes([len(payload)])
    head += calcularChecksum(payload).to_bytes(2, "big")
    head += bytes(1)  # reservado
    return head + payload + EOP


def montarControle(tipo, texto=""):
    """Atalho para mensagens sem arquivo associado (handshake, seleção, ack de controle...)."""
    return montarPacote(tipo, FILE_ID_CONTROLE, 0, 0, texto)


def enviarPacote(com, pacote):
    com.sendData(pacote)
    return com.tx.getStatus()


# ---- Leitura de pacotes, com time out ---------------------------------------
def receberBytes(com, quantidade, timeout):
    """Lê 'quantidade' bytes do buffer de recepção, devolvendo None se o tempo
    acabar antes de todos os bytes chegarem (timeout=None espera para sempre).
    Usa só métodos que já existem na camada de enlace, sem alterá-la.
    """
    inicio = time.time()
    while com.rx.getBufferLen() < quantidade:
        if timeout is not None and time.time() - inicio > timeout:
            return None
        time.sleep(0.02)
    return com.rx.getBuffer(quantidade)


def resincronizar(com, limiteBytes=4096):
    """Descarta bytes do buffer até encontrar (e consumir) a marca EOP,
    assumindo que o próximo pacote completo começa logo em seguida.

    Necessário porque receberPacote() já consome o head do buffer antes de
    saber se o resto do pacote vai chegar certo. Se o corpo não chegar a
    tempo (ex.: o fio foi desconectado bem no meio da recepção do payload)
    ou o EOP não bater (o head lido era, na verdade, lixo/bytes deslocados),
    o que sobrou no buffer não é mais o início de um pacote válido — sem
    essa resincronização, a próxima leitura interpretaria esse lixo como um
    head novo e o protocolo nunca mais se recuperaria sozinho depois de uma
    desconexão. Devolve True se achou o EOP (fluxo realinhado) ou False se
    não achou dentro do limite (ex.: ainda sem conexão; tenta de novo depois).
    """
    janela = b""
    descartados = 0
    while descartados < limiteBytes:
        byte = receberBytes(com, 1, 1)
        if byte is None:
            return False
        janela = (janela + byte)[-EOP_SIZE:]
        descartados += 1
        if janela == EOP:
            return True
    return False


def receberPacote(com, timeout):
    """Lê um datagrama completo: primeiro o head (tamanho fixo), depois o
    payload + EOP (tamanho que o próprio head informou). Devolve um 'Pacote'
    (namedtuple) ou None em caso de time out.
    """
    head = receberBytes(com, HEAD_SIZE, timeout)
    if head is None:
        return None

    tipo       = head[0]
    fileId     = head[1]
    seq        = int.from_bytes(head[2:4], "big")
    total      = int.from_bytes(head[4:6], "big")
    payloadLen = head[6]
    checksumRx = int.from_bytes(head[7:9], "big")

    resto = receberBytes(com, payloadLen + EOP_SIZE, timeout)
    if resto is None:
        # o head já foi consumido, mas o resto do pacote não chegou a tempo
        # (conexão pode ter caído no meio); tenta realinhar o fluxo antes
        # de devolver o time out ao chamador.
        resincronizar(com)
        return None

    payload    = resto[:payloadLen]
    eopOk      = resto[payloadLen:] == EOP
    checksumOk = calcularChecksum(payload) == checksumRx

    if not eopOk:
        # o head lido provavelmente não era o início real de um pacote;
        # realinha o fluxo achando o próximo EOP antes de devolver o erro.
        resincronizar(com)

    return Pacote(tipo, fileId, seq, total, payload, eopOk, checksumOk)
