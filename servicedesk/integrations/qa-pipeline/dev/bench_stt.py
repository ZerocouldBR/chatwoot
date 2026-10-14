"""Benchmark do STT local sobre os áudios sintéticos: WER aproximado e tempo por minuto de áudio.

  python dev/bench_stt.py --models base,small --threads 1 --out dev/run/bench.json

WER calculado com jiwer após normalização (minúsculas, sem pontuação). Também mostra o WER
"sem números" (descarta dígitos e números por extenso), porque a escrita de números
("4592" x "quatro cinco nove dois") infla o WER sem prejudicar o entendimento.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from dialogues import REFERENCES  # noqa: E402
from qa_pipeline.stt.faster_whisper_stt import FasterWhisperStt  # noqa: E402

NUM_WORDS = set("zero um uma dois duas tres quatro cinco seis sete oito nove dez onze doze treze quatorze "
                "catorze quinze dezesseis dezessete dezoito dezenove vinte trinta quarenta cinquenta "
                "sessenta setenta oitenta noventa cem cento mil e".split())


def norm(text: str, drop_numbers: bool = False) -> str:
    t = unicodedata.normalize("NFKC", text.lower())
    t = re.sub(r"[^\w@\s-]", " ", t).replace("-", " ")
    toks = t.split()
    if drop_numbers:
        def is_num(w):
            plain = unicodedata.normalize("NFD", w).encode("ascii", "ignore").decode()
            return any(c.isdigit() for c in w) or plain in NUM_WORDS
        toks = [w for w in toks if not is_num(w)]
    return " ".join(toks)


def main():
    import jiwer
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="dev/audio/out")
    ap.add_argument("--models", default="base,small")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--formats", default="mp3,stereo8k.wav")
    ap.add_argument("--out", default="dev/run/bench.json")
    args = ap.parse_args()
    results = []
    for model in args.models.split(","):
        load_t = time.perf_counter()
        stt = FasterWhisperStt(model=model, cpu_threads=args.threads, language="pt")
        stt._model()
        load_s = time.perf_counter() - load_t
        print(f"== modelo {model}: carregado em {load_s:.1f}s", flush=True)
        for name, ref in REFERENCES.items():
            for fmt in args.formats.split(","):
                path = os.path.join(args.dir, f"{name}.{fmt}")
                t0 = time.perf_counter()
                res = stt.transcribe(path)
                wall = time.perf_counter() - t0
                hyp = " ".join(s.text for s in res.segments)
                wer = jiwer.wer(norm(ref), norm(hyp))
                wer_nn = jiwer.wer(norm(ref, True), norm(hyp, True))
                confs = [s.confidence for s in res.segments if s.confidence is not None]
                attrib = None
                turns_path = os.path.join(args.dir, f"{name}.turns.json")
                if res.diarization == "channel" and os.path.exists(turns_path):
                    turns = json.load(open(turns_path, encoding="utf-8"))["turns"]
                    ok = wrong = none = 0.0
                    for sg in res.segments:
                        dur = max(0.01, sg.end - sg.start)
                        mid = (sg.start + sg.end) / 2
                        t = next((t for t in turns if t["start"] - 0.3 <= mid <= t["end"] + 0.3), None)
                        if sg.channel is None or t is None:
                            none += dur
                        elif (t["role"] == "A") == (sg.channel == 0):
                            ok += dur
                        else:
                            wrong += dur
                    tot = ok + wrong + none
                    attrib = {"correto": round(ok / tot, 3), "errado": round(wrong / tot, 3),
                              "sem_canal": round(none / tot, 3)}
                row = {
                    "model": model, "audio": f"{name}.{fmt}", "audio_s": res.audio_duration_s,
                    "wall_s": round(wall, 1), "rtf": round(wall / res.audio_duration_s, 3),
                    "s_per_audio_min": round(60 * wall / res.audio_duration_s, 1),
                    "wer": round(wer, 3), "wer_sem_numeros": round(wer_nn, 3),
                    "language": res.language, "lang_prob": round(res.language_probability or 0, 3),
                    "segments": len(res.segments), "diarization": res.diarization,
                    "avg_conf": round(sum(confs) / len(confs), 3) if confs else None,
                    "atribuicao_canal": attrib,
                    "hyp": hyp,
                }
                results.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "hyp"}, ensure_ascii=False), flush=True)
        results.append({"model": model, "load_s": round(load_s, 1)})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
