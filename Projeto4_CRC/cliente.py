# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 4 - Aplicação CLIENTE (quem ENVIA os arquivos)
#
# Diferente do Projeto 3, aqui é o cliente quem transmite os arquivos e o
# servidor quem recebe e confere. É o que o enunciado do Projeto 4 pede:
# "caso o lado que recebe o pacote (server) detecte uma incoerência entre o
# CRC enviado e o CRC calculado" e "transmissão com erro na ordem dos
# pacotes enviados pelo client".
#
# O cliente oferece os arquivos da pasta arquivosCliente/, negocia com o
# servidor quais serão enviados e então transmite todos simultaneamente
# (pacotes alternados entre os arquivos), sempre esperando a resposta OK do
# servidor antes de mandar o próximo pacote. Se vier ERRO (CRC ou ordem),
# o pacote é reenviado.
#
# Durante a transmissão, o usuário pode apertar uma tecla a qualquer momento:
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

# ---------------------------------------------------------------------------
# ERROS PROPOSITAIS (hard coded), como pede o enunciado.
#
# Mude UM flag por vez para True, rode a transmissão e compare os logs dos
# dois lados em logs/. Em todos os casos o erro é injetado uma única vez: o
# protocolo detecta, pede reenvio e a transmissão termina com SUCESSO — que é
# exatamente o que o enunciado exige ("esse problema deve ser corrigido e a
# transmissão terminar com sucesso").
#
#   ERRO_CRC   -> corrompe 1 byte do payload DEPOIS de calcular o CRC, então
#                 o CRC do head não bate com o payload que chega no servidor.
#   ERRO_ORDEM -> pula um pacote no envio (manda o 4 no lugar do 3), então o
#                 servidor recebe um pacote fora de ordem.
#
# O 4º cenário do enunciado (interrupção física) não precisa de flag: basta
# desconectar os jumpers no meio da transmissão e reconectar depois.
# ---------------------------------------------------------------------------
ERRO_CRC        = False
ERRO_ORDEM      = False
PACOTE_COM_ERRO = 3       # em qual número de pacote o erro proposital acontece
ARQUIVO_COM_ERRO = 0      # em qual dos arquivos escolhidos (0 = o primeiro)

# Nome do cenário, usado para nomear os arquivos de log dos DOIS lados (o
# cliente manda esse nome no handshake). Deixe vazio para sair automático dos
# flags acima; para o teste dos fios, escreva "desconexao".
CENARIO = ""

baseDir = os.path.dirname(os.path.abspath(__file__))
pastaArquivos = os.path.join(baseDir, "arquivosCliente")


def nomeDoCenario():
    if CENARIO:
        return CENARIO
    if ERRO_CRC:
        return "erro_crc"
    if ERRO_ORDEM:
        return "erro_ordem"
    return "sucesso"


def teclaPressionada():
    """Devolve a tecla pressionada (minúscula), sem bloquear, ou None."""
    if msvcrt.kbhit():
        try:
            return msvcrt.getch().decode().lower()
        except UnicodeDecodeError:
            return None
    return None


def listarArquivos():
    return sorted(
        nome for nome in os.listdir(pastaArquivos)
        if os.path.isfile(os.path.join(pastaArquivos, nome))
    )


def escolherArquivos(com):
    """Handshake e negociação: o cliente diz quais arquivos vai enviar e o
    servidor confirma cada escolha, perguntando se há mais algum.
    """
    print("\nEnviando handshake para o servidor...")
    pacote = pedir(com, montarControle(HELLO, nomeDoCenario()), (PRONTO,))
    if pacote is None:
        print("Servidor não respondeu ao handshake.")
        return []
    print("Servidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))

    disponiveis = listarArquivos()
    escolhidos = []

    while True:
        restantes = [n for n in disponiveis if n not in escolhidos]
        if not restantes:
            # acabaram os arquivos da pasta: avisa o servidor que não há mais
            # nada a escolher e espera a autorização para começar
            print("\nNão há mais arquivos para enviar.")
            if not escolhidos:
                return []
            pacote = pedir(com, montarControle(RESPOSTA, "N"), (INICIAR,))
            if pacote is None:
                print("Servidor não autorizou o início da transmissão.")
                return []
            print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))
            return escolhidos

        print("\nArquivos disponíveis para envio (pasta arquivosCliente/):")
        for i, nome in enumerate(restantes, start=1):
            caminho = os.path.join(pastaArquivos, nome)
            print("  {}) {} ({} bytes)".format(i, nome, os.path.getsize(caminho)))

        nome = None
        while nome is None:
            escolha = input("Escolha o número do arquivo que deseja enviar: ").strip()
            try:
                nome = restantes[int(escolha) - 1]
            except (ValueError, IndexError):
                print("Opção inválida, tente novamente.")

        pacote = pedir(com, montarControle(SELECIONAR, nome), (CONFIRMAR,))
        if pacote is None:
            print("Servidor não respondeu à escolha do arquivo.")
            return []

        escolhidos.append(nome)
        print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))

        resp = input("Adicionar outro arquivo? (S/N): ").strip().upper()
        querMais = resp.startswith("S")

        # Toda mensagem do cliente tem uma resposta do servidor: com "S" ele
        # responde PRONTO (pode escolher o próximo), com "N" responde INICIAR.
        # É isso que permite reenviar qualquer pedido perdido sem os dois lados
        # saírem do passo.
        esperado = (PRONTO,) if querMais else (INICIAR,)
        pacote = pedir(com, montarControle(RESPOSTA, "S" if querMais else "N"), esperado)
        if pacote is None:
            print("Servidor não respondeu.")
            return []

        if querMais:
            continue

        print("\nServidor: {}".format(pacote.payload.decode("utf-8", errors="replace")))
        return escolhidos

    return escolhidos


