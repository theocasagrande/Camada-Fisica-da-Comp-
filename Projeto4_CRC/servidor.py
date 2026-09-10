# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 4 - Aplicação SERVIDOR (quem RECEBE os arquivos)
#
# O servidor fica esperando um cliente. Quando ele chega, negocia quais
# arquivos serão enviados e então recebe todos simultaneamente (pacotes
# alternados entre os arquivos). Para CADA pacote de dados recebido ele:
#
#   1. recalcula o CRC-16 do payload e compara com o CRC que veio no head;
#   2. confere se o número do pacote é o esperado (ordem);
#   3. responde OK   ("não houve incoerências, pode mandar o próximo") ou
#      responde ERRO ("incoerência de CRC / de ordem, reenvie o pacote N").
#
# Os arquivos recebidos são salvos em arquivosRecebidos/ e cada pacote que
# entra ou sai é registrado em logs/log_servidor_<cenario>.txt.
#
# IMPORTANTE: este programa deve ser iniciado ANTES do cliente.
#####################################################

from enlace import *
from protocolo import *
import os
import time

# Porta serial deste computador.
# Para descobrir: python -m serial.tools.list_ports
serialName = "COM3"

baseDir = os.path.dirname(os.path.abspath(__file__))
pastaRecebidos = os.path.join(baseDir, "arquivosRecebidos")

MSG_INICIAR = "Entendido. Pode iniciar a transmissao simultanea dos arquivos escolhidos."


def formatarLista(nomes):
    """'a.txt' / "'a.txt' e 'b.png'" / "'a.txt', 'b.png' e 'c.bin'" """
    citados = ["'{}'".format(nome) for nome in nomes]
    if len(citados) == 1:
        return citados[0]
    return "{} e {}".format(", ".join(citados[:-1]), citados[-1])


def montarMensagemEscolha(escolhidos):
    """"Arquivo 'x' escolhido, deseja adicionar outro arquivo? (S/N)" ou, com
    mais de um, "Arquivo 'x' e 'y' escolhidos, ...", citando todos os nomes
    escolhidos até agora. Se a lista ficar grande demais para caber no
    payload (100 bytes), cai para uma versão resumida.
    """
    verbo = "escolhido" if len(escolhidos) == 1 else "escolhidos"
    texto = "Arquivo {} {}, deseja adicionar outro arquivo? (S/N)".format(formatarLista(escolhidos), verbo)
    if len(texto.encode("utf-8")) <= PAYLOAD_MAX:
        return texto
    return "Arquivo '{}' tambem escolhido ({} no total). Deseja adicionar outro arquivo? (S/N)".format(
        escolhidos[-1], len(escolhidos))


def aguardarRetomada(com):
    """Bloqueia até o cliente mandar RETOMAR (ou ABORTAR), enquanto pausado."""
    while True:
        resposta = receberPacote(com, None)
        if resposta is None or not (resposta.eopOk and resposta.crcOk):
            continue
        if resposta.tipo == RETOMAR:
            return
        if resposta.tipo == ABORTAR:
            print("\nCliente abortou durante a pausa.")
            raise Abortado()


