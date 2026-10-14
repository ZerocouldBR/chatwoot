"""Mede o tamanho dos prompts reais (QA + resumo) das avaliações informadas, para estimar custo de LLM.

  python dev/prompt_size.py 6 7 8
Tokens estimados por caracteres (pt-BR ~3,5 caracteres por token em tokenizadores BPE recentes); para um
número exato, use o contador de tokens do provedor escolhido.
"""
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qa_pipeline import db, prompts  # noqa: E402
from qa_pipeline.analysis import Seg, format_transcript  # noqa: E402
from qa_pipeline.models import QaEvaluation, Transcription, TranscriptionSegment  # noqa: E402
from qa_pipeline.rubric import DEFAULT_RUBRIC  # noqa: E402

CPT = 3.5


def main(ids):
    db.init_engine(os.environ["DATABASE_URL"])
    qa_t, su_t = prompts.load("qa")[1], prompts.load("summary")[1]
    rub = "\n".join(f"- {c['key']} | {c['label']} | peso {c['weight']} | {c['description']}" for c in DEFAULT_RUBRIC["criteria"])
    with db.session() as s:
        for eid in ids:
            ev = s.get(QaEvaluation, int(eid))
            tr = s.get(Transcription, ev.transcription_id)
            rows = s.execute(select(TranscriptionSegment).where(TranscriptionSegment.transcription_id == tr.id)
                             .order_by(TranscriptionSegment.idx)).scalars().all()
            segs = [Seg(r.idx, r.start_s, r.end_s, r.text_masked, r.speaker, r.channel) for r in rows]
            tx = format_transcript(segs)
            q = prompts.render(qa_t, rubric=rub, mandatory="- Informar o número de protocolo", coverage="100%", transcript=tx)
            m = prompts.render(su_t, transcript=tx)
            qc = len(q["system"]) + len(q["user"])
            mc = len(m["system"]) + len(m["user"])
            print(f"avaliação {eid}: áudio {tr.audio_duration_s:.0f}s | transcrição {len(tx)} car. | prompt QA {qc} car. "
                  f"(~{qc / CPT:.0f} tok) | prompt resumo {mc} car. (~{mc / CPT:.0f} tok) | fixo (sem transcrição) "
                  f"~{(qc + mc - 2 * len(tx)) / CPT:.0f} tok | transcrição ~{len(tx) / tr.audio_duration_s * 60 / CPT:.0f} tok/min")


if __name__ == "__main__":
    main(sys.argv[1:])
