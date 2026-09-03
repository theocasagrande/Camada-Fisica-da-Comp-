# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 3 - Aplicação SERVIDOR
#
# Oferece os arquivos da pasta arquivosServidor/ para download. Faz o
# handshake, negocia com o cliente quais arquivos serão baixados e então
# transmite todos os arquivos escolhidos simultaneamente (pacotes alternados
# entre os arquivos), em datagramas, sempre esperando a confirmação (ACK)
# de um pacote antes de enviar o próximo.
#
# IMPORTANTE: o servidor deve ser iniciado ANTES do cliente.
#####################################################

from enlace import *
from protocolo import *
import os
import math
import time

# Porta serial deste computador.
# Para descobrir: python -m serial.tools.list_ports
serialName = "COM7"

baseDir = os.path.dirname(os.path.abspath(__file__))
pastaArquivos = os.path.join(baseDir, "arquivosServidor")


def listarArquivos():
    return sorted(
        nome for nome in os.listdir(pastaArquivos)
        if os.path.isfile(os.path.join(pastaArquivos, nome))
    )


def formatarLista(nomes):
    """'a.txt' / "'a.txt' e 'b.png'" / "'a.txt', 'b.png' e 'c.bin'" """
    citados = ["'{}'".format(nome) for nome in nomes]
    if len(citados) == 1:
        return citados[0]
    return "{} e {}".format(", ".join(citados[:-1]), citados[-1])


def montarMensagemEscolha(escolhidos):
    """"Arquivo 'x' escolhido, deseja adicionar outro arquivo? (S/N)" ou, com
    mais de um, "Arquivo 'x' e 'y' escolhidos, deseja adicionar outro
    arquivo? (S/N)", citando o nome de todos os arquivos já escolhidos até
    agora (como pede o enunciado). Se a lista de nomes ficar grande demais
    para caber no payload (100 bytes), cai para uma versão resumida em vez
    de estourar o limite.
    """
    verbo = "escolhido" if len(escolhidos) == 1 else "escolhidos"
    texto = "Arquivo {} {}, deseja adicionar outro arquivo? (S/N)".format(formatarLista(escolhidos), verbo)
    if len(texto.encode("utf-8")) <= PAYLOAD_MAX:
        return texto
    return "Arquivo '{}' também escolhido ({} arquivos no total). Deseja adicionar outro arquivo? (S/N)".format(
        escolhidos[-1], len(escolhidos))


def atenderCliente(com):
    print("\nAguardando handshake de um cliente... (Ctrl+C para encerrar)")
    pacote = receberPacote(com, None)
    if pacote is None or pacote.tipo != HELLO:
        print("Pacote inesperado recebido antes do handshake, ignorando.")
        return

    print("Cliente conectado! Enviando lista de arquivos disponíveis.")
    disponiveis = listarArquivos()
    escolhidos = []
    enviarPacote(com, montarControle(LISTA, ";".join(disponiveis)))

    # ---- diálogo de seleção de arquivos ----
    while True:
        pacote = receberPacote(com, None)
        if pacote is None:
            print("Cliente não respondeu durante a seleção. Encerrando atendimento.")
            return
        if pacote.tipo == ABORTAR:
            print("Cliente abortou durante a seleção de arquivos.")
            return
        if pacote.tipo != SELECIONAR:
            print("Mensagem inesperada durante a seleção ({}), ignorando.".format(nomeTipo(pacote.tipo)))
            continue

        nome = pacote.payload.decode("utf-8", errors="replace")
        restantes = [f for f in disponiveis if f not in escolhidos]
        if nome not in restantes:
            print("Cliente pediu um arquivo indisponível: '{}'. Reenviando lista.".format(nome))
            enviarPacote(com, montarControle(LISTA, ";".join(restantes)))
            continue

        escolhidos.append(nome)
        print("Cliente escolheu '{}'. Escolhidos até agora: {}".format(nome, formatarLista(escolhidos)))

        enviarPacote(com, montarControle(CONFIRMAR, montarMensagemEscolha(escolhidos)))

        pacote = receberPacote(com, None)
        if pacote is None:
            print("Cliente não respondeu durante a seleção. Encerrando atendimento.")
            return
        if pacote.tipo == ABORTAR:
            print("Cliente abortou durante a seleção de arquivos.")
            return

        querMais = (pacote.tipo == RESPOSTA and pacote.payload[:1].upper() == b"S")
        if querMais:
            restantes = [f for f in disponiveis if f not in escolhidos]
            enviarPacote(com, montarControle(LISTA, ";".join(restantes)))
            continue
        else:
            break

    print("\nSeleção concluída: {}".format(formatarLista(escolhidos)))
    enviarPacote(com, montarControle(
        INICIAR, "Entendido. Vou iniciar a transmissão simultânea dos arquivos escolhidos."))

    transmitirArquivos(com, escolhidos)


def aguardarRetomada(com):
    """Bloqueia até o cliente mandar RETOMAR (ou ABORTAR), enquanto pausado."""
    while True:
        resposta = receberPacote(com, None)
        if resposta is None:
            continue
        if resposta.tipo == RETOMAR:
            return
        if resposta.tipo == ABORTAR:
            print("\nCliente abortou durante a pausa.")
            raise Abortado()