def atenderCliente(com):
    print("\nAguardando handshake de um cliente... (Ctrl+C para encerrar)")

    # O handshake vem antes de sabermos o nome do cenário, então ele é lido
    # sem log e registrado logo depois, já no arquivo certo.
    pacote = receberPacote(com, None)
    if pacote is None or pacote.tipo != HELLO:
        print("Pacote inesperado recebido antes do handshake, ignorando.")
        return

    cenario = pacote.payload.decode("utf-8", errors="replace").strip() or "sessao"
    caminhoLog = iniciarLog("servidor", cenario)
    registrarLog("receb", HELLO, HEAD_SIZE + len(pacote.payload) + EOP_SIZE,
                 observacao="handshake, cenario '{}'".format(cenario))
    print("Cliente conectado! Cenário informado: '{}'".format(cenario))
    print("Log desta transmissão: {}".format(caminhoLog))

    enviarPacote(com, montarControle(PRONTO, "Servidor pronto. Quais arquivos voce vai enviar?"))

    # ---- diálogo de seleção de arquivos ----
    #
    # O laço é IDEMPOTENTE de propósito: cada mensagem do cliente sempre gera a
    # mesma resposta, mesmo que ela chegue repetida. Isso é o que permite ao
    # cliente reenviar um pedido perdido (fio desconectado bem no meio da
    # negociação) sem que os dois lados saiam do passo — receber duas vezes o
    # mesmo SELECIONAR não escolhe o arquivo duas vezes, só repete o CONFIRMAR.
    escolhidos = []
    while True:
        # time out finito (e não None) para que, se o fio cair no meio da
        # negociação, o laço volte ao topo e o protocolo possa se realinhar,
        # em vez de ficar preso esperando o resto de um pacote que não vem
        pacote = receberPacote(com, TIMEOUT_HANDSHAKE)
        if pacote is None or not (pacote.eopOk and pacote.crcOk):
            continue

        if pacote.tipo == ABORTAR:
            print("Cliente abortou durante a seleção de arquivos.")
            return

        if pacote.tipo == HELLO:
            # o cliente não recebeu nosso PRONTO e está reenviando o handshake
            enviarPacote(com, montarControle(PRONTO, "Servidor pronto. Quais arquivos voce vai enviar?"))
            continue

        if pacote.tipo == SELECIONAR:
            nome = pacote.payload.decode("utf-8", errors="replace")
            if nome not in escolhidos:
                escolhidos.append(nome)
                print("Cliente vai enviar '{}'. Escolhidos até agora: {}".format(
                    nome, formatarLista(escolhidos)))
            else:
                print("Cliente reenviou a escolha de '{}' (o CONFIRMAR deve ter se perdido).".format(nome))
            enviarPacote(com, montarControle(CONFIRMAR, montarMensagemEscolha(escolhidos)))
            continue

        if pacote.tipo == RESPOSTA:
            if pacote.payload[:1].upper() == b"S":
                enviarPacote(com, montarControle(PRONTO, "Ok, pode escolher o proximo arquivo."))
                continue
            break

        print("Mensagem inesperada durante a seleção ({}), ignorando.".format(nomeTipo(pacote.tipo)))

    if not escolhidos:
        print("Cliente não escolheu nenhum arquivo.")
        return

    print("\nSeleção concluída: {}".format(formatarLista(escolhidos)))
    enviarPacote(com, montarControle(INICIAR, MSG_INICIAR))

    receberArquivos(com, escolhidos)


