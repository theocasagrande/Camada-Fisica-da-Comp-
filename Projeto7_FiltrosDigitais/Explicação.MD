# Projeto 7 — Filtros Digitais (equalizador digital de áudio)

Camada Física da Computação — Engenharia da Computação — Insper

O projeto tem duas partes:

1. **Exercícios 1 a 6** do `filtros_digitais.pdf`: passa-baixa, decibéis, Bode,
   passa-faixa e rejeita-faixa → `exercicios.py`.
2. **Equalizador de 12 bandas**: o usuário escolhe de −10 a +10 dB em cada
   banda, o programa monta uma função de transferência por banda, aplica os
   filtros **um a um** ao áudio, toca o original seguido do equalizado e
   desenha o **Bode do equalizador completo** → `equalizador.py`.

Rubrica do site: **C** filtros atuando no sinal · **B** interface bem
construída e execução dos áudios · **A** Bode do filtro completo. Os "+"
dependem do capricho e dos exercícios.

---

## 1. Arquivos

```
Projeto7_FiltrosDigitais/
├── filtros.py             <- biblioteca: peaking EQ, Q das bandas, cascata, Bode, wav
├── equalizador.py         <- O PROJETO: interface com 12 sliders, áudio e gráficos
├── exercicios.py          <- exercícios 1 a 6 (contas no terminal + gráficos)
├── testes.py              <- 8 testes automáticos da matemática (sem som, sem janela)
├── gerar_audio_teste.py   <- cria audios/teste.wav e audios/varredura.wav
├── audios/
│   ├── teste.wav          <- 6 s de "música" sintética (graves, médios e agudos)
│   └── varredura.wav      <- senoide que sobe de 20 Hz a 20 kHz em 6 s
├── filtro_peaking_EQ.ipynb   (notebook do professor, não foi alterado)
└── filtros_digitais.pdf      (enunciado)
```

`filtros.py` não tem interface nem som: é a parte que o `testes.py` confere.
O `equalizador.py` só cuida da tela e chama as funções dela.

---

## 2. Instalação

Bibliotecas: `numpy`, `scipy`, `matplotlib` e `sounddevice` (a mesma do
Projeto 6, para tocar e gravar). O `tkinter` da interface já vem com o Python.

**Neste computador** há dois Pythons. O 3.14 (o padrão do `py`) não tem o
matplotlib; o **3.12 tem tudo** (o `sounddevice` foi instalado nele agora).
Por isso todos os comandos abaixo usam `py -3.12`:

```
cd Projeto7_FiltrosDigitais
py -3.12 equalizador.py
```

Em outro computador: `pip install numpy scipy matplotlib sounddevice`.

---

## 3. A teoria, em uma página

### 3.1 Filtro digital = equação de diferenças = G(z)

Um filtro de 2ª ordem (biquad) calcula cada amostra de saída a partir das
duas anteriores dela mesma e da entrada atual e das duas anteriores:

```
G(z) = (b0 z² + b1 z + b2) / (z² + a1 z + a2)
y[n] = −a1·y[n−1] − a2·y[n−2] + b0·x[n] + b1·x[n−1] + b2·x[n−2]
```

> **Cuidado com o sinal:** os coeficientes do denominador entram na equação
> com o sinal **trocado**. O passa-baixa do enunciado tem `a = [1, −1,899, 0,904]`,
> que vira `y[n] = +1,899·y[n−1] − 0,904·y[n−2] + ...`

Isso está em `filtro_IIR_ordem2` (`filtros.py`), escrito amostra por amostra
como no PDF.

### 3.2 O filtro de cada banda: peaking EQ

É a fórmula do notebook `filtro_peaking_EQ` do professor, sem mudanças:

```
A = 10^(ganho_dB / 40)      ω0 = 2π·f0/fs      α = sen(ω0) / (2Q)
b = [1 + αA,  −2cos ω0,  1 − αA] / a0
a = [1 + α/A, −2cos ω0,  1 − α/A] / a0
```

