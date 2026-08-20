 "[ERRO] interfaceFisica, read, decode. buffer :" 
Esse erro ocorre porque, alguns computadores (ou arduínos) produzem 2 (ou mais) bytes não pertencentes à mensagem no início da primeira transmissão (geralmente \xF0\xF0). Não adianta usar a função flush, pois esses lixos são gerados apenas no início da transmissão.  Esses bytes são gerados com mais alguns bits espúrios, e a decodificação de binário para ASCII não pode ser feita, gerando o except. 

Em alguns casos o erro ocorre no início da transmissão e a aplicação continua sem problemas, mas caso voce tenha se deparado com esse problema e ele esteja te impedindo de continuar, aqui vai um "workaround" :

1) No computador que está enviando a mensagem, após declarar a variavel enlace, você deve acrescentar o envio de um byte de sacrifício. Esse byte será descartado, servindo apenas para produzir o erro. Depois disso, basta acrescentar um sleep de 1 segundo. Copie o código abaixo.

        com1.enable()
        time.sleep(.2)
        com1.sendData(b'00')
        time.sleep(1) 

2) Na aplicação de recebimento, você deverá tentar ler esse byte de sacrificio. Esse byte chegará misturado aos bytes de sujeira, corrompido, algumas partes irão gerar dados na variável buffer,  que voce irá limpar. Outras partes irão gerar o erro de decodificação, que poderá ignorar. Dessa maneira, a aplicação que recebe os primeiros dados irá "nascer" esperando 1 byte. Deve ser iniciada antes da outra aplicação. Você pode copiar o codigo abaixo:

        com1.enable()
        print("esperando 1 byte de sacrifício")        
        rxBuffer, nRx = com1.getData(1)
        com1.rx.clearBuffer()
        time.sleep(.1)