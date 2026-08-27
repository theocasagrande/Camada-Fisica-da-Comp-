# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
# Projeto 2 - Aplicação CLIENTE
#
# Envia uma sequência de números em ponto flutuante IEEE-754 de
# 32 bits, recebe de volta a soma calculada pelo servidor e confere.
#
# IMPORTANTE: o servidor deve ser iniciado ANTES do cliente.
#####################################################

from enlace import *
import time
import struct

# Porta serial deste computador.
# Para descobrir: python -m serial.tools.list_ports
serialName = "COM7"

# Números a enviar. O enunciado pede de 5 a 15 números, cada um no
# intervalo [-1000 ; +1000] e com 6 casas de precisão.
numeros = [45.450000,
           -1.435670,
           154.767830,
           -87.654321,
           0.000123,
           999.999900,
           -500.500500,
           3.141593,
           -2.718282,
           123.456789]

# Se o servidor não responder em 5 segundos, o cliente avisa "time out".
TIMEOUT = 5


def recebe(com, quantidade, timeout):
    """Lê 'quantidade' bytes do buffer de recepção.

    Devolve None se o tempo acabar antes dos bytes chegarem.
    Precisamos desta função porque com.getData() espera para sempre,
    e o enunciado pede um time out. Aqui usamos só métodos que já
    existem na camada de enlace, sem alterá-la.
    """
    inicio = time.time()
    while com.rx.getBufferLen() < quantidade:
        if time.time() - inicio > timeout:
            return None
        time.sleep(0.05)
    return com.rx.getBuffer(quantidade)


def para_float32(valor):
    """Arredonda o número para a precisão de 32 bits que vai na linha."""
    return struct.unpack(">f", struct.pack(">f", valor))[0]


def main():
    com1 = None
    try:
        print("Iniciando o cliente")
        com1 = enlace(serialName)
        com1.enable()
        print("Comunicação aberta em {}".format(serialName))
        com1.rx.clearBuffer()

        # Monta o pacote: 1 byte com a quantidade de números,
        # seguido de 4 bytes por número (IEEE-754 de 32 bits).
        # O servidor descobre a quantidade lendo esse primeiro byte.
        txBuffer = bytes([len(numeros)])
        for numero in numeros:
            txBuffer += struct.pack(">f", numero)

        print("\nNúmeros a enviar:")
        for numero in numeros:
            print("{:.6f}".format(numero))

        # Soma esperada, calculada com a mesma precisão de 32 bits
        # que o servidor vai usar.
        somaEsperada = para_float32(sum([para_float32(n) for n in numeros]))
        print("\nSoma esperada: {:.6f}".format(somaEsperada))

        # Envia tudo de uma vez só
        print("\nEnviando {} bytes...".format(len(txBuffer)))
        com1.sendData(txBuffer)
        print("Enviou {} bytes".format(int(com1.tx.getStatus())))

        # Espera a soma do servidor (4 bytes), com time out
        print("\nAguardando a resposta do servidor...")
        rxBuffer = recebe(com1, 4, TIMEOUT)

        if rxBuffer is None:
            print("\nTIME OUT: o servidor não respondeu em {} segundos".format(TIMEOUT))
        else:
            somaRecebida = struct.unpack(">f", rxBuffer)[0]
            print("Soma recebida do servidor: {:.6f}".format(somaRecebida))

            if rxBuffer == struct.pack(">f", somaEsperada):
                print("\nSUCESSO: a soma devolvida pelo servidor está correta")
            else:
                print("\nERRO: a soma devolvida pelo servidor está incorreta!")
                print("Esperava {:.6f} e recebi {:.6f}".format(somaEsperada, somaRecebida))

        print("\nComunicação encerrada")
        com1.disable()

    except Exception as erro:
        print("ops! :-\\")
        print(erro)
        if com1 is not None:
            com1.disable()


if __name__ == "__main__":
    main()
