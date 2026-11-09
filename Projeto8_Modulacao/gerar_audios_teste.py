
# Projeto 8 (parte 1) - gera 3 áudios de teste em audios/originais/
#
#   estacao_1.wav   voz sintetizada (Windows, voz pt-BR "Maria"): "Rádio um..."
#   estacao_2.wav   melodia sintética (notas de 262 a 784 Hz)
#   estacao_3.wav   voz sintetizada: "Aqui é a rádio três..."
#
#   python gerar_audios_teste.py
#
# O enunciado pede 3 áudios GRAVADOS: no rádio (python radio_am.py), o botão
# "● Gravar" de cada estação substitui o arquivo dela pela sua gravação. Estes
# aqui são a alternativa reprodutível (o mesmo sinal toda vez), usada pelos testes.
# Sem a voz do Windows (outro sistema operacional), as estações 1 e 3 viram
# melodias diferentes.

import base64
import os
import subprocess
import tempfile

import numpy as np

from am import FS, carregar_audio, normalizar, salvar_wav, suavizar_bordas

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_ORIGINAIS = os.path.join(PASTA, "audios", "originais")
PICO = 0.8

FRASES = {
    1: "Rádio um, de nove a doze quilohertz. Bom dia!",
    3: "Aqui é a rádio três, de quinze a dezoito quilohertz.",
}


def falar(texto, caminho):
    """Sintetiza `texto` com a voz do Windows num .wav de 44,1 kHz. Retorna True se deu certo."""
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voz = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -eq 'pt-BR' }} | Select-Object -First 1
if ($voz) {{ $s.SelectVoice($voz.VoiceInfo.Name) }}
$s.Rate = 1
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{caminho}', $formato)
$s.Speak('{texto}')
$s.Dispose()
"""
    # -EncodedCommand (UTF-16 em base64) evita problema com acentos e aspas
    codificado = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", codificado],
                       check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.exists(caminho) and os.path.getsize(caminho) > 1000


def aparar_silencio(audio, fs=FS, limiar=0.02, margem=0.1):
    """Corta o silêncio do começo e do fim, deixando `margem` s de cada lado."""
    com_som = np.nonzero(np.abs(audio) > limiar * np.max(np.abs(audio)))[0]
    inicio = max(0, com_som[0] - int(margem * fs))
    return audio[inicio:com_som[-1] + int(margem * fs)]


def nota(freq, duracao, fs=FS, harmonicos=4):
    """Nota com alguns harmônicos de amplitude 1/k e um envelope de ataque e decaimento."""
    t = np.arange(int(duracao * fs)) / fs
    s = sum(np.sin(2 * np.pi * k * freq * t) / k for k in range(1, harmonicos + 1))
    return s * np.minimum(1, t / 0.01) * np.exp(-t / (duracao * 0.7))


def melodia(notas, batida=0.25, fs=FS):
    return np.concatenate([nota(f, batida, fs) for f in notas])


# Duas melodias simples (Hz). A segunda só é usada sem a voz do Windows.
MELODIA_A = [262, 330, 392, 523, 392, 330, 262, 330, 392, 523, 659, 523, 392, 330, 294, 262]
MELODIA_B = [392, 392, 440, 392, 523, 494, 392, 392, 440, 392, 587, 523, 784, 659, 523, 494]


def main():
    os.makedirs(PASTA_ORIGINAIS, exist_ok=True)
    with tempfile.TemporaryDirectory() as pasta_temp:
        for numero in (1, 2, 3):
            caminho = os.path.join(PASTA_ORIGINAIS, f"estacao_{numero}.wav")
            temporario = os.path.join(pasta_temp, f"voz_{numero}.wav")
            if numero in FRASES and falar(FRASES[numero], temporario):
                audio = aparar_silencio(carregar_audio(temporario))
                origem = f'voz: "{FRASES[numero]}"'
            elif numero == 2:
                audio, origem = melodia(MELODIA_A), "melodia sintética"
            else:
                audio, origem = melodia(MELODIA_B), "melodia sintética (sem voz do Windows)"
            audio = suavizar_bordas(normalizar(audio - np.mean(audio), PICO))
            salvar_wav(caminho, audio, FS)
            print(f"{caminho}  ({len(audio) / FS:.1f} s)  {origem}")


if __name__ == "__main__":
    main()
