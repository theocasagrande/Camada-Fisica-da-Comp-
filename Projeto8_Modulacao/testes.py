
# Projeto 8 (parte 1) - testes automáticos da modulação AM (não toca som nem abre janelas)
#
#   python testes.py
#
# Cada teste imprime OK ou FALHOU. Os testes 6 a 8 usam os áudios de
# audios/originais/ (gere com "python gerar_audios_teste.py" se não existirem).
# O último bloco não é teste: mostra por que os filtros estão em SOS.

import os
import sys
import tempfile

import numpy as np
from scipy.signal import butter, freqz, sosfreqz

from am import (ESTACOES, FS, analisar, carregar_audio, criar_estacao, demodular, espectro, filtrar,
                fora_da_faixa, limitar_banda, modular, passa_baixa, passa_faixa, portadora, rebater,
                resposta_db, salvar_wav, senoide, simular)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASTA = os.path.dirname(os.path.abspath(__file__))
falhas = 0


def confere(condicao, descricao):
    global falhas
    print(f"[{'OK' if condicao else 'FALHOU'}] {descricao}")
    if not condicao:
        falhas += 1


def amplitude_em(x, f0, fs=FS):
    """Amplitude do maior pico da FFT a menos de 20 Hz de f0."""
    f, X = espectro(x, fs)
    perto = np.abs(f - f0) < 20
    return np.max(X[perto])


n = 2 * FS
fm, fc = 2000, 15000

# 1. Somar não é modular: a soma mantém a componente de 2 kHz, fora de 12-18 kHz
soma = senoide(fm, n) + portadora(fc, n)
fora = fora_da_faixa(soma, (12000, 18000))
confere(abs(fora - 0.5) < 1e-6, f"exercício 1: a soma tem {fora:.0%} da energia fora de 12-18 kHz (a de 2 kHz)")

# 2. Multiplicar desloca: só fc - fm e fc + fm, cada um com amplitude 0,5
produto = senoide(fm, n) * portadora(fc, n)
a13, a17 = amplitude_em(produto, fc - fm), amplitude_em(produto, fc + fm)
fora = fora_da_faixa(produto, (fc - fm - 1, fc + fm + 1))
confere(abs(a13 - 0.5) < 1e-3 and abs(a17 - 0.5) < 1e-3 and fora < 1e-12,
        f"exercício 3: produto = 0,5 em 13 kHz ({a13:.4f}) e em 17 kHz ({a17:.4f}), nada mais ({fora:.0e})")

# 3. As estações: portadora no centro e mensagem cortada em 80% da meia-largura
esperado = [(10500, 1200), (13500, 1200), (16500, 1200)]
confere([(e.fc, e.corte) for e in ESTACOES] == esperado,
        "estações: portadoras 10,5 / 13,5 / 16,5 kHz, mensagem até 1,2 kHz")

# 4. Demodular um tom puro devolve o tom, com a amplitude certa
e = ESTACOES[1]
tom = 0.5 * np.sin(2 * np.pi * 700 * np.arange(n) / FS)
saida, _ = demodular(modular(tom, e.fc), e)
amp = amplitude_em(saida[FS // 2:-FS // 2], 700)
confere(abs(amp - 0.5) < 0.005, f"tom de 700 Hz modulado em 13,5 kHz e demodulado: amplitude {amp:.4f} (era 0,5)")

# 5. Erro de fase na portadora local: a saída fica multiplicada por cos(erro)
fatores = []
for graus in (0, 60, 90):
    saida, _ = demodular(modular(tom, e.fc), e, fase=np.radians(graus))
    fatores.append(amplitude_em(saida[FS // 2:-FS // 2], 700) / 0.5)
confere(abs(fatores[0] - 1) < 0.01 and abs(fatores[1] - 0.5) < 0.01 and fatores[2] < 0.01,
        f"erro de fase 0° / 60° / 90°: saída × {fatores[0]:.3f} / {fatores[1]:.3f} / {fatores[2]:.4f} "
        f"(cos = 1 / 0,5 / 0)")

# 6 a 8. A cadeia completa com os 3 áudios
caminhos = [os.path.join(PASTA, "audios", "originais", f"estacao_{k}.wav") for k in (1, 2, 3)]
if all(os.path.exists(c) for c in caminhos):
    cadeia = simular([carregar_audio(c) for c in caminhos])
    analise = analisar(cadeia)
    pior = max(r.fora_db for r in analise)
    confere(pior < -60, f"nenhum modulado invade outra faixa (pior: {pior:.1f} dB fora da própria)")
    menor = min(r.correlacao for r in analise)
    snr = min(r.snr_db for r in analise)
    confere(menor > 0.9999 and snr > 40,
            f"demodulado = transmitido nas 3 estações (correlação mínima {menor:.6f}, SNR mínima {snr:.1f} dB)")
    interf = max(r.interferencia_db for r in analise)
    confere(interf < -60, f"interferência das outras estações depois de demodular: {interf:.1f} dB")
else:
    print("[--] testes 6 a 8 pulados: rode antes  python gerar_audios_teste.py")

# 9. Aliasing: a cópia em 2fc da estação 3 (33 kHz) aparece em 44,1 - 33 = 11,1 kHz
e3 = ESTACOES[2]
_, produto = demodular(modular(tom, e3.fc), e3)
esperadas = (rebater(2 * e3.fc - 700), rebater(2 * e3.fc + 700))      # 33,7 e 32,3 kHz
amps = [amplitude_em(produto, f) for f in esperadas]
# amplitude 0,5 (tom) x ½ (modulação) x ½ (demodulação) = 0,125 em cada uma
confere(np.allclose(esperadas, (11800, 10400)) and np.allclose(amps, 0.125, atol=0.002),
        f"aliasing: 2fc ± 700 Hz = 32,3 e 33,7 kHz aparecem em {esperadas[0]:.0f} e {esperadas[1]:.0f} Hz "
        f"(amplitudes {amps[0]:.3f} e {amps[1]:.3f}, como esperado 0,5 x ½ x ½)")

# 10. Sem multiplicar pela portadora, o passa-baixa não ouve nada: o modulado não tem nada perto de 0 Hz
baixo = filtrar(passa_baixa(e.meia_largura), modular(tom, e.fc))[FS // 2:-FS // 2]   # longe das bordas
razao = np.sqrt(np.mean(baixo ** 2) / np.mean(tom ** 2))
confere(razao < 1e-3, f"só o passa-baixa, sem a portadora: sobra {razao:.1e} do sinal (a informação está em 13,5 kHz)")

# 11. Os filtros são estáveis: todos os polos dentro do círculo unitário
maior = 0
for sos in [passa_baixa(e.corte), passa_baixa(e.meia_largura)] + \
           [passa_faixa(x.f_ini, x.f_fim) for x in ESTACOES]:
    for secao in sos:
        maior = max(maior, np.max(np.abs(np.roots(secao[3:]))))
confere(maior < 1, f"filtros estáveis: maior |polo| = {maior:.5f} < 1")

# 12. Ida e volta: o ganho em dB dobra (|H|²) e a borda do passa-faixa fica em -6 dB
borda = resposta_db(passa_faixa(9000, 12000), [9000, 12000])
confere(np.allclose(borda, -6.02, atol=0.05), f"passa-faixa ida e volta: {borda[0]:.2f} dB nas bordas (-3 dB x 2)")

# 13. Áudio a 48 kHz é reamostrado para 44,1 kHz
with tempfile.TemporaryDirectory() as pasta:
    caminho = os.path.join(pasta, "48k.wav")
    salvar_wav(caminho, 0.5 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000), 48000)
    audio = carregar_audio(caminho)
    pico = espectro(audio)[0][np.argmax(espectro(audio)[1])]
confere(len(audio) == FS and abs(pico - 440) < 2,
        f"wav de 48 kHz: 1 s vira {len(audio)} amostras a 44,1 kHz, tom continua em {pico:.0f} Hz")

# 14. Exercício 4: com passa-baixa de 800 Hz a mensagem de 20-2000 Hz cabe em 14-16 kHz
e4 = criar_estacao(4, (14000, 16000))
rng = np.random.default_rng(4)
m = sum(senoide(f, n, fase=rng.uniform(0, 2 * np.pi)) for f in np.linspace(20, 2000, 40)) / 40
fora = fora_da_faixa(modular(limitar_banda(m, e4), e4.fc), (14000, 16000))
confere(fora < 1e-5, f"exercício 4: depois do passa-baixa, {10 * np.log10(fora):.0f} dB fora de 14-16 kHz")

print(f"\n{'Todos os testes passaram' if falhas == 0 else f'{falhas} teste(s) falharam'}")

# ------------------------------------------------------------------ demonstração
print("\nPor que SOS (cascata de biquads) e não uma fração só (b, a), como no Projeto 7:")
for ordem, corte in ((12, 1500), (12, 800)):
    b, a = butter(ordem, corte, fs=FS, output="ba")
    sos = butter(ordem, corte, fs=FS, output="sos")
    f = np.linspace(10, 5000, 2000)
    _, h_ba = freqz(b, a, worN=f, fs=FS)
    _, h_sos = sosfreqz(sos, worN=f, fs=FS)
    erro = np.max(np.abs(20 * np.log10(np.abs(h_ba)) - 20 * np.log10(np.abs(h_sos))))
    print(f"  passa-baixa ordem {ordem}, {corte} Hz em (b, a): erro de até {erro:.2f} dB em relação ao SOS")
print("  Em SOS cada biquad tem só 2 polos e o erro some. Quanto mais baixo o corte, mais os")
print("  polos se amontoam perto de z = 1 e pior fica a fração (no Projeto 7 virou NaN).")

sys.exit(1 if falhas else 0)
