# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 2 - Aplicação SERVIDOR
#
# Fica esperando os números do cliente, mostra um por linha
# e devolve a soma em ponto flutuante IEEE-754 de 32 bits.
#
# IMPORTANTE: este programa deve ser iniciado ANTES do cliente.
#####################################################

from enlace import *
import time
import struct

# Porta serial deste computador.
# Para descobrir: python -m serial.tools.list_ports
serialName = "COM3"

# Para demonstrar o caso 2 da avaliação, mude para True.
# O servidor passa a ler o primeiro número com os bytes na ordem
# trocada, ou seja, interpreta errado o que chegou certo.
FORCAR_ERRO = False

# Para demonstrar o caso 3 da avaliação, mude para True.
# O servidor recebe e mostra tudo, mas não devolve a soma,
# fazendo o cliente cair no time out.
NAO_RESPONDER = False


def recebe(com, quantidade, timeout):
    """Lê 'quantidade' bytes do buffer de recepção.

    Com timeout = None espera para sempre, que é como o servidor
    aguarda o cliente. Com um número, desiste depois desse tempo.
    Usa só métodos que já existem na camada de enlace.
    """
    inicio = time.time()
    while com.rx.getBufferLen() < quantidade:
        if timeout is not None and time.time() - inicio > timeout:
            return None
        time.sleep(0.05)
    return com.rx.getBuffer(quantidade)


def main():
    com1 = None
    try:
        print("Iniciando o servidor")
        com1 = enlace(serialName)
        com1.enable()
        print("Comunicação aberta em {}".format(serialName))
        com1.rx.clearBuffer()

        print("\nAguardando dados do cliente... (Ctrl+C para encerrar)")

        while True:
            # O primeiro byte diz quantos números vêm. O servidor não
            # sabe a quantidade de antemão: descobre lendo esse byte.
            cabecalho = recebe(com1, 1, None)
            quantidade = cabecalho[0]

            if quantidade < 1 or quantidade > 15:
                print("Byte inesperado na linha ({}), descartando".format(quantidade))
                com1.rx.clearBuffer()
                continue

            print("\n----------------------------------------")
            print("O cliente vai enviar {} números".format(quantidade))

            # Cada número ocupa 4 bytes (IEEE-754 de 32 bits)
            rxBuffer = recebe(com1, quantidade * 4, 5)
            if rxBuffer is None:
                print("Os números não chegaram completos, descartando")
                com1.rx.clearBuffer()
                continue

            numeros = []
            for i in range(quantidade):
                bytesDoNumero = rxBuffer[i * 4:(i + 1) * 4]
                if FORCAR_ERRO and i == 0:
                    # Erro proposital: lê os 4 bytes na ordem trocada
                    bytesDoNumero = bytesDoNumero[::-1]
                numeros.append(struct.unpack(">f", bytesDoNumero)[0])

            # Mostra os números recebidos, um por linha
            print("Números recebidos:")
            for numero in numeros:
                print("{:.6f}".format(numero))

            # Calcula a soma e a converte para 32 bits, que é o que vai na linha
            resposta = struct.pack(">f", sum(numeros))
            print("Soma: {:.6f}".format(struct.unpack(">f", resposta)[0]))

            if NAO_RESPONDER:
                print("O servidor não vai responder (simulação de time out)")
            else:
                com1.sendData(resposta)
                print("Enviou {} bytes com a soma".format(int(com1.tx.getStatus())))

            print("\nAguardando dados do cliente... (Ctrl+C para encerrar)")

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
