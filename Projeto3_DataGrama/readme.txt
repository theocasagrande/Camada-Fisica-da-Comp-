Projeto 3 - Protocolo de transmissao de arquivos por datagramas
=================================================================

O cliente baixa arquivos do servidor pela UART. Os arquivos sao
fragmentados em datagramas (head + payload + EOP), transmitidos com
handshake, confirmacao (ACK/NACK) pacote a pacote, e o cliente pode
pausar, retomar ou abortar a transmissao a qualquer momento.


1) Arquivos
------------
Sao 7 arquivos no total. 4 deles sao os mesmos do Projeto 1 e 2, sem
nenhuma alteracao (copiados para esta pasta conforme pedido):

    enlace.py            <- do Projeto 1/2, sem alteracao
    enlaceRx.py           <- do Projeto 1/2, sem alteracao
    enlaceTx.py           <- do Projeto 1/2, sem alteracao
    interfaceFisica.py    <- do Projeto 1/2, sem alteracao

Os novos deste projeto:

    protocolo.py    <- formato do datagrama (head/payload/EOP), tipos de
                       pacote e as funcoes de montar/enviar/receber,
                       usadas tanto pelo cliente quanto pelo servidor
    servidor.py     <- oferece os arquivos de arquivosServidor/
    cliente.py      <- baixa os arquivos escolhidos e salva em
                       arquivosRecebidos/ (criada automaticamente)
    arquivosServidor/
        poema.txt   <- arquivo de texto de exemplo
        dados.bin   <- arquivo binario de exemplo (bytes pseudo-aleatorios)

Como no Projeto 2, o mais simples e copiar a pasta inteira para os dois
computadores e rodar servidor.py em um e cliente.py no outro. Precisa
apenas do pyserial:

    python -m pip install pyserial


2) Ligacao dos Arduinos
-------------------------
Mesma ligacao ponto a ponto do Projeto 2: cada Arduino e usado só como
conversor USB-serial (o ATmega fica em reset), com TX/RX cruzados entre
as duas placas e GND comum. Veja o Explicação.MD do Projeto 2 para o
diagrama completo e a explicacao de por que o cruzamento é necessário.

Para descobrir a porta serial de cada computador:

    python -m serial.tools.list_ports

Ajuste a variavel serialName no topo de servidor.py e de cliente.py.


3) Como rodar
---------------
O SERVIDOR sempre comeca primeiro (fica esperando o handshake do
cliente):

    python servidor.py

Depois, no outro computador:

    python cliente.py

O cliente mostra os arquivos disponiveis, pede para escolher um (numero
da lista), pergunta se quer adicionar outro, e assim por diante ate
responder "N". Escolha pelo menos 2 arquivos para a demonstracao
principal. O servidor entao transmite todos os arquivos escolhidos
simultaneamente (um pacote de cada arquivo por vez, alternados) ate
terminar, e o cliente salva cada um em arquivosRecebidos/.

Depois de atender um cliente o servidor volta a esperar outro, sem
precisar reiniciar (Ctrl+C para encerrar de vez).


4) Controles durante a transmissao (no cliente)
--------------------------------------------------
    p = pausar a transmissao
    r = retomar a transmissao pausada
    a = abortar a transmissao

O cliente fica de olho no teclado (sem bloquear a recepcao) durante
toda a fase de transferencia. Ao pausar, o cliente avisa o servidor
por uma mensagem de controle e o servidor para de enviar ate receber o
"retomar"; ao abortar, os dois lados encerram a comunicacao e nenhum
arquivo incompleto e considerado valido.


5) Simulando a desconexao dos fios
-------------------------------------
Para demonstrar a recuperacao apos desconexao: com uma transmissao em
andamento, desligue fisicamente um dos jumpers TX/RX/GND entre os dois
Arduinos e espere alguns segundos (os dois lados ficam avisando "sem
resposta... reenviando" no terminal, sem travar nem desistir). Ao
reconectar o fio, a transmissao continua sozinha de onde parou e
termina com sucesso — nenhuma tecla precisa ser apertada para isso,
o proprio time out de cada pacote e que cuida da retransmissao.


6) O datagrama
-----------------
    +----------------------- HEAD (10 bytes) -----------------------+---- payload ----+-- EOP --+
    | tipo(1) | fileId(1) | seq(2) | total(2) | payloadLen(1) | rsv(3) |  ate 100 bytes  | 4 bytes |
    +------------------------------------------------------------------+-----------------+---------+

tipo identifica a mensagem (handshake, selecao de arquivo, dados,
ack/nack, pausar/retomar/abortar...); fileId diz a qual arquivo o
pacote pertence (ou 0xFF para mensagens sem arquivo associado); seq e
total sao o numero do pacote e o total de pacotes daquele arquivo,
enviados em todo pacote de dados; payloadLen diz quantos bytes do
payload sao validos; e o EOP e uma marca fixa de 4 bytes usada para
conferir que o pacote chegou inteiro.

Ao receber cada pacote de dados o cliente faz as duas verificacoes
pedidas: confere que o numero do pacote e exatamente 1 a mais que o
anterior (ordem correta) e que o EOP esta no lugar certo (chegaram
todos os bytes). Se estiver tudo certo, confirma com ACK e o servidor
manda o proximo; se algo estiver errado, pede reenvio com NACK. Um
pacote repetido (por exemplo, quando o ACK anterior se perde) e
identificado e reconfirmado sem duplicar os dados já recebidos.


7) Problemas comuns
-----------------------
| Problema                                    | O que fazer |
|----------------------------------------------|-------------|
| could not open port COMx                      | Porta errada, cabo solto, ou o Serial Monitor da IDE do Arduino aberto — feche-o. |
| [ERRO] interfaceFisica, read, decode           | Lixo que algumas maquinas geram no comeco da primeira transmissao (mesmo problema do Projeto 1/2). O protocolo se recupera sozinho pelo time out; se persistir, reinicie o cliente. |
| Cliente trava em "Servidor nao respondeu"      | O servidor nao foi iniciado antes, ou os jumpers TX/RX estao invertidos / falta o GND comum. |
| "Excedido o numero de tentativas"              | Muitos NACKs seguidos para o mesmo pacote (erro persistente, nao so uma desconexao); a transmissao é encerrada de propósito em vez de tentar para sempre. |