- Na frequência central f0 o ganho é **exatamente** o do slider (o teste 2
  confere nas 12 bandas). O expoente é 40, e não 20, porque em f0 o ganho
  vale A², e 20·log(A²) = 40·log(A).
- Longe de f0 o ganho volta a 0 dB: o filtro só mexe na sua faixa.
- Com 0 dB, A = 1 e **b fica igual a a**: G(z) = 1, o filtro não faz nada.
- **Q** controla a largura da faixa afetada (é o mesmo Q dos exercícios 5 e 6).

### 3.3 O Q de cada banda

O notebook usa Q = 1, mas as bandas da figura não são igualmente espaçadas
(20→32 Hz é muito mais perto que 125→250 Hz). Por isso o Q é calculado para
cada banda (`fatores_q`): cada uma cobre do ponto médio (em escala log) com a
vizinha de baixo até o ponto médio com a vizinha de cima, e Q = f0 / largura.

| banda | 20 Hz | 32 Hz | 64 Hz | 125 Hz | 250 Hz … 8 kHz | 16 kHz | 20 kHz |
|---|---|---|---|---|---|---|---|
| Q | 2,11 | 1,60 | 1,45 | 1,43 | **1,41** | 2,43 | 4,47 |

Para bandas separadas por uma oitava, isso dá Q = √2 ≈ 1,41, o valor clássico
de equalizador gráfico. Nas pontas da figura as bandas são próximas, então o
Q aumenta (faixa mais estreita) para uma não invadir a outra.

---

## 4. Como o equalizador funciona

```
sliders (12 ganhos)
   │  projetar_equalizador()        uma G(z) peaking EQ por banda
   ▼
12 pares (b, a)
   │  aplicar_filtros()             a saída de um filtro é a entrada do próximo
   ▼
áudio equalizado ──► tocar: original, 0,6 s de silêncio, equalizado
   │
   └─ resposta_total()              Bode = produto das 12 respostas
```

### 4.1 "Aplicar os filtros um a um" = cascata

```python
y = audio
for f in filtros:                     # 12 bandas
    y = lfilter(f.b, f.a, y, axis=0)  # mesma equação de diferenças, em C
```

`lfilter` calcula **a mesma equação** de `filtro_IIR_ordem2` (o teste 1 mostra
diferença de 5·10⁻¹³). A única diferença é a velocidade: medido no
`teste.wav` (6 s), os 12 filtros em Python puro levam **1,7 s** e com
`lfilter` **25 ms**, cerca de 70 vezes menos. Isso permite refiltrar o áudio
sempre que um slider para de mexer sem travar a interface.

`axis=0` filtra cada canal de um áudio estéreo separadamente (teste 6).

### 4.2 A função de transferência do equalizador completo

Filtros em cascata se **multiplicam**:

```
G(z) = G1(z) · G2(z) · ... · G12(z)          (ordem 24)
```

Então a resposta em frequência do todo é o produto das respostas de cada
banda e, **em dB, a soma** dos ganhos de cada banda. É exatamente isso que
o gráfico de cima da interface mostra: as curvas cinza são as 12 bandas, a
azul é a soma.

**Por que não multiplicar os polinômios e usar uma fração só?** Dá para fazer
(`funcao_transferencia_expandida`, com `np.convolve`), e matematicamente está
certo. Na prática não funciona: as bandas graves têm polos quase em cima de
z = 1 (o de 20 Hz tem |p| = 0,99962), e num polinômio de grau 24 o
arredondamento do computador basta para deslocá-los. O `testes.py` mostra:

```
Bode da fração expandida erra até 15.0 dB nos graves
filtrar com ela: resposta ao impulso depois de 1 s = nan   (a cascata dá ~0)
```

Ou seja, a fração expandida fica instável. Por isso o Bode é calculado banda a
banda, e o áudio passa pelos filtros um de cada vez, como o enunciado pede.
É também o que se faz em equalizadores de verdade.

### 4.3 As bandas se somam

