#####################################################
# Camada Física da Computação
#Carareto
#11/08/2022
#Aplicação
####################################################


#esta é a camada superior, de aplicação do seu software de comunicação serial UART.
#para acompanhar a execução e identificar erros, construa prints ao longo do código!


from enlace import *
import time
import numpy as np
import os

# voce deverá descomentar e configurar a porta com através da qual ira fazer comunicaçao
#   para saber a sua porta, execute no terminal :
#   python -m serial.tools.list_ports
# se estiver usando windows, o gerenciador de dispositivos informa a porta

#use uma das 3 opcoes para atribuir à variável a porta usada
#serialName = "/dev/ttyACM0"           # Ubuntu (variacao de)
#serialName = "/dev/tty.usbmodem1411" # Mac    (variacao de)
serialName = "COM3"                  # Windows(variacao de)  detectar sua porta e substituir aqui

# Caminhos das imagens. Usamos o diretório deste arquivo como referência para que
# funcionem independente de onde o script for executado.
baseDir = os.path.dirname(os.path.abspath(__file__))
imageR  = os.path.join(baseDir, "imgs", "image.png")           # imagem a ser transmitida
imageW  = os.path.join(baseDir, "imgs", "recebidaCopia.png")   # cópia recebida via serial


def main():
    com1 = None
    try:
        print("Iniciou o main")
        #declaramos um objeto do tipo enlace com o nome "com". Essa é a camada inferior à aplicação. Observe que um parametro
        #para declarar esse objeto é o nome da porta.
        com1 = enlace(serialName)


        # Ativa comunicacao. Inicia os threads e a comunicação seiral
        com1.enable()
        #Se chegamos até aqui, a comunicação foi aberta com sucesso. Faça um print para informar.
        print("Abriu a comunicação")

        #aqui geramos os dados a serem transmitidos: os bytes crus da imagem.
        #seus dados a serem transmitidos são um array bytes a serem transmitidos. Essa lista tem o
        #nome de txBuffer. Ela sempre irá armazenar os dados a serem enviados.
        print("Carregando imagem para transmissão :")
        print(" - {}".format(imageR))
        print("-------------------------")
        txBuffer = open(imageR, 'rb').read()  #txBuffer = imagem em bytes!

        print("meu array de bytes tem tamanho {}" .format(len(txBuffer)))
        #conferência do tamanho do txBuffer, ou seja, quantos bytes serão enviados.


        #finalmente vamos transmitir os todos. Para isso usamos a funçao sendData que é um método da camada enlace.
        print("Iniciando a transmissão...")
        #tente entender como o método send funciona!
        #Cuidado! Apenas trasmita arrays de bytes!
        com1.sendData(np.asarray(txBuffer))  #as array apenas como boa pratica para casos de ter uma outra forma de dados

        # A camada enlace possui uma camada inferior, TX possui um método para conhecermos o status da transmissão
        # getStatus() aguarda o término da escrita física e retorna quantos bytes foram efetivamente enviados.
        txSize = com1.tx.getStatus()
        print('enviou = {} bytes' .format(txSize))

        #Agora vamos iniciar a recepção dos dados. Se algo chegou ao RX, deve estar automaticamente guardado
        #Observe o que faz a rotina dentro do thread RX
        print("Aguardando recepção de {} bytes..." .format(len(txBuffer)))

        #acesso aos bytes recebidos
        txLen = len(txBuffer)
        rxBuffer, nRx = com1.getData(txLen)
        print("recebeu {} bytes" .format(len(rxBuffer)))

        #salva a cópia recebida como um novo arquivo de imagem
        print("Salvando dados no arquivo :")
        print(" - {}".format(imageW))
        f = open(imageW, 'wb')
        f.write(rxBuffer)
        f.close()

        #confere se a imagem recebida é idêntica à transmitida (loop back correto)
        if rxBuffer == txBuffer:
            print("Sucesso! A imagem recebida é idêntica à original.")
        else:
            print("Atenção: a imagem recebida é diferente da original.")



        # Encerra comunicação
        print("-------------------------")
        print("Comunicação encerrada")
        print("-------------------------")
        com1.disable()

    except Exception as erro:
        print("ops! :-\\")
        print(erro)
        if com1 is not None:
            com1.disable()


    #so roda o main quando for executado do terminal ... se for chamado dentro de outro modulo nao roda
if __name__ == "__main__":
    main()
