
# Projeto 8 (parte 2) - "Altere a taxa / altere a portadora e observe a FFT"
#
#   python experimentos_psk.py                -> as duas tabelas + os dois gráficos
#   python experimentos_psk.py --sem-janela   -> só tabelas; gráficos em graficos_psk/
#
# Usa bits aleatórios (metade 0, metade 1), que é o caso da teoria. Um texto tem
# mais zeros que uns (o bit mais alto do ASCII é 0), e isso põe um pico extra em
# fc; o chat mostra esse caso. Cada sinal também passa pelo canal simulado para
# ver se ainda é recebido.

import argparse
import os
import sys

import numpy as np

from psk import FS, banda_medida, banda_teorica, canal, modular_bpsk, montar_quadro, pico_em, receber

PASTA_GRAFICOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos_psk")
TAXAS = (50, 100, 200, 400, 1000)
PORTADORAS = (2000, 3000, 4000, 5000, 6000)
N_BITS = 2000
FRASE = "Teste de taxa e portadora!"


def bits_aleatorios(n=N_BITS, semente=8):
    return list(np.random.default_rng(semente).integers(0, 2, n))


def medir(taxa, fc):
    bits = bits_aleatorios()
    audio, (ini, fim) = modular_bpsk(bits, fc, taxa, abertura=0, fim=0)
    x = audio[ini:fim]
    quadro, _ = montar_quadro(FRASE)
    sinal, _ = modular_bpsk(quadro, fc, taxa)
    recebidas = receber(canal(sinal, snr_db=15, ppm=50), fc, taxa)
    chegou = bool(recebidas) and recebidas[0].ok and recebidas[0].texto == FRASE
    return x, {
        "pico": pico_em(x),
        "b90": banda_medida(x, fc, fracao=0.9),
        "b99": banda_medida(x, fc, fracao=0.99),
        "recebeu": chegou,
    }


def num(x, casas=0):
    return f"{x:.{casas}f}".replace(".", ",")


def main():
    parser = argparse.ArgumentParser(description="Efeito da taxa e da portadora na FFT do BPSK")
    parser.add_argument("--sem-janela", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import matplotlib
    if args.sem_janela:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from graficos_psk import desenhar_variacao

    fc = 4000
    print(f"\n=== Mudando a TAXA (portadora {fc} Hz, {N_BITS} bits aleatórios)")
    print(f"{'taxa':>8} {'amostras/bit':>13} {'ciclos/bit':>11} {'lóbulo principal':>18} "
          f"{'90% medido':>11} {'99% medido':>11} {'100 caracteres':>15} {'canal simulado':>15}")
    por_taxa = []
    for taxa in TAXAS:
        x, r = medir(taxa, fc)
        por_taxa.append((taxa, x, fc, taxa))
        print(f"{taxa:>6} bit/s {num(FS / taxa, 1):>11} {num(fc / taxa, 1):>11} "
              f"{fc - taxa:>7}-{fc + taxa} Hz ({banda_teorica(taxa)}) "
              f"{num(r['b90']):>6} Hz {num(r['b99']):>8} Hz {num(800 / taxa, 1):>12} s "
              f"{'recebeu' if r['recebeu'] else 'FALHOU':>15}")
    print("-> a banda acompanha a taxa: o dobro de bits por segundo ocupa o dobro de Hz.")
    print("   Cada bit dura 1/taxa; um pedaço de senoide mais curto tem espectro mais largo.")

    taxa = 100
    print(f"\n=== Mudando a PORTADORA (taxa {taxa} bit/s)")
    print(f"{'portadora':>10} {'pico da FFT':>12} {'lóbulo principal':>18} {'90% medido':>11} {'canal simulado':>15}")
    por_portadora = []
    for fc in PORTADORAS:
        x, r = medir(taxa, fc)
        por_portadora.append((fc, x, fc, taxa))
        print(f"{fc:>7} Hz {num(r['pico']):>9} Hz {fc - taxa:>8}-{fc + taxa} Hz "
              f"{num(r['b90']):>8} Hz {'recebeu' if r['recebeu'] else 'FALHOU':>15}")
    print("-> a portadora só MUDA DE LUGAR o espectro: o formato e a largura são os mesmos.")
    print("   É a multiplicação pela portadora deslocando o espectro, como no AM da parte 1.")

    fig1 = plt.figure("Mudando a taxa", figsize=(12, 7.5), layout="constrained")
    desenhar_variacao(fig1, por_taxa, "taxa")
    fig1.suptitle(f"Mesma portadora ({4000} Hz), taxas diferentes: a largura do espectro acompanha a taxa",
                  x=0.01, ha="left", fontsize=11)
    fig2 = plt.figure("Mudando a portadora", figsize=(12, 7.5), layout="constrained")
    desenhar_variacao(fig2, por_portadora, "portadora")
    fig2.suptitle(f"Mesma taxa ({taxa} bit/s), portadoras diferentes: o espectro só muda de lugar",
                  x=0.01, ha="left", fontsize=11)
    os.makedirs(PASTA_GRAFICOS, exist_ok=True)
    for nome, fig in (("taxas", fig1), ("portadoras", fig2)):
        caminho = os.path.join(PASTA_GRAFICOS, f"{nome}.png")
        fig.savefig(caminho, dpi=110)
        print(caminho)
    if not args.sem_janela:
        plt.show()


if __name__ == "__main__":
    main()
