#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#####################################################
# Camada Física da Computação
#Carareto
#17/02/2018
#  Camada de Enlace
####################################################

# Importa pacote de tempo
import time

# Threads
import threading

# Class
class TX(object):
 
    def __init__(self, fisica):
        self.fisica      = fisica
        self.buffer      = bytes(bytearray())
        self.transLen    = 0
        self.empty       = True
        self.threadMutex = False
        self.threadStop  = False


    def thread(self):
        while not self.threadStop:
            if(self.threadMutex):
                self.transLen    = self.fisica.write(self.buffer)
                self.threadMutex = False

    def threadStart(self):
        self.thread = threading.Thread(target=self.thread, args=())
        self.thread.start()

    def threadKill(self):
        self.threadStop = True

    def threadPause(self):
        self.threadMutex = False

    def threadResume(self):
        self.threadMutex = True

    def sendBuffer(self, data):
        self.transLen   = 0
        self.buffer = data
        self.threadMutex  = True

    def getBufferLen(self):
        return(len(self.buffer))

    def getStatus(self):
        """ Retorna quantos bytes foram efetivamente transmitidos.

        sendBuffer() apenas sinaliza a thread TX (threadMutex = True) e retorna
        na hora; quem realmente escreve na porta e atualiza transLen é a thread,
        de forma assíncrona. Chamar getStatus() logo em seguida, sem esperar,
        lia transLen antes da thread ter processado o envio (valor 0 ou de um
        envio anterior). Por isso aguardamos threadMutex voltar a False, que é
        o sinal de que a thread concluiu a escrita e atualizou transLen.
        """

        while self.threadMutex:
            time.sleep(0.001)
        return(self.transLen)


    def getIsBussy(self):
        return(self.threadMutex)