Bandas vizinhas se sobrepõem um pouco. Por isso, com três bandas vizinhas em
−10 dB o total chega a cerca de −14 dB, e com todas em +10 dB passa de +15 dB.
No gráfico isso aparece como a curva azul passando dos pontos laranja (o
ganho pedido em cada slider). É normal em equalizador gráfico, e o Bode
mostra o efeito real.

### 4.4 Detalhes que evitam problemas

| Situação | O que o código faz |
|---|---|
| Reforçar bandas faz o áudio passar de 1 e saturar a placa (clipping) | Original e equalizado são multiplicados pelo **mesmo** fator. Assim os dois cabem na faixa e a diferença de volume entre eles continua sendo a real. O status mostra quantos dB foram reduzidos. |
| Arquivo com fs < 40 kHz | Bandas a partir de fs/2 (Nyquist) não existem no sinal e são ignoradas. O status avisa quais. |
| Arquivo longo | Só os primeiros 15 s são usados: o enunciado pede um áudio curto. |
| Slider sendo arrastado | O Bode atualiza na hora. O áudio é refiltrado 250 ms depois que o slider para. |
| Gravação do microfone | É tirado o nível DC e o pico é normalizado em −6 dBFS, para sobrar folga para reforços. O áudio é salvo em `audios/gravacao.wav`. |

---

## 5. A interface

```
┌ Ganho de cada banda (dB) ─────────────────────────┐ ┌ Ajustes prontos ──┐
│ 12 sliders verticais, −10 a +10, passo de 1 dB    │ │ Plano (tudo 0 dB) │
│ 20 Hz 32 Hz 64 Hz ... 8 kHz 16 kHz 20 kHz         │ │ Figura do enunc.  │
└───────────────────────────────────────────────────┘ │ Reforço de graves │
                                                       │ Reforço de agudos │
                                                       │ Só médios (voz)   │
                                                       │ Telefone          │
                                                       └───────────────────┘
[Abrir .wav…] [Gravar 5 s]  [▶ Original → Equalizado] [▶ Original] [▶ Equalizado] [■ Parar]  [Salvar…] [Imprimir G(z)]
Áudio: teste.wav - 6.0 s, 44100 Hz, mono                       Tocando: 2º EQUALIZADO
┌ Bode do equalizador completo ──────────────────────────────────────────────┐
│ cinza = cada banda · azul = equalizador completo · laranja = slider        │
└────────────────────────────────────────────────────────────────────────────┘
┌ Espectro do áudio ─────────────────────────────────────────────────────────┐
│ cinza = original · azul = equalizado                                       │
└────────────────────────────────────────────────────────────────────────────┘
```

