
# Projeto 8 (parte 2) - testes automáticos do PSK (não toca som nem abre janelas)
#
#   python testes_psk.py
#
# Cada teste imprime OK ou FALHOU. Os que passam pelo "canal" usam a simulação de
# psk.canal(): atraso, eco, zumbido de 120 Hz, voz de fundo, ruído e relógios diferentes.

import sys
import time

import numpy as np

from psk import (BARKER, FC, FS, TAXA, Receptor, banda_medida, bits_no_quadro, bits_para_bytes,
                 bytes_para_bits, canal, crc16, modular_bpsk, montar_quadro, pico_em, receber,
                 transmitir)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

falhas = 0


def confere(condicao, descricao):
    global falhas
    print(f"[{'OK' if condicao else 'FALHOU'}] {descricao}")
    if not condicao:
        falhas += 1


def recebe_igual(texto, **kw_canal):
    audio, *_ = transmitir(texto)
    msgs = receber(canal(audio, **kw_canal))
    return len(msgs) == 1 and msgs[0].ok and msgs[0].texto == texto, msgs


inicio = time.time()

# 1. Texto -> bytes -> bits e de volta
confere(bytes_para_bits(b"A") == [0, 1, 0, 0, 0, 0, 0, 1] and bits_para_bytes(bytes_para_bits(b"Oi!")) == b"Oi!",
        "'A' = 0x41 = 01000001 e bits -> bytes devolve o original")

# 2. UTF-8: acento ocupa 2 bytes
_, dados = montar_quadro("Olá")
confere(dados == b"Ol\xc3\xa1", f"'Olá' = 3 caracteres e {len(dados)} bytes UTF-8 (á = C3 A1)")

# 3. CRC-16 igual ao do Projeto 4 e sensível a 1 bit
alterado = bytearray(b"Camada Fisica")
alterado[3] ^= 0x01
confere(crc16(b"123456789") == 0x31C3 and crc16(alterado) != crc16(b"Camada Fisica"),
        "CRC-16/XMODEM: 123456789 -> 0x31C3 (valor de referência) e 1 bit trocado muda o CRC")

# 4. Tamanho do quadro
bits, dados = montar_quadro("Olá, mundo!")
confere(len(bits) == bits_no_quadro(len(dados)) == 13 + 16 + 96 + 16,
        f"'Olá, mundo!' = 12 bytes -> quadro de {len(bits)} bits (13 + 16 + 96 + 16)")

# 5. Bit 0 = fase 0°, bit 1 = fase 180°
sinal, (ini, _) = modular_bpsk([0] * 5 + [1] * 5, abertura=0, fim=0)    # bits 2 e 7: longe das rampas
c = np.cos(2 * np.pi * FC * np.arange(len(sinal)) / FS)
n = FS // TAXA
p0, p1 = np.dot(sinal[2 * n:3 * n], c[2 * n:3 * n]), np.dot(sinal[7 * n:8 * n], c[7 * n:8 * n])
confere(p0 > 0 and p1 < 0 and abs(p0 + p1) < 1e-6 * abs(p0),
        "bit 0 está em fase com cos(2π fc t) e bit 1 está invertido (180°)")

# 6. 100 bit/s: 441 amostras por bit, duração = bits / 100
audio, (ini, fim) = modular_bpsk(bits)
confere(fim - ini == len(bits) * 441, f"{len(bits)} bits a 100 bit/s = {(fim - ini) / FS:.2f} s ({fim - ini} amostras)")

# 7. Código de Barker: correlação deslocada nunca passa de 1 (o pico é 13)
lados = [abs(np.dot(BARKER[k:], BARKER[:-k])) for k in range(1, 13)]
confere(max(lados) == 1, f"Barker 13: pico 13 e correlações deslocadas ≤ {max(lados)}")

# 8. Canal perfeito
ok, _ = recebe_igual("Olá, mundo!", snr_db=80, eco=False, ruido_grave=False, atraso=0.1)
confere(ok, "canal perfeito: chega 'Olá, mundo!' com CRC ok")

# 9. Canal "de sala": atraso, eco, zumbido, voz de fundo, SNR 20 dB
ok, msgs = recebe_igual("Camada Física da Computação")
confere(ok, f"canal com eco, zumbido e ruído: chega igual (SNR medida {msgs[0].snr_db:.1f} dB)" if msgs
        else "canal com eco, zumbido e ruído")

# 10. Ruído mais forte que o sinal
ok, _ = recebe_igual("ruido forte", snr_db=-5)
confere(ok, "SNR de -5 dB no canal (ruído mais forte que o sinal): ainda chega")