def transmitirArquivos(com, nomes):
    arquivos = []
    for fileId, nome in enumerate(nomes):
        caminho = os.path.join(pastaArquivos, nome)
        with open(caminho, "rb") as f:
            dados = f.read()
        total = max(1, math.ceil(len(dados) / PAYLOAD_MAX))
        arquivos.append({
            "id": fileId, "nome": nome, "dados": dados,
            "total": total, "seq": 1, "pacotesEnviados": 0,
        })
        print("  [{}] {} - {} bytes - {} pacotes".format(fileId, nome, len(dados), total))

    ativos = list(range(len(arquivos)))
    inicio = time.time()
    print("\nIniciando transmissão simultânea de {} arquivo(s)...".format(len(arquivos)))
    print("(o cliente pode pausar/retomar/abortar a qualquer momento)")

    while ativos:
        for fileId in list(ativos):
            arq = arquivos[fileId]
            offset = (arq["seq"] - 1) * PAYLOAD_MAX
            payload = arq["dados"][offset:offset + PAYLOAD_MAX]
            pacote = montarPacote(DADOS, fileId, arq["seq"], arq["total"], payload)

            tentativasConteudo = 0
            reenviar = True
            while True:
                if reenviar:
                    enviarPacote(com, pacote)
                    print("  -> '{}' pacote {}/{} ({} bytes)".format(
                        arq["nome"], arq["seq"], arq["total"], len(payload)))
                    reenviar = False

                resposta = receberPacote(com, TIMEOUT_PACOTE)

                if resposta is None:
                    print("     sem resposta em {}s (conexão pode estar interrompida); reenviando...".format(
                        TIMEOUT_PACOTE))
                    reenviar = True
                    continue

                if resposta.tipo == ABORTAR:
                    print("\nCliente abortou a transmissão.")
                    raise Abortado()

                if resposta.tipo == PAUSAR:
                    print("     cliente pausou a transmissão.")
                    aguardarRetomada(com)
                    print("     cliente retomou a transmissão.")
                    reenviar = True  # o cliente ainda não confirmou este pacote
                    continue

                if (resposta.tipo in (ACK, NACK) and 0 <= resposta.fileId < len(arquivos)
                        and resposta.seq < arquivos[resposta.fileId]["seq"]):
                    # resquício de uma rodada já concluída (ex.: cruzou com o reenvio pós-pausa,
                    # possivelmente de OUTRO arquivo, já que o round-robin pode ter avançado
                    # enquanto essa resposta estava a caminho); ignora e segue esperando a atual
                    print("     resposta atrasada ('{}' pacote {}) ignorada".format(
                        arquivos[resposta.fileId]["nome"], resposta.seq))
                    continue

                if resposta.tipo == ACK and resposta.fileId == fileId and resposta.seq == arq["seq"]:
                    print("     ACK recebido para '{}' pacote {}".format(arq["nome"], arq["seq"]))
                    break

                if resposta.tipo == NACK and resposta.fileId == fileId and resposta.seq == arq["seq"]:
                    tentativasConteudo += 1
                    print("     NACK recebido para '{}' pacote {} (tentativa {}/{})".format(
                        arq["nome"], arq["seq"], tentativasConteudo, MAX_TENTATIVAS_CONTEUDO))
                    if tentativasConteudo >= MAX_TENTATIVAS_CONTEUDO:
                        print("     Excedido o número de tentativas. Encerrando transmissão.")
                        enviarPacote(com, montarControle(ABORTAR, "Excedido o número de tentativas de reenvio."))
                        raise Abortado()
                    reenviar = True
                    continue

                print("     resposta inesperada ({}), reenviando pacote...".format(nomeTipo(resposta.tipo)))
                reenviar = True
                continue

            arq["seq"] += 1
            arq["pacotesEnviados"] += 1
            if arq["seq"] > arq["total"]:
                ativos.remove(fileId)
                print("  Arquivo '{}' transmitido por completo ({} pacotes).".format(
                    arq["nome"], arq["pacotesEnviados"]))

    duracao = time.time() - inicio
    enviarPacote(com, montarControle(SUCESSO, "Transmissão concluída com sucesso."))

    print("\n" + "=" * 60)
    print("RESUMO DA TRANSMISSÃO (servidor)")
    print("=" * 60)
    for arq in arquivos:
        print("  {:<20s} {:>8d} bytes  {:>5d} pacotes".format(
            arq["nome"], len(arq["dados"]), arq["pacotesEnviados"]))
    print("  Tempo total: {:.1f}s".format(duracao))
    print("=" * 60)


def main():
    com1 = None
    try:
        print("Iniciando o servidor")
        com1 = enlace(serialName)
        com1.enable()
        time.sleep(2)          # deixa o Arduino terminar o reset provocado ao abrir a porta
        com1.fisica.flush()    # descarta o lixo que chegou na linha durante esse reset
        print("Comunicação aberta em {}".format(serialName))
        com1.rx.clearBuffer()

        print("\nArquivos disponíveis em '{}':".format(pastaArquivos))
        for nome in listarArquivos():
            print(" - {}".format(nome))

        while True:
            try:
                atenderCliente(com1)
            except Abortado:
                print("\nAtendimento encerrado (transmissão abortada).")
            com1.rx.clearBuffer()

    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário")
        if com1 is not None:
            com1.disable()

    except Exception as erro:
        print("ops! :-\\")
        print(erro)
        if com1 is not None:
            com1.disable()


if __name__ == "__main__":
    main()