- **▶ Original → Equalizado** é o botão do enunciado ("o sinal resultante deve
  ser executado após o sinal original"). O status avisa quando troca de um
  para o outro.
- **Imprimir G(z)** mostra no terminal os coeficientes das 12 funções de
  transferência para os ganhos atuais, e como elas se combinam.
- O preset **Figura do enunciado** reproduz a posição dos sliders da figura do PDF.

---

## 6. Como testar

### Passo 1 — testes automáticos (30 s)

```
py -3.12 testes.py
```

Deve terminar com `Todos os testes passaram`. Os 8 testes conferem:

1. a equação de diferenças feita na mão dá o mesmo resultado que o `lfilter`;
2. em f0, cada banda dá exatamente o ganho escolhido (nas 12 bandas, com +10, −10 e +4 dB);
3. com tudo em 0 dB, o áudio sai idêntico;
4. um tom de 1 kHz com a banda de 1 kHz em +10 dB sai 3,162 vezes maior;
5. **o ganho medido no áudio (ruído branco) bate com o Bode do completo** (desvio de ~0,2 dB);
6. no estéreo, cada canal é filtrado separadamente;
7. os 12 filtros são estáveis (polos dentro do círculo unitário);
8. com fs = 32 kHz, as bandas acima de Nyquist são ignoradas.

No fim aparece a demonstração do item 4.2 (a fração expandida dá NaN).

### Passo 2 — exercícios

```
py -3.12 exercicios.py 1      (toca original e filtrado: use fone ou caixa)
py -3.12 exercicios.py        (todos, um depois do outro)
```

### Passo 3 — o equalizador

Use **fone de ouvido**. Caixinhas de notebook quase não reproduzem abaixo de
~100 Hz, e quase ninguém ouve bem 16–20 kHz. Nessas bandas, confira pelo
espectro.

```
py -3.12 equalizador.py
```

Ele abre `audios/teste.wav`. Roteiro:

| # | Faça | Deve acontecer |
|---|---|---|
| 1 | **Plano** → **▶ Original → Equalizado** | Os dois soam iguais; Bode reto em 0 dB; espectros sobrepostos |
| 2 | **Reforço de graves** → ▶ Original → Equalizado | Bumbo e baixo mais fortes; Bode sobe à esquerda; espectro azul acima do cinza nos graves |
| 3 | **Reforço de agudos** | Chimbal mais brilhante; Bode sobe à direita |
| 4 | **Telefone** | Som "de telefone", fino e sem grave |
| 5 | Arraste um slider devagar | Bode muda junto; o ponto laranja acompanha o slider |
| 6 | **Abrir .wav…** → `varredura.wav`, **Plano**, depois só **1 kHz em +10** → ▶ Equalizado | A varredura fica bem mais alta perto de **3,4 s** (é quando ela passa por 1 kHz). O volume ao longo do tempo segue o Bode |
| 7 | **Gravar 5 s** e fale perto do microfone → Só médios / Reforço de graves | A sua voz equalizada (o enunciado pede um áudio gravado) |
| 8 | **Imprimir G(z)** | Tabela de coeficientes no terminal |
| 9 | Coloque tudo em +10 → ▶ Equalizado | O status avisa a redução de volume que evita saturar |

### O que mostrar na apresentação (rubrica)

- **C — filtros atuando no sinal:** passos 2–4 e o espectro azul × cinza.
- **B — interface e áudios:** sliders, presets, ▶ Original → Equalizado, gravação.
- **A — Bode completo:** a curva azul, explicando que G = G1·G2·…·G12 e que
  em dB os ganhos se somam (item 4.2). Bom ponto extra: por que a fração
  expandida não funciona.

---

## 7. Respostas dos exercícios

Todos os números saem de `py -3.12 exercicios.py`.

### Exercício 1 — passa-baixa de 500 Hz

Sinal: soma de senoides de **300, 1500 e 5000 Hz** (amplitude 0,3 cada, 3 s
a 44100 Hz), ou seja, duas componentes acima de 500 Hz. O filtro é o do
enunciado (`butter`, ordem 2), aplicado com a equação de diferenças na mão.

| tom | entrada | saída | ganho medido | ganho do Bode |
|---|---|---|---|---|
| 300 Hz | 0,300 | 0,282 | −0,5 dB | −0,5 dB |
| 1500 Hz | 0,300 | 0,033 | −19,2 dB | −19,2 dB |
| 5000 Hz | 0,300 | 0,003 | −40,8 dB | −40,8 dB |

Na FFT do filtrado sobra praticamente só o pico de 300 Hz. **O que se ouve:**
o original é um acorde estridente; o filtrado fica "abafado" e mais baixo,
quase só o tom grave de 300 Hz. O de 1500 Hz ainda aparece bem de leve (1/9
da amplitude), e o de 5000 Hz some (1/110). O filtro não corta de uma vez em
500 Hz: ele atenua cada vez mais conforme a frequência sobe (−40 dB por
década, por ser de 2ª ordem).

### Exercício 2

`I_dB = 10·log(I / 10⁻¹²)`

- limiar da audição, 10⁻¹² W/m²: 10·log(1) = **0 dB**
- limiar da dor, 10⁰ = 1 W/m²: 10·log(10¹²) = **120 dB**

### Exercício 3

`G = 20·log(10 / 20) = 20·log(0,5) =` **−6,02 dB** (a saída tem metade da amplitude).

### Exercício 4a

O eixo do Bode do enunciado está em **rad/s**. U(t) = 50·sen(ω·t) tem ω em rad/s.

- ω = 10⁴ rad/s (f = 1592 Hz): Bode ≈ **−20 dB** → ×0,1 → saída ≈ **5** (exato: −20,2 dB → 4,87)
- ω = 10³ rad/s (f = 159 Hz): Bode ≈ **0 dB** → ×1 → saída ≈ **50** (exato: −0,04 dB → 49,7)

### Exercício 4b

−6 dB acontece em **≈ 4,1·10³ rad/s ≈ 657 Hz**. A relação saída/entrada é
10^(−6/20) = **0,50**: metade da amplitude.
(Obs.: o `butter` define o corte como −3 dB, que fica em 500 Hz, onde a relação é 0,707.)

### Exercício 5 — passa-faixa (`iirpeak`) em 2 kHz

| Q | largura (−3 dB) | f0/Q | faixa que passa | ganho em 500 Hz |
|---|---|---|---|---|
| 1 | 2000 Hz | 2000 | 1230 a 3230 Hz | −11,7 dB |
| 2 | 1000 Hz | 1000 | 1560 a 2560 Hz | −17,5 dB |
| 5 | 400 Hz | 400 | 1810 a 2210 Hz | −25,4 dB |
| 10 | 200 Hz | 200 | 1902 a 2102 Hz | −31,4 dB |
| 30 | 67 Hz | 67 | 1967 a 2034 Hz | −41,0 dB |

**Como Q atua:** é a seletividade do filtro. A largura da faixa que passa é
**f0/Q**: Q alto deixa passar uma faixa estreita em volta de 2 kHz e rejeita
mais o resto; Q baixo deixa passar uma faixa larga. O ganho em f0 é sempre
0 dB, porque o Q não muda o centro, só a largura.

### Exercício 6 — rejeita-faixa (`iirnotch`) em 2 kHz

| Q | largura rejeitada (−3 dB) | ganho em 1900 Hz |
|---|---|---|
| 1 | 2000 Hz | −19,9 dB |
| 2 | 1000 Hz | −14,0 dB |
| 5 | 400 Hz | −6,8 dB |
| 10 | 200 Hz | −2,9 dB |
| 30 | 67 Hz | −0,4 dB |

**Como Q atua:** de novo, a largura é f0/Q, mas agora da faixa **eliminada**.
Q alto faz um "buraco" estreito, que remove só a frequência-alvo e quase não
afeta as vizinhas. Q baixo come uma faixa larga. Em f0 o ganho é zero
(−∞ dB), porque o filtro tem um zero exatamente em f0. **Mudando f0**
(60 Hz, 1 kHz, 5 kHz) o buraco só muda de lugar.

**Utilidades:** remover o **zumbido de 60 Hz** da rede elétrica (e harmônicos
de 120 e 180 Hz) em áudio e em sinais de ECG; eliminar **microfonia**
(apito de realimentação) numa frequência fixa; remover um tom interferente
sem estragar o resto do sinal (por exemplo, um tom DTMF do Projeto 6).

---

## 8. Escolhas que vale saber explicar

- **Bandas:** usei as da figura do PDF (20, 32, 64, 125, 250, 500 Hz, 1, 2, 4,
  8, 16, 20 kHz). O site lista 31, 63, 125… (11 bandas) e diz "ajuste
  conforme necessário". Para trocar, basta mudar `BANDAS` em `filtros.py`:
  o Q é recalculado sozinho.
- **Ordem dos filtros na cascata:** não importa. Multiplicação é comutativa,
  então G1·G2 = G2·G1.
- **Por que `lfilter` e não a função na mão no equalizador:** é a mesma conta
  (teste 1), mas ~70 vezes mais rápida (1,7 s × 25 ms). A versão na mão é usada no
  exercício 1 e no teste 1.
- **O 20 Hz e o 20 kHz quase não se ouvem:** é limite do alto-falante e do
  ouvido, não do filtro. O espectro mostra que eles atuam.
