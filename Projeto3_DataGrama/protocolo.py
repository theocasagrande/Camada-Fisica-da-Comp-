# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 3 - Protocolo de datagramas (camada de aplicação)
#
# Formato do datagrama, igual para cliente e servidor:
#
#   +--------------------- HEAD (10 bytes) ---------------------+-- payload --+-- EOP --+
#   | tipo(1) | fileId(1) | seq(2) | total(2) | payloadLen(1) | rsv(3) |  0..48 bytes | 4 bytes |
#   +-------------------------------------------------------------+--------------+---------+
#
#   tipo       : que mensagem é essa (handshake, seleção, dados, ack, nack...)
#   fileId     : a qual arquivo o pacote pertence (0xFF = mensagem de controle)
#   seq/total  : número do pacote e total de pacotes do arquivo (usado em DADOS)
#   payloadLen : quantos bytes do payload são válidos
#   EOP        : marca fixa de fim de pacote, usada para conferir se ele chegou inteiro
#
# O head tem 10 bytes fixos, o payload nunca passa de 100 bytes (o máximo
# permitido pelo enunciado) e o EOP tem 4 bytes, então o datagrama nunca
# passa de 10 + 100 + 4 = 114 bytes.
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


Pacote = namedtuple("Pacote", ["tipo", "fileId", "seq", "total", "payload", "eopOk"])


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
    head += bytes(3)  # reservado
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

    resto = receberBytes(com, payloadLen + EOP_SIZE, timeout)
    if resto is None:
        return None

    payload = resto[:payloadLen]
    eopOk   = resto[payloadLen:] == EOP
    return Pacote(tipo, fileId, seq, total, payload, eopOk)
