#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#####################################################
#Carareto
#17/02/2018
####################################################

# Importa pacote de comunicação serial
import serial

# importa pacote para conversão binário ascii
import binascii

# Dígitos hexadecimais ASCII válidos: tudo que o outro lado envia passou por
# binascii.hexlify, então todo byte legítimo cai nesse conjunto. Qualquer byte
# fora dele é ruído de linha (reset do Arduino ao abrir a porta, sobras de uma
# execução anterior, glitch de framing).
_HEXDIGITS = frozenset(b"0123456789abcdefABCDEF")

#################################
# Interface com a camada física #
#################################
class fisica(object):
    def __init__(self, name):
        self.name        = name
        self.port        = None
        self.baudrate    = 115200
        #self.baudrate    = 9600
        self.bytesize    = serial.EIGHTBITS
        self.parity      = serial.PARITY_NONE
        self.stop        = serial.STOPBITS_ONE
        self.timeout     = 0.1
        self.rxRemain    = b""

    def open(self):
        self.port = serial.Serial(self.name,
                                  self.baudrate,
                                  self.bytesize,
                                  self.parity,
                                  self.stop,
                                  self.timeout)


    def close(self):
        self.port.close()

    def flush(self):
        self.port.flushInput()
        self.port.flushOutput()

    def encode(self, data):
        encoded = binascii.hexlify(data)
        return(encoded)

    def decode(self, data):
        """ RX ASCII data after reception
        """
        decoded = binascii.unhexlify(data)
        return(decoded)

    def write(self, txBuffer):
        """ Write data to serial port

        This command takes a buffer and format
        it before transmit. This is necessary
        because the pyserial and arduino uses
        Software flow control between both
        sides of communication.
        """
        nTx = self.port.write(self.encode(txBuffer))
        self.port.flush()
        return(nTx/2)

    def read(self, nBytes):
        """ Read nBytes from the UART com port

        Nem toda a leitura retorna múltiplo de 2
        devemos verificar isso para evitar que a funcao
        self.decode seja chamada com números ímpares.
        """
        rxBuffer = self.port.read(nBytes)
        rxBufferConcat = self.rxRemain + rxBuffer

        # Descarta qualquer byte que não seja dígito hexadecimal antes de tentar
        # decodificar. Sem isso, um único byte de lixo (ruído, reset do Arduino,
        # sobra de execução anterior) fazia o binascii.unhexlify lançar exceção
        # e o pacote válido que veio grudado nesse lixo era jogado fora junto.
        limpo = bytes(b for b in rxBufferConcat if b in _HEXDIGITS)

        nValid = (len(limpo)//2)*2
        rxBufferValid = limpo[0:nValid]
        self.rxRemain = limpo[nValid:]
        try :
            """ As vezes acontece erros na decodificacao
            fora do ambiente linux, isso tenta corrigir
            em parte esses erros. Melhorar futuramente."""
            "muitas vezes um flush no inicio resolve!"
            rxBufferDecoded = self.decode(rxBufferValid)

            # nº de bytes já decodificados que entram no buffer da camada de
            # enlace (o original devolvia len(rxBuffer), que era o tamanho em
            # hex, ~2x, e ainda descartava bytes quando a porta lia vazio mas
            # havia sobra pendente em rxRemain).
            nRx = len(rxBufferDecoded)
            return(rxBufferDecoded, nRx)
        except :
            print("[ERRO] interfaceFisica, read, decode. buffer : {}".format(rxBufferValid))
            return(b"", 0)