def transmitirArquivos(com, nomes):
    arquivos = []
    print("")
    for fileId, nome in enumerate(nomes):
        caminho = os.path.join(pastaArquivos, nome)
        with open(caminho, "rb") as f:
            dados = f.read()
        # ceil da divisão, sem depender do módulo math; no mínimo 1 pacote,
        # para que um arquivo vazio ainda gere um pacote (vazio) e o servidor
        # saiba que ele terminou.
        total = max(1, -(-len(dados) // PAYLOAD_MAX))
        arquivos.append({
            "id": fileId, "nome": nome, "dados": dados,
            "total": total, "seq": 1, "pacotesEnviados": 0, "reenvios": 0,
        })
        print("  [{}] {} - {} bytes - {} pacotes".format(fileId, nome, len(dados), total))

    erroCrcFeito   = False
    erroOrdemFeito = False
    pausado        = False

    ativos = list(range(len(arquivos)))
    inicio = time.time()
    print("\nIniciando transmissão simultânea de {} arquivo(s)...".format(len(arquivos)))
    print("(durante a transmissão: 'p' pausa, 'r' retoma, 'a' aborta)")

    while ativos:
        for fileId in list(ativos):
            arq = arquivos[fileId]

            # ---- teclado: pausar / retomar / abortar ----
            while True:
                tecla = teclaPressionada()
                if tecla == "a":
                    print("\n[tecla 'a'] Abortando a transmissão...")
                    enviarPacote(com, montarControle(ABORTAR, "Abortado pelo usuario."))
                    raise Abortado()
                if not pausado and tecla == "p":
                    print("\n[tecla 'p'] Pausando a transmissão...")
                    enviarPacote(com, montarControle(PAUSAR))
                    pausado = True
                    print("Pausado. Pressione 'r' para retomar ou 'a' para abortar.")
                    continue
                if pausado:
                    if tecla == "r":
                        print("\n[tecla 'r'] Retomando a transmissão...")
                        enviarPacote(com, montarControle(RETOMAR))
                        pausado = False
                        break
                    time.sleep(0.05)
                    continue
                break

            # ---- monta, envia e aguarda a resposta de um pacote ----
            tentativas = 0
            reenviar = True
            while True:
                if reenviar:
                    observacao = ""

                    # ERRO PROPOSITAL DE ORDEM: pula um pacote no envio.
                    if (ERRO_ORDEM and not erroOrdemFeito and fileId == ARQUIVO_COM_ERRO
                            and arq["seq"] == PACOTE_COM_ERRO and arq["total"] > PACOTE_COM_ERRO):
                        erroOrdemFeito = True
                        arq["seq"] += 1
                        observacao = "ERRO PROPOSITAL: pulou o pacote {}".format(PACOTE_COM_ERRO)
                        print("  !! erro proposital: pulando o pacote {} de '{}'".format(
                            PACOTE_COM_ERRO, arq["nome"]))

                    offset  = (arq["seq"] - 1) * PAYLOAD_MAX
                    payload = arq["dados"][offset:offset + PAYLOAD_MAX]
                    pacote  = montarPacote(DADOS, fileId, arq["seq"], arq["total"], payload)

                    # ERRO PROPOSITAL DE CRC: corrompe 1 byte do payload DEPOIS
                    # de o CRC já ter sido calculado e gravado no head. O CRC
                    # que viaja no head continua sendo o do payload original,
                    # então no servidor ele não vai bater com o que chegou.
                    if (ERRO_CRC and not erroCrcFeito and fileId == ARQUIVO_COM_ERRO
                            and arq["seq"] == PACOTE_COM_ERRO and len(payload) > 0):
                        erroCrcFeito = True
                        corrompido = bytearray(pacote)
                        corrompido[HEAD_SIZE] ^= 0xFF
                        pacote = bytes(corrompido)
                        observacao = "ERRO PROPOSITAL: payload corrompido (CRC nao vai bater)"
                        print("  !! erro proposital: corrompendo o payload do pacote {} de '{}'".format(
                            arq["seq"], arq["nome"]))

                    enviarPacote(com, pacote, observacao)
                    print("  -> '{}' pacote {}/{} ({} bytes de payload)".format(
                        arq["nome"], arq["seq"], arq["total"], len(payload)))
                    reenviar = False

                resposta = receberPacote(com, TIMEOUT_PACOTE)

                if resposta is None:
                    print("     sem resposta em {}s (conexão pode estar interrompida); reenviando...".format(
                        TIMEOUT_PACOTE))
                    arq["reenvios"] += 1
                    reenviar = True
                    continue

                if resposta.tipo == ABORTAR:
                    print("\nServidor abortou a transmissão: {}".format(
                        resposta.payload.decode("utf-8", errors="replace")))
                    raise Abortado()

                if not (resposta.eopOk and resposta.crcOk):
                    print("     resposta corrompida do servidor; reenviando o pacote...")
                    reenviar = True
                    continue

                if resposta.tipo == OK and resposta.fileId == fileId and resposta.seq == arq["seq"]:
                    print("     OK do servidor para '{}' pacote {} (sem incoerência de CRC)".format(
                        arq["nome"], arq["seq"]))
                    break

                if resposta.tipo == ERRO and resposta.fileId == fileId:
                    tentativas += 1
                    arq["reenvios"] += 1
                    motivo = resposta.payload.decode("utf-8", errors="replace")
                    print("     ERRO do servidor em '{}': {} - reenviando o pacote {} (tentativa {}/{})".format(
                        arq["nome"], motivo, resposta.seq, tentativas, MAX_TENTATIVAS_CONTEUDO))
                    if tentativas >= MAX_TENTATIVAS_CONTEUDO:
                        print("     Excedido o número de tentativas. Encerrando transmissão.")
                        enviarPacote(com, montarControle(ABORTAR, "Excedido o numero de tentativas."))
                        raise Abortado()
                    # o servidor informa, no campo seq, qual pacote ele espera:
                    # é assim que o erro de ordem (pacote pulado) se conserta.
                    arq["seq"] = resposta.seq
                    reenviar = True
                    continue

                # respostas atrasadas de uma rodada anterior (ex.: o OK chegou
                # depois de já termos reenviado por time out) são ignoradas.
                print("     resposta fora de contexto ({} de fileId {} seq {}), ignorando".format(
                    nomeTipo(resposta.tipo), resposta.fileId, resposta.seq))
                continue

            arq["seq"] += 1
            arq["pacotesEnviados"] += 1
            if arq["seq"] > arq["total"]:
                ativos.remove(fileId)
                print("  Arquivo '{}' enviado por completo ({} pacotes).".format(
                    arq["nome"], arq["pacotesEnviados"]))

    duracao = time.time() - inicio

    resposta = receberPacote(com, TIMEOUT_HANDSHAKE)
    if resposta is not None and resposta.tipo == SUCESSO:
        print("\nServidor: {}".format(resposta.payload.decode("utf-8", errors="replace")))

    print("\n" + "=" * 68)
    print("RESUMO DA TRANSMISSÃO (cliente - enviou)")
    print("=" * 68)
    for arq in arquivos:
        print("  {:<20s} {:>8d} bytes  {:>5d} pacotes  {:>3d} reenvios".format(
            arq["nome"], len(arq["dados"]), arq["pacotesEnviados"], arq["reenvios"]))
    print("  Tempo total: {:.1f}s".format(duracao))
    print("=" * 68)


def main():
    com1 = None
    try:
        cenario = nomeDoCenario()
        caminhoLog = iniciarLog("cliente", cenario)
        print("Iniciando o cliente (cenário: {})".format(cenario))
        print("Log desta transmissão: {}".format(caminhoLog))

        com1 = enlace(serialName)
        com1.enable()
        time.sleep(2)          # deixa o Arduino terminar o reset provocado ao abrir a porta
        com1.fisica.flush()    # descarta o lixo que chegou na linha durante esse reset
        print("Comunicação aberta em {}".format(serialName))
        com1.rx.clearBuffer()

        nomes = escolherArquivos(com1)
        if nomes:
            transmitirArquivos(com1, nomes)

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

    finally:
        fecharLog()


if __name__ == "__main__":
    main()
