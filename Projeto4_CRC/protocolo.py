# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 4 - Protocolo de datagramas com CRC-16 e log
#
# Evolução do protocolo do Projeto 3. O datagrama continua o mesmo, mas os
# 2 bytes de verificação do head agora carregam um CRC-16 (e não mais a soma
# simples do Projeto 3), e todo pacote que entra ou sai é registrado em um
# arquivo de log, como pede o enunciado.
#
# Formato do datagrama, igual para cliente e servidor:
#
#   +------------------------- HEAD (10 bytes) -------------------------+- payload -+- EOP -+
#   | tipo(1) | fileId(1) | seq(2) | total(2) | payloadLen(1) | crc(2) | rsv(1) | 0..100 B | 4 B |
#   +--------------------------------------------------------------------------+-----------+-----+
#
#   tipo       : que mensagem é essa (handshake, seleção, dados, ok, erro...)
#   fileId     : a qual arquivo o pacote pertence (0xFF = mensagem de controle)
#   seq/total  : número do pacote e total de pacotes do arquivo (usado em DADOS)
#   payloadLen : quantos bytes do payload são válidos
#   crc        : CRC-16 do PAYLOAD (apenas do payload), como pede o enunciado
#   EOP        : marca fixa de fim de pacote, usada para conferir se ele chegou inteiro
#
# O head tem 10 bytes fixos, o payload nunca passa de 100 bytes (o máximo
# permitido pelo enunciado do Projeto 3) e o EOP tem 4 bytes, então o
# datagrama nunca passa de 10 + 100 + 4 = 114 bytes.
#
# Verificação de integridade: são duas conferências independentes.
#   - o EOP diz se o pacote terminou no lugar certo (enquadramento);
#   - o CRC-16 diz se os bytes do payload chegaram intactos (conteúdo).
# Um pacote só é aceito se as duas baterem.
#
# Resincronização: se o corpo de um pacote não chegar por completo a tempo
# (ex.: o fio entre os Arduinos foi desconectado no meio da recepção), ou se
# o EOP não bater, os bytes que sobrarem no buffer deixam de ser o início de
# um pacote válido. Nesses casos, resincronizar() descarta bytes até achar a
# próxima marca EOP, para que o head seguinte volte a ser lido do lugar
# certo (veja receberPacote).
####################################################

import binascii
import os
import time
from collections import namedtuple
from datetime import datetime

# ---- Tamanhos e marca de fim de pacote ------------------------------------
HEAD_SIZE   = 10
EOP         = bytes([0xAA, 0x55, 0xAA, 0x55])
EOP_SIZE    = len(EOP)
PAYLOAD_MAX = 100

FILE_ID_CONTROLE = 0xFF

# ---- Tipos de pacote -------------------------------------------------------
# Atenção: no Projeto 4 quem ENVIA os arquivos é o cliente (upload), ao
# contrário do Projeto 3. O enunciado é explícito nisso: "caso o lado que
# recebe o pacote (server) detecte uma incoerência entre o CRC enviado e o
# CRC calculado" e "transmissão com erro na ordem dos pacotes enviados pelo
# client".
HELLO      = 0x01   # cliente  -> servidor : "está vivo? vou te enviar arquivos"
PRONTO     = 0x02   # servidor -> cliente  : "estou vivo, pode escolher"
SELECIONAR = 0x03   # cliente  -> servidor : nome do arquivo que será enviado
CONFIRMAR  = 0x04   # servidor -> cliente  : confirma escolha, pergunta se quer mais
RESPOSTA   = 0x05   # cliente  -> servidor : "S" ou "N" para a pergunta acima
INICIAR    = 0x06   # servidor -> cliente  : pode começar a transmissão
DADOS      = 0x07   # cliente  -> servidor : pedaço de um arquivo
OK         = 0x08   # servidor -> cliente  : "sem incoerências, pode mandar o próximo"
ERRO       = 0x09   # servidor -> cliente  : "erro de CRC / de ordem, reenvie o pacote"
SUCESSO    = 0x0B   # servidor -> cliente  : todos os arquivos chegaram inteiros
PAUSAR     = 0x0C   # cliente  -> servidor : pausei a transmissão
RETOMAR    = 0x0D   # cliente  -> servidor : retomei a transmissão
ABORTAR    = 0x0E   # cliente <-> servidor : aborta a transmissão

NOMES_TIPO = {
    HELLO: "HELLO", PRONTO: "PRONTO", SELECIONAR: "SELECIONAR",
    CONFIRMAR: "CONFIRMAR", RESPOSTA: "RESPOSTA", INICIAR: "INICIAR",
    DADOS: "DADOS", OK: "OK", ERRO: "ERRO", SUCESSO: "SUCESSO",
    PAUSAR: "PAUSAR", RETOMAR: "RETOMAR", ABORTAR: "ABORTAR",
}

