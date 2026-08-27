# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 3 - Aplicação CLIENTE
#
# Conecta ao servidor, pergunta quais arquivos estão disponíveis, escolhe
# 2 ou mais para baixar e recebe todos simultaneamente (pacotes alternados
# entre os arquivos), confirmando (ACK) ou pedindo reenvio (NACK) de cada
# pacote recebido. Os arquivos são salvos em arquivosRecebidos/.
#
# Durante a transmissão, o usuário pode apertar uma tecla a qualquer
# momento:
#   p = pausar     r = retomar     a = abortar
#
# IMPORTANTE: o servidor deve ser iniciado ANTES do cliente.
#####################################################

from enlace import *
from protocolo import *
import os
import time
import msvcrt

# Porta serial deste computador.
# Para descobrir: python -m serial.tools.list_ports
serialName = "COM7"

baseDir = os.path.dirname(os.path.abspath(__file__))
pastaRecebidos = os.path.join(baseDir, "arquivosRecebidos")


def teclaPressionada():
    """Devolve a tecla pressionada (minúscula), sem bloquear, ou None."""
    if msvcrt.kbhit():
        try:
            return msvcrt.getch().decode().lower()
        except UnicodeDecodeError:
            return None
    return None


def escolherArquivos(com):
    pacote = receberPacote(com, TIMEOUT_HANDSHAKE)
    if pacote is None or pacote.tipo != LISTA:
        print("Servidor não respondeu ao handshake.")
        return []

    escolhidos = []
    while True:
        disponiveis = [n for n in pacote.payload.decode("utf-8", errors="replace").split(";") if n]
        if not disponiveis:
            print("Não há mais arquivos disponíveis no servidor.")
            break

        print("\nArquivos disponíveis no servidor:")
        for i, nome in enumerate(disponiveis, start=1):
            print("  {}) {}".format(i, nome))

        nome = None
        while nome is None:
            escolha = input("Escolha o número do arquivo desejado: ").strip()
            try:
                nome = disponiveis[int(escolha) - 1]
            except (ValueError, IndexError):
                print("Opção inválida, tente novamente.")

        enviarPacote(com, montarControle(SELECIONAR, nome))
        pacote = receberPacote(com, TIMEOUT_HANDSHAKE)
        if pacote is None:
            print("Servidor não respondeu.")
            return []

        if pacote.tipo == LISTA:
            print("Servidor recusou a escolha (arquivo indisponível). Tente novamente.")
            continue

        if pacote.tipo != CONFIRMAR:
            print("Resposta inesperada do servidor ({}).".format(nomeTipo(pacote.tipo)))
            return []

        escolhidos.append(nome)
        print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))

        resp = input("Adicionar outro arquivo? (S/N): ").strip().upper()
        querMais = resp.startswith("S")
        enviarPacote(com, montarControle(RESPOSTA, "S" if querMais else "N"))

        pacote = receberPacote(com, TIMEOUT_HANDSHAKE)
        if pacote is None:
            print("Servidor não respondeu.")
            return []

        if pacote.tipo == INICIAR:
            print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))
            return escolhidos

        if pacote.tipo != LISTA:
            print("Resposta inesperada do servidor ({}).".format(nomeTipo(pacote.tipo)))
            return []
        # senão, 'pacote' já é a lista atualizada: volta ao topo do laço para escolher mais um


