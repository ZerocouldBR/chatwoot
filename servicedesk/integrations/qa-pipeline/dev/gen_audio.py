"""Gera áudios SINTÉTICOS de atendimento com o Piper TTS (local, gratuito, MIT).

Rodar num container (ver dev/README.md):
  pip install piper-tts && python dev/gen_audio.py --out dev/audio/out --voices /models/piper

Saídas por roteiro:
  <nome>.mono8k.wav    mono 8 kHz, banda telefônica (como a gravação do PABX)
  <nome>.stereo8k.wav  estéreo 8 kHz: atendente no canal 0 e cliente no canal 1
  <nome>.mp3           mono 32 kbps (formato que o sd-ops/pbx-bridge armazena)
  <nome>.turns.json    tempos reais de cada fala (para avaliar a separação por canal)
E também: parcial_bom.mp3 (metade do bom_atendimento), corrompido.mp3 (bytes inválidos)
e silencio.mp3 (sem fala).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from dialogues import DIALOGUES  # noqa: E402

VOICES = {
    "A": "pt_BR-faber-medium",
    "C": "pt_BR-cadu-medium",
}
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/{name}/{quality}/{voice}.onnx"


def ensure_voice(voice: str, root: str) -> str:
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, voice + ".onnx")
    for suffix in ("", ".json"):
        dst = path + suffix
        if not os.path.exists(dst):
            url = HF.format(name=voice.split("-")[1], quality=voice.split("-")[2], voice=voice) + suffix
            print("baixando", url, flush=True)
            urllib.request.urlretrieve(url, dst)
    return path


def synth(voice, text: str) -> tuple:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        if hasattr(voice, "synthesize_wav"):
            voice.synthesize_wav(text, w)
        else:  # API antiga do piper-tts
            voice.synthesize(text, w)
    buf.seek(0)
    with wave.open(buf, "rb") as r:
        sr = r.getframerate()
        data = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16)
    return sr, data


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dev/audio/out")
    ap.add_argument("--voices", default="/models/piper")
    args = ap.parse_args()
    from piper import PiperVoice

    os.makedirs(args.out, exist_ok=True)
    voices = {k: PiperVoice.load(ensure_voice(v, args.voices)) for k, v in VOICES.items()}
    rng = np.random.default_rng(42)
    for name, turns in DIALOGUES.items():
        sr = None
        left, right, meta, t = [], [], [], 0.0
        for role, text in turns:
            sr, pcm = synth(voices[role], text)
            gap = np.zeros(int(sr * 0.6), dtype=np.int16)
            silence = np.zeros_like(pcm)
            (left if role == "A" else right).append(pcm)
            (right if role == "A" else left).append(silence)
            left.append(gap)
            right.append(gap)
            dur = len(pcm) / sr
            meta.append({"role": role, "start": round(t, 2), "end": round(t + dur, 2), "text": text})
            t += dur + 0.6
        L = np.concatenate(left).astype(np.float32)
        R = np.concatenate(right).astype(np.float32)
        noise = rng.normal(0, 120, size=L.shape)  # ruído leve de linha
        stereo = np.stack([L + noise, R + noise], axis=1).clip(-32768, 32767).astype(np.int16)
        raw = os.path.join(args.out, f"{name}.raw.wav")
        with wave.open(raw, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(stereo.tobytes())
        band = "highpass=f=300,lowpass=f=3400"
        ffmpeg("-i", raw, "-af", band, "-ar", "8000", "-ac", "2", os.path.join(args.out, f"{name}.stereo8k.wav"))
        ffmpeg("-i", raw, "-af", band, "-ar", "8000", "-ac", "1", os.path.join(args.out, f"{name}.mono8k.wav"))
        ffmpeg("-i", os.path.join(args.out, f"{name}.mono8k.wav"), "-ar", "16000", "-ac", "1", "-b:a", "32k",
               os.path.join(args.out, f"{name}.mp3"))
        os.remove(raw)
        with open(os.path.join(args.out, f"{name}.turns.json"), "w", encoding="utf-8") as f:
            json.dump({"duration_s": round(t, 2), "turns": meta}, f, ensure_ascii=False, indent=1)
        print(name, f"{t:.1f}s", flush=True)
    # Cenários de falha
    src = os.path.join(args.out, "bom_atendimento.mp3")
    ffmpeg("-i", src, "-t", "40", "-c", "copy", os.path.join(args.out, "parcial_bom.mp3"))
    with open(os.path.join(args.out, "corrompido.mp3"), "wb") as f:
        f.write(b"ID3" + bytes(rng.integers(0, 255, 4096, dtype=np.uint8)))
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "8", "-b:a", "32k",
           os.path.join(args.out, "silencio.mp3"))
    print("ok", flush=True)


if __name__ == "__main__":
    main()