# Motivos de um pacote ERRO, enviados no payload para o log ficar legível.
MOTIVO_CRC    = "CRC"
MOTIVO_ORDEM  = "ORDEM"
MOTIVO_EOP    = "EOP"


def nomeTipo(tipo):
    return NOMES_TIPO.get(tipo, "0x{:02X}".format(tipo))


# ---- Tempos de espera e tentativas -----------------------------------------
TIMEOUT_PACOTE          = 2    # segundos: espera por resposta durante a transmissão
TIMEOUT_HANDSHAKE       = 10   # segundos: espera por resposta durante handshake/seleção
MAX_TENTATIVAS_CONTEUDO = 8    # tentativas de reenvio por ERRO antes de desistir


class Abortado(Exception):
    """Sinaliza que a transmissão foi abortada (pelo usuário ou por erro)."""
    pass


Pacote = namedtuple("Pacote", ["tipo", "fileId", "seq", "total", "payload", "eopOk", "crcOk", "crc"])


# ---- CRC-16 ------------------------------------------------------------------
def calcularCRC(payload):
    """CRC-16 do payload.

    O enunciado diz para NÃO implementar o algoritmo à mão, e sim usar uma
    biblioteca. Usamos binascii.crc_hqx, da biblioteca padrão do Python, que
    é o CRC-16/XMODEM (polinômio 0x1021, valor inicial 0x0000) — o mesmo CRC
    de 16 bits usado pelo protocolo XMODEM. Vantagem de estar na biblioteca
    padrão: não precisa instalar nada com pip nas duas máquinas.

    Conferência rápida: crc_hqx(b"123456789", 0) == 0x31C3, que é o valor de
    referência publicado para o CRC-16/XMODEM.
    """
    return binascii.crc_hqx(payload, 0x0000)


# ---- Log da transmissão ------------------------------------------------------
# O enunciado pede um arquivo txt, dos dois lados, com uma linha para cada
# pacote enviado ou recebido. Para não depender de o programador lembrar de
# chamar o log em cada ponto do código, o registro é feito automaticamente
# dentro de enviarPacote() e receberPacote(): todo pacote que passa pelo
# protocolo aparece no arquivo.
_logArquivo = None
_logLado    = ""


def iniciarLog(lado, cenario, pasta=None):
    """Abre o arquivo de log deste lado da comunicação.

    'lado' é "cliente" ou "servidor", e 'cenario' é o nome do teste que está
    sendo feito (sucesso, erro_crc, erro_ordem, desconexao). Assim cada
    cenário do enunciado gera um par de arquivos separado, e dá para comparar
    o log do cliente com o do servidor lado a lado.
    """
    global _logArquivo, _logLado
    fecharLog()

    if pasta is None:
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(pasta, exist_ok=True)

    caminho = os.path.join(pasta, "log_{}_{}.txt".format(lado, cenario))
    _logArquivo = open(caminho, "w", encoding="utf-8")
    _logLado    = lado
    _logArquivo.write("# Log da transmissao - lado {} - cenario '{}' - {}\n".format(
        lado, cenario, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    _logArquivo.write("# instante / envio-receb / tipo / bytes totais"
                      " / pacote / total de pacotes / CRC do payload / observacao\n")
    _logArquivo.flush()
    return caminho


def fecharLog():
    global _logArquivo
    if _logArquivo is not None:
        _logArquivo.close()
        _logArquivo = None


def registrarLog(direcao, tipo, tamanhoTotal, seq=None, total=None, crc=None, observacao=""):
    """Escreve uma linha no log. Formato, no espírito do exemplo do enunciado:

        10/09/2026 13:34:23.089 / envio / DADOS(0x07) / 114 / 1 / 23 / F23F
        10/09/2026 13:34:23.230 / receb / OK(0x08) / 14

    Os campos de pacote/total/CRC só aparecem em pacotes do tipo DADOS, que é
    exatamente o que o enunciado pede ("se for pacote do tipo dados").
    """
    if _logArquivo is None:
        return

    instante = datetime.now().strftime("%d/%m/%Y %H:%M:%S.") + "{:03d}".format(
        int((time.time() % 1) * 1000))
    campos = [instante, direcao, "{}(0x{:02X})".format(nomeTipo(tipo), tipo), str(tamanhoTotal)]
    if tipo == DADOS:
        campos += [str(seq), str(total), "{:04X}".format(crc)]
    if observacao:
        campos.append(observacao)

    _logArquivo.write(" / ".join(campos) + "\n")
    _logArquivo.flush()   # flush a cada linha: se o professor puxar o fio (ou
                          # o programa for interrompido), o log já está no disco


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
    head += calcularCRC(payload).to_bytes(2, "big")
    head += bytes(1)  # reservado
    return head + payload + EOP


def montarControle(tipo, texto=""):
    """Atalho para mensagens sem arquivo associado (handshake, seleção, ok/erro de controle...)."""
    return montarPacote(tipo, FILE_ID_CONTROLE, 0, 0, texto)


def lerCampos(pacote):
    """Lê tipo/seq/total/CRC de um datagrama já montado (bytes), para o log."""
    return (pacote[0],
            int.from_bytes(pacote[2:4], "big"),
            int.from_bytes(pacote[4:6], "big"),
            int.from_bytes(pacote[7:9], "big"))


def enviarPacote(com, pacote, observacao=""):
    com.sendData(pacote)
    enviados = com.tx.getStatus()
    tipo, seq, total, crc = lerCampos(pacote)
    registrarLog("envio", tipo, len(pacote), seq, total, crc, observacao)
    return enviados


# ---- Leitura de pacotes, com time out ---------------------------------------
def receberBytes(com, quantidade, timeout):
    """Lê 'quantidade' bytes do buffer de recepção, devolvendo None se o tempo
    acabar antes de todos os bytes chegarem (timeout=None espera para sempre).
    Usa só métodos que já existem na camada de enlace.
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
            # A linha ficou em silêncio sem que o EOP aparecesse. Além do caso
            # óbvio (o fio ainda está fora), isso acontece quando a desconexão
            # cortou um byte pela METADE: a camada física transmite tudo em
            # hexadecimal (2 caracteres por byte) e guarda em rxRemain o
            # caractere ímpar que sobrou. Enquanto essa meia-sobra estiver lá,
            # todo byte remontado sai deslocado em 4 bits e NENHUM EOP volta a
            # aparecer — o protocolo nunca mais se recupera sozinho.
            # Com a linha em silêncio, o que estiver pendente só pode ser lixo,
            # então descartar é seguro e devolve o alinhamento dos bytes.
            com.fisica.rxRemain = b""
            com.rx.clearBuffer()
            return False
        janela = (janela + byte)[-EOP_SIZE:]
        descartados += 1
        if janela == EOP:
            return True
    return False


def pedir(com, pacote, tiposEsperados, timeout=TIMEOUT_PACOTE, tentativas=30):
    """Envia um pacote e espera uma resposta de um dos tipos esperados,
    REENVIANDO o pedido a cada time out.

    É o que torna o handshake tão robusto quanto a transmissão de dados: sem
    isso, se o fio fosse desconectado bem durante a negociação, uma única
    mensagem perdida (um CONFIRMAR, um INICIAR) já encerrava a sessão, mesmo
    que o fio voltasse logo em seguida. Com o reenvio, o cliente insiste por
    timeout x tentativas segundos (60s no padrão) e a conversa continua de
    onde parou assim que a linha volta.

    Respostas corrompidas ou de tipo inesperado (ex.: a duplicata de um
    CONFIRMAR que já tínhamos recebido) são descartadas sem gastar tentativa.
    Devolve o Pacote recebido, ou None se desistir.
    """
    for _ in range(tentativas):
        enviarPacote(com, pacote)
        while True:
            resposta = receberPacote(com, timeout)
            if resposta is None:
                break                      # time out: sai para reenviar o pedido
            if not (resposta.eopOk and resposta.crcOk):
                continue
            if resposta.tipo == ABORTAR:
                raise Abortado()
            if resposta.tipo in tiposEsperados:
                return resposta
    return None


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
    crcRx      = int.from_bytes(head[7:9], "big")

    if payloadLen > PAYLOAD_MAX:
        # Nenhum pacote legítimo declara mais de 100 bytes de payload, então
        # esse head é lixo (bytes deslocados depois de uma desconexão). Sem
        # essa checagem ficaríamos esperando até 255 bytes que nunca vêm, um
        # time out inteiro perdido a cada tentativa.
        resincronizar(com)
        return None

    resto = receberBytes(com, payloadLen + EOP_SIZE, timeout)
    if resto is None:
        # o head já foi consumido, mas o resto do pacote não chegou a tempo
        # (conexão pode ter caído no meio); tenta realinhar o fluxo antes
        # de devolver o time out ao chamador.
        resincronizar(com)
        return None

    payload = resto[:payloadLen]
    eopOk   = resto[payloadLen:] == EOP
    crcCalc = calcularCRC(payload)
    crcOk   = crcCalc == crcRx

    if not eopOk:
        # o head lido provavelmente não era o início real de um pacote;
        # realinha o fluxo achando o próximo EOP antes de devolver o erro.
        resincronizar(com)

    if not eopOk:
        observacao = "EOP INVALIDO"
    elif not crcOk:
        observacao = "CRC INVALIDO (recebido {:04X}, calculado {:04X})".format(crcRx, crcCalc)
    else:
        observacao = ""

    registrarLog("receb", tipo, HEAD_SIZE + len(resto), seq, total, crcRx, observacao)

    return Pacote(tipo, fileId, seq, total, payload, eopOk, crcOk, crcRx)