def receberArquivos(com, nomes):
    arquivos = {}
    for fileId, nome in enumerate(nomes):
        arquivos[fileId] = {"nome": nome, "dados": bytearray(), "seq": 0, "total": 0, "pacotesRecebidos": 0}

    ativos = set(arquivos.keys())
    inicio = time.time()
    pausado = False

    print("\nRecebendo {} arquivo(s) simultaneamente...".format(len(nomes)))
    print("(durante a transmissão: 'p' pausa, 'r' retoma, 'a' aborta)")

    while ativos:
        tecla = teclaPressionada()

        if not pausado and tecla == "p":
            print("\n[tecla 'p'] Pausando a transmissão...")
            enviarPacote(com, montarControle(PAUSAR))
            pausado = True
            print("Pausado. Pressione 'r' para retomar ou 'a' para abortar.")
            continue

        if tecla == "a":
            print("\n[tecla 'a'] Abortando a transmissão...")
            enviarPacote(com, montarControle(ABORTAR))
            raise Abortado()

        if pausado:
            if tecla == "r":
                print("\n[tecla 'r'] Retomando a transmissão...")
                enviarPacote(com, montarControle(RETOMAR))
                pausado = False
            else:
                time.sleep(0.05)
                continue

        pacote = receberPacote(com, TIMEOUT_PACOTE)
        if pacote is None:
            print("  sem dados em {}s (conexão pode estar interrompida); aguardando...".format(TIMEOUT_PACOTE))
            continue

        if pacote.tipo == ABORTAR:
            print("\nServidor abortou a transmissão: {}".format(pacote.payload.decode("utf-8", errors="replace")))
            raise Abortado()

        if pacote.tipo != DADOS:
            print("  mensagem inesperada recebida ({}), ignorando.".format(nomeTipo(pacote.tipo)))
            continue

        arq = arquivos.get(pacote.fileId)
        if arq is None:
            continue

        seqEsperado = arq["seq"] + 1
        if pacote.seq == seqEsperado and pacote.eopOk:
            arq["dados"] += pacote.payload
            arq["seq"] = pacote.seq
            arq["total"] = pacote.total
            arq["pacotesRecebidos"] += 1
            enviarPacote(com, montarPacote(ACK, pacote.fileId, pacote.seq, pacote.total))
            print("  <- '{}' pacote {}/{} recebido e confirmado ({} bytes)".format(
                arq["nome"], pacote.seq, pacote.total, len(pacote.payload)))

            if pacote.seq >= pacote.total:
                ativos.discard(pacote.fileId)
                print("  Arquivo '{}' recebido por completo.".format(arq["nome"]))

        elif pacote.seq == arq["seq"] and pacote.eopOk:
            # pacote repetido: nosso ACK anterior deve ter se perdido. Não duplica
            # os dados, só confirma de novo para o servidor seguir em frente.
            enviarPacote(com, montarPacote(ACK, pacote.fileId, pacote.seq, pacote.total))
            print("  <- '{}' pacote {} repetido (ACK anterior deve ter se perdido); reenviando ACK".format(
                arq["nome"], pacote.seq))

        else:
            motivo = "ordem incorreta" if pacote.seq != seqEsperado else "EOP inválido"
            print("  pacote de '{}' rejeitado ({}); pedindo reenvio do pacote {}...".format(
                arq["nome"], motivo, seqEsperado))
            enviarPacote(com, montarPacote(NACK, pacote.fileId, seqEsperado, pacote.total))

    duracao = time.time() - inicio

    pacote = receberPacote(com, TIMEOUT_PACOTE)
    if pacote is not None and pacote.tipo == SUCESSO:
        print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))

    os.makedirs(pastaRecebidos, exist_ok=True)
    print("\n" + "=" * 60)
    print("RESUMO DA TRANSMISSÃO (cliente)")
    print("=" * 60)
    for arq in arquivos.values():
        caminho = os.path.join(pastaRecebidos, arq["nome"])
        with open(caminho, "wb") as f:
            f.write(arq["dados"])
        print("  {:<20s} {:>8d} bytes  {:>5d} pacotes  -> {}".format(
            arq["nome"], len(arq["dados"]), arq["pacotesRecebidos"], caminho))
    print("  Tempo total: {:.1f}s".format(duracao))
    print("=" * 60)


def main():
    com1 = None
    try:
        print("Iniciando o cliente")
        com1 = enlace(serialName)
        com1.enable()
        print("Comunicação aberta em {}".format(serialName))
        com1.rx.clearBuffer()

        print("\nEnviando handshake para o servidor...")
        enviarPacote(com1, montarControle(HELLO))

        nomes = escolherArquivos(com1)
        if nomes:
            receberArquivos(com1, nomes)

        print("\nComunicação encerrada")
        com1.disable()

    except Abortado:
        print("\nTransmissão abortada.")
        if com1 is not None:
            com1.disable()

    except Exception as erro:
        print("ops! :-\\")
        print(erro)
        if com1 is not None:
            com1.disable()


if __name__ == "__main__":
    main()
