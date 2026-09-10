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
class RX(object):
  
    def __init__(self, fisica):
        self.fisica      = fisica
        self.buffer      = bytes(bytearray())
        self.threadStop  = False
        self.threadMutex = True
        self.READLEN     = 1024
        # Protege self.buffer. A thread de RX faz "self.buffer += rxTemp" enquanto
        # a aplicação faz "self.buffer = self.buffer[n:]" em getBuffer(). As duas
        # operações leem e reescrevem a variável inteira, então sem o lock uma
        # podia sobrescrever a outra e bytes já recebidos sumiam do buffer.
        # threadPause() sozinho não resolvia: ele só impede a PRÓXIMA volta do
        # laço, e a thread pode estar justamente dentro de fisica.read().
        self.lock        = threading.Lock()

    def thread(self): 
        while not self.threadStop:
            if(self.threadMutex == True):
                rxTemp, nRx = self.fisica.read(self.READLEN)
                if (nRx > 0):
                    with self.lock:
                        self.buffer += rxTemp
                time.sleep(0.01)

    def threadStart(self):       
        self.thread = threading.Thread(target=self.thread, args=())
        self.thread.start()

    def threadKill(self):
        self.threadStop = True

    def threadPause(self):
        self.threadMutex = False

    def threadResume(self):
        self.threadMutex = True

    def getIsEmpty(self):
        if(self.getBufferLen() == 0):
            return(True)
        else:
            return(False)

    def getBufferLen(self):
        with self.lock:
            return(len(self.buffer))

    def getAllBuffer(self, len=None):
        with self.lock:
            b = self.buffer[:]
            self.buffer = b""
        return(b)

    def getBuffer(self, nData):
        with self.lock:
            b           = self.buffer[0:nData]
            self.buffer = self.buffer[nData:]
        return(b)

    def getNData(self, size):
        while(self.getBufferLen() < size):
            time.sleep(0.05)                 
        return(self.getBuffer(size))


    def clearBuffer(self):
        with self.lock:
            self.buffer = b""