def receberArquivos(com, nomes):
    arquivos = {}
    for fileId, nome in enumerate(nomes):
        arquivos[fileId] = {
            "nome": nome, "dados": bytearray(), "seq": 0, "total": 0,
            "pacotesRecebidos": 0, "errosCrc": 0, "errosOrdem": 0,
        }

    ativos = set(arquivos.keys())
    inicio = time.time()
    print("\nRecebendo {} arquivo(s) simultaneamente...".format(len(nomes)))
    print("(conferindo o CRC-16 do payload de cada pacote)")

    while ativos:
        pacote = receberPacote(com, TIMEOUT_PACOTE)

        if pacote is None:
            print("  sem dados em {}s (conexão pode estar interrompida); aguardando...".format(
                TIMEOUT_PACOTE))
            continue

        if not pacote.eopOk:
            # Sem o EOP no lugar certo não dá para confiar em nenhum campo do
            # head (nem no fileId, nem no seq, nem no próprio tipo), então não
            # há a quem responder — e obedecer um "ABORTAR" que na verdade é
            # lixo seria pior ainda. O protocolo já se realinhou sozinho; o
            # cliente reenvia por time out.
            print("  pacote descartado: EOP inválido (o fluxo foi realinhado)")
            continue

        if pacote.tipo != DADOS:
            # Mensagens de controle carregam o texto no payload, então só são
            # obedecidas se o CRC do payload também estiver correto.
            if not pacote.crcOk:
                print("  mensagem de controle corrompida ({}), ignorando.".format(nomeTipo(pacote.tipo)))
                continue

            if pacote.tipo == ABORTAR:
                print("\nCliente abortou a transmissão: {}".format(
                    pacote.payload.decode("utf-8", errors="replace")))
                raise Abortado()

            if pacote.tipo == PAUSAR:
                print("  cliente pausou a transmissão; aguardando o retomar...")
                aguardarRetomada(com)
                print("  cliente retomou a transmissão.")
                continue

            if pacote.tipo == RESPOSTA:
                # o cliente não recebeu o INICIAR e está reenviando a resposta
                # final da seleção; repete a autorização para ele destravar
                enviarPacote(com, montarControle(INICIAR, MSG_INICIAR))
                continue

            if pacote.tipo == RETOMAR:
                continue

            print("  mensagem inesperada recebida ({}), ignorando.".format(nomeTipo(pacote.tipo)))
            continue

        arq = arquivos.get(pacote.fileId)
        if arq is None:
            print("  pacote de um arquivo desconhecido (fileId {}), ignorando.".format(pacote.fileId))
            continue

        seqEsperado = arq["seq"] + 1

        # ---- 1) conferência do CRC-16 do payload ----
        if not pacote.crcOk:
            arq["errosCrc"] += 1
            print("  !! '{}' pacote {}: INCOERENCIA DE CRC (veio {:04X}, calculei {:04X})".format(
                arq["nome"], pacote.seq, pacote.crc, calcularCRC(pacote.payload)))
            print("     pedindo reenvio do pacote {}".format(seqEsperado))
            enviarPacote(com, montarPacote(ERRO, pacote.fileId, seqEsperado, arq["total"], MOTIVO_CRC))
            continue

        # ---- 2) pacote repetido: nosso OK anterior deve ter se perdido ----
        if pacote.seq == arq["seq"] and arq["seq"] > 0:
            print("  <- '{}' pacote {} repetido (o OK anterior deve ter se perdido); reenviando OK".format(
                arq["nome"], pacote.seq))
            enviarPacote(com, montarPacote(OK, pacote.fileId, pacote.seq, arq["total"]))
            continue

        # ---- 3) conferência da ordem ----
        if pacote.seq != seqEsperado:
            arq["errosOrdem"] += 1
            print("  !! '{}': pacote FORA DE ORDEM (recebi {}, esperava {})".format(
                arq["nome"], pacote.seq, seqEsperado))
            print("     pedindo reenvio do pacote {}".format(seqEsperado))
            enviarPacote(com, montarPacote(ERRO, pacote.fileId, seqEsperado, pacote.total, MOTIVO_ORDEM))
            continue

        # ---- 4) tudo certo: guarda o pedaço e confirma ----
        arq["dados"] += pacote.payload
        arq["seq"]    = pacote.seq
        arq["total"]  = pacote.total
        arq["pacotesRecebidos"] += 1
        enviarPacote(com, montarPacote(OK, pacote.fileId, pacote.seq, pacote.total))
        print("  <- '{}' pacote {}/{} ok, CRC {:04X} confere ({} bytes)".format(
            arq["nome"], pacote.seq, pacote.total, pacote.crc, len(pacote.payload)))

        if pacote.seq >= pacote.total:
            ativos.discard(pacote.fileId)
            print("  Arquivo '{}' recebido por completo.".format(arq["nome"]))

    duracao = time.time() - inicio
    enviarPacote(com, montarControle(SUCESSO, "Todos os arquivos chegaram com o CRC correto."))

    os.makedirs(pastaRecebidos, exist_ok=True)
    print("\n" + "=" * 68)
    print("RESUMO DA TRANSMISSÃO (servidor - recebeu)")
    print("=" * 68)
    for arq in arquivos.values():
        caminho = os.path.join(pastaRecebidos, arq["nome"])
        with open(caminho, "wb") as f:
            f.write(arq["dados"])
        print("  {:<20s} {:>8d} bytes  {:>5d} pacotes  {} erro(s) de CRC, {} de ordem".format(
            arq["nome"], len(arq["dados"]), arq["pacotesRecebidos"],
            arq["errosCrc"], arq["errosOrdem"]))
        print("  {:<20s} salvo em {}".format("", caminho))
    print("  Tempo total: {:.1f}s".format(duracao))
    print("=" * 68)


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

        while True:
            try:
                atenderCliente(com1)
            except Abortado:
                print("\nAtendimento encerrado (transmissão abortada).")
            fecharLog()
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

    finally:
        fecharLog()


if __name__ == "__main__":
    main()