# 11. Relógios diferentes e mensagem longa
longa = ("Relogios diferentes nas duas placas de som. " * 6)[:255]
ok_ppm = all(recebe_igual(longa, ppm=p)[0] for p in (-500, 500))
ok_hz = all(recebe_igual("desvio de frequencia", desvio_hz=h)[0] for h in (-10, 10))
confere(ok_ppm and ok_hz, "255 bytes (21 s) com relógios ±500 ppm, e desvio de ±10 Hz na portadora")

# 12. Duas mensagens seguidas no mesmo áudio, entregue aos pedaços
a1, *_ = transmitir("primeira")
a2, *_ = transmitir("segunda")
msgs = receber(canal(np.concatenate([a1, np.zeros(FS // 2), a2])))
confere([m.texto for m in msgs] == ["primeira", "segunda"], "duas mensagens seguidas: chegam as duas, na ordem")

# 13. Outras taxas e portadoras
casos = [(50, 2000), (200, 3000), (300, 6000), (1000, 4000)]
resultados = []
for taxa, fc in casos:
    bits, _ = montar_quadro(f"{taxa} bit/s em {fc} Hz")
    msgs = receber(canal(modular_bpsk(bits, fc, taxa)[0]), fc, taxa)
    resultados.append(bool(msgs) and msgs[0].ok)
confere(all(resultados), "também funciona com " + ", ".join(f"{t} bit/s em {f} Hz" for t, f in casos))

# 14. Sem mensagem não inventa mensagem (nem no silêncio perfeito logo depois de uma)
rx = Receptor()
rng = np.random.default_rng(5)
falsas = sum(len(rx.alimentar(rng.normal(0, 0.01, 4410))) for _ in range(600))
tom = 0.3 * np.sin(2 * np.pi * FC * np.arange(30 * FS) / FS)
falsas += len(receber(tom))
audio, *_ = transmitir("e depois silêncio")
depois = receber(np.concatenate([np.zeros(FS // 10), audio, np.zeros(5 * FS)]))
falsas += len(depois) - 1
confere(falsas == 0, "60 s de ruído, 30 s de apito na portadora e 5 s de silêncio perfeito depois de "
                    "uma mensagem: nenhuma mensagem falsa")

# 15. Erro no meio da mensagem: o CRC acusa
bits, dados = montar_quadro("o CRC pega isso")
audio, (ini, _) = modular_bpsk(bits)
k = 13 + 16 + 20                                         # um bit no meio dos dados
a, b = ini + k * 441, ini + (k + 1) * 441
audio[a:b] *= -1                                         # inverte a fase só desse bit
msgs = receber(canal(audio, snr_db=40))
confere(len(msgs) == 1 and not msgs[0].ok, f"1 bit invertido no meio: chega {msgs[0].texto!r} e o CRC acusa erro"
        if msgs else "1 bit invertido no meio: o CRC acusa erro")

# 16. Banda: lóbulo principal 2 x taxa, e 90% da energia em ~1,6 x taxa (bits aleatórios)
proporcoes = []
for taxa in (50, 100, 200, 400):
    x, (i, f) = modular_bpsk(list(np.random.default_rng(1).integers(0, 2, 2000)), FC, taxa, abertura=0, fim=0)
    proporcoes.append(banda_medida(x[i:f], FC) / taxa)
confere(max(proporcoes) - min(proporcoes) < 0.1 and 1.4 < np.mean(proporcoes) < 1.8,
        f"banda de 90% / taxa = {', '.join(f'{p:.2f}' for p in proporcoes)} (a banda acompanha a taxa)")

# 17. Mudar a portadora só desloca o espectro
bits = list(np.random.default_rng(2).integers(0, 2, 2000))
picos, larguras = [], []
for fc in (2000, 4000, 6000):
    x, (i, f) = modular_bpsk(bits, fc, 100, abertura=0, fim=0)
    picos.append(pico_em(x[i:f]))
    larguras.append(banda_medida(x[i:f], fc))
confere(all(abs(p - fc) < 50 for p, fc in zip(picos, (2000, 4000, 6000))) and np.ptp(larguras) < 5,
        f"portadora 2/4/6 kHz: centro em {', '.join(f'{p:.0f}' for p in picos)} Hz, "
        f"mesma largura ({', '.join(f'{w:.0f}' for w in larguras)} Hz)")

print(f"\n{'Todos os testes passaram' if falhas == 0 else f'{falhas} teste(s) falharam'}"
      f"  ({time.time() - inicio:.0f} s)")
sys.exit(1 if falhas else 0)
