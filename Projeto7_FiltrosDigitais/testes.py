
# Projeto 7 - testes automáticos dos filtros (não toca som nem abre janelas)
#
#   python testes.py
#
# Cada teste imprime OK ou FALHOU. O último bloco não é teste: mostra por que o
# equalizador aplica os filtros um a um em vez de usar a G(z) expandida.

import sys

import numpy as np
from scipy.signal import freqz, lfilter, welch

from filtros import (BANDAS, FS, aplicar_filtros, em_db, fatores_q, filtro_IIR_ordem2,
                     funcao_transferencia_expandida, projetar_equalizador, resposta_total)

falhas = 0


def confere(condicao, descricao):
    global falhas
    print(f"[{'OK' if condicao else 'FALHOU'}] {descricao}")
    if not condicao:
        falhas += 1


rng = np.random.default_rng(0)
ruido = rng.standard_normal(4 * FS) * 0.1       # 4 s de ruído branco: tem todas as frequências

# 1. A equação de diferenças feita na mão é a mesma conta que o lfilter faz
filtros = projetar_equalizador([3, -2, 5, 0, -7, 10, -10, 4, 1, -5, 8, -3])
x = ruido[:FS // 2]
y_mao = x
for f in filtros:
    y_mao = filtro_IIR_ordem2(y_mao, f.b, f.a)
erro = np.max(np.abs(y_mao - aplicar_filtros(x, filtros)))
confere(erro < 1e-10, f"equação de diferenças na mão = lfilter (diferença máxima {erro:.1e})")

# 2. Na frequência central, cada banda sozinha dá exatamente o ganho do slider
piores = []
for ganho in (10, -10, 4):
    for i, f0 in enumerate(BANDAS):
        ganhos = [0] * 12
        ganhos[i] = ganho
        (filtro,) = [f for f in projetar_equalizador(ganhos) if f.f0 == f0]
        _, h = freqz(filtro.b, filtro.a, worN=[f0], fs=FS)
        piores.append(abs(em_db(h[0]) - ganho))
confere(max(piores) < 1e-6, f"ganho em f0 = ganho escolhido, nas 12 bandas (erro máx. {max(piores):.1e} dB)")

# 3. Tudo em 0 dB: o áudio sai idêntico
igual = np.max(np.abs(aplicar_filtros(ruido, projetar_equalizador([0] * 12)) - ruido))
confere(igual < 1e-12, f"equalizador plano não altera o áudio (diferença {igual:.1e})")

# 4. Um tom de 1 kHz com a banda de 1 kHz em +10 dB sai 3,16 vezes maior
t = np.arange(FS) / FS
tom = 0.1 * np.sin(2 * np.pi * 1000 * t)
ganhos = [0] * 12
ganhos[BANDAS.index(1000)] = 10
saida = aplicar_filtros(tom, projetar_equalizador(ganhos))
razao = np.max(np.abs(saida[FS // 2:])) / 0.1  # segunda metade: transitório já passou
confere(abs(razao - 10**(10 / 20)) < 0.01, f"tom de 1 kHz amplificado {razao:.3f}x (esperado 3,162x = +10 dB)")

# 5. O Bode do equalizador completo bate com o que o áudio realmente sofre
ganhos = [int(g) for g in rng.integers(-10, 11, 12)]
filtros = projetar_equalizador(ganhos)
saida = aplicar_filtros(ruido, filtros)
f, p_entrada = welch(ruido, FS, nperseg=4096)
_, p_saida = welch(saida, FS, nperseg=4096)
medido = 10 * np.log10(p_saida / p_entrada)          # potência: 10 log10
faixa = (f >= 100) & (f <= 20000)                    # abaixo de 100 Hz a resolução do welch é grossa
teoria = em_db(resposta_total(filtros, f[faixa]))
desvio = np.max(np.abs(medido[faixa] - teoria))
confere(desvio < 1.0, f"ganho medido no ruído = Bode do completo (desvio máx. {desvio:.2f} dB, ganhos {ganhos})")

# 6. Áudio estéreo: os dois canais são filtrados, cada um por conta própria
estereo = np.column_stack([ruido[:FS], -0.5 * ruido[:FS]])
saida = aplicar_filtros(estereo, filtros)
so_esquerdo = aplicar_filtros(estereo[:, 0], filtros)
confere(saida.shape == estereo.shape and np.allclose(saida[:, 0], so_esquerdo)
        and np.allclose(saida[:, 1], -0.5 * so_esquerdo), "estéreo: cada canal filtrado separadamente")

# 7. Todos os 12 filtros são estáveis (polos dentro do círculo unitário)
raio = max(np.max(np.abs(np.roots(f.a))) for f in projetar_equalizador([10] * 12))
confere(raio < 1, f"12 filtros estáveis: maior |polo| = {raio:.5f} < 1")

# 8. Bandas a partir de fs/2 (Nyquist) não existem no sinal digital
confere([f.f0 for f in projetar_equalizador([0] * 12, fs=32000)] == list(BANDAS[:-2]),
        "fs = 32 kHz: bandas de 16 e 20 kHz (>= Nyquist de 16 kHz) são ignoradas")

print("\nQ de cada banda:", ", ".join(f"{f0} Hz: {q:.2f}" for f0, q in zip(BANDAS, fatores_q())))

# Por que não usar a G(z) expandida (ordem 24) de uma vez só
print("\nG(z) expandida (12 polinômios multiplicados, ordem 24) com todas as bandas em +10 dB:")
filtros = projetar_equalizador([10] * 12)
b_total, a_total = funcao_transferencia_expandida(filtros)
freqs = np.logspace(1, np.log10(20000), 500)
_, h_expandida = freqz(b_total, a_total, worN=freqs, fs=FS)
erro_bode = np.max(np.abs(em_db(h_expandida) - em_db(resposta_total(filtros, freqs))))
impulso = np.zeros(FS)
impulso[0] = 1
with np.errstate(all="ignore"):
    final = lfilter(b_total, a_total, impulso)[-1]
print(f"  Bode da fração expandida erra até {erro_bode:.1f} dB nos graves")
print(f"  filtrar com ela: resposta ao impulso depois de 1 s = {final} (a cascata dá ~0)")
print("  -> por isso o equalizador aplica os 12 filtros um a um e o Bode multiplica as respostas")

print(f"\n{'Todos os testes passaram' if falhas == 0 else f'{falhas} teste(s) falharam'}")
sys.exit(1 if falhas else 0)
