from qa_pipeline import prompts
from qa_pipeline.analysis import Seg, run_qa, run_summary, summary_to_note, verify_evidence
from qa_pipeline.llm import LlmResponse, MockLlm
from qa_pipeline.pii import mask_segments
from qa_pipeline.rubric import DEFAULT_RUBRIC

from .fixtures import BAD, GOOD

RUB = {"criteria": DEFAULT_RUBRIC["criteria"], "mandatory_phrases": DEFAULT_RUBRIC["mandatory_phrases"]}
QA_T = prompts.load("qa")[1]
SUM_T = prompts.load("summary")[1]
FULL = {"ratio": 1, "partial": False, "start_s": 0}


def segs(rows):
    masked, _ = mask_segments([t for _, _, t in rows])
    return [Seg(idx=i, start=a, end=b, text=m) for i, ((a, b, _), m) in enumerate(zip(rows, masked))]


class FakeLlm:
    name, model = "fake", "fake-1"

    def __init__(self, data):
        self.data = data
        self.prompts = []

    def complete_json(self, system, user, *, task, context=None):
        self.prompts.append(user)
        return LlmResponse(self.data, self.name, self.model)


def test_pii_never_reaches_llm_prompt():
    llm = FakeLlm({"criteria": [], "alerts": []})
    run_qa(llm, segs(GOOD), RUB, FULL, QA_T)
    assert "123 456 789 09" not in llm.prompts[0] and "[CPF]" in llm.prompts[0]
    assert "roberto.silva@exemplo.com" not in llm.prompts[0] and "[EMAIL]" in llm.prompts[0]


def test_good_call_scores_high_with_verified_evidence():
    out = run_qa(MockLlm(), segs(GOOD), RUB, FULL, QA_T)
    assert out.status == "ai_completed" and out.score >= 85
    by = {c.key: c for c in out.criteria}
    assert by["saudacao"].status == "observed" and by["saudacao"].evidence_verified
    assert by["saudacao"].evidence_start_s == 0.0
    assert all(c.evidence_text is None or "123 456" not in c.evidence_text for c in out.criteria)


def test_bad_call_scores_low_and_raises_alerts():
    out = run_qa(MockLlm(), segs(BAD), RUB, FULL, QA_T)
    assert out.score is not None and out.score < 40
    types = {a.type for a in out.alerts}
    assert {"reclamacao", "pedido_supervisor", "cliente_sem_solucao", "recorrencia",
            "script_descumprido"} <= types
    assert all(a.evidence_text for a in out.alerts)


def test_hallucinated_evidence_is_not_scored():
    data = {"criteria": [{"key": c["key"], "status": "observed", "score": 100, "justification": "ok",
                          "evidence": {"segment_idx": 0, "quote": "frase que nunca foi dita na ligação"},
                          "confidence": 0.9} for c in DEFAULT_RUBRIC["criteria"]],
            "alerts": [{"type": "reclamacao", "severity": "alta", "description": "x",
                        "evidence": {"segment_idx": 1, "quote": "inventado aqui agora"}},
                       {"type": "tipo_inexistente", "evidence": {"segment_idx": 0, "quote": "B2B Reservas, bom dia"}}]}
    out = run_qa(FakeLlm(data), segs(GOOD), RUB, FULL, QA_T)
    assert out.score is None and out.status == "insufficient_evidence"
    assert all(c.status == "not_applicable" and "sem_evidencia_verificavel" in c.flags for c in out.criteria)
    assert out.alerts == [] and len(out.warnings) == 2


def test_forbidden_inference_removed_and_non_verifiable_not_failure():
    crit = []
    for c in DEFAULT_RUBRIC["criteria"]:
        crit.append({"key": c["key"], "status": "not_observed" if c["key"] == "registro" else "observed",
                     "score": 80, "justification": "O cliente parecia nervoso pela voz trêmula",
                     "evidence": {"segment_idx": 0, "quote": "B2B Reservas, bom dia! Meu nome é Carla"},
                     "confidence": 0.8})
    out = run_qa(FakeLlm({"criteria": crit, "alerts": []}), segs(GOOD), RUB, FULL, QA_T)
    by = {c.key: c for c in out.criteria}
    assert by["registro"].status == "not_applicable" and "nao_verificavel_no_audio" in by["registro"].flags
    assert "nervos" not in by["saudacao"].justification and "inferencia_pessoal_removida" in by["saudacao"].flags
    assert out.applicable_weight == 90 and out.score == 80.0


def test_partial_transcript_closing_not_applicable():
    out = run_qa(MockLlm(), segs(GOOD[:6]), RUB, {"ratio": 0.4, "partial": True, "start_s": 0}, QA_T)
    by = {c.key: c for c in out.criteria}
    assert by["encerramento"].status == "not_applicable"
    assert not any(a.type == "script_descumprido" for a in out.alerts)
    assert out.confidence <= 0.4


def test_summary_separates_fact_and_inference():
    out = run_summary(MockLlm(), segs(GOOD), SUM_T)
    c = out.content
    assert c["motivo"]["tipo"] == "fato" and c["motivo"]["evidencia"]
    assert c["classificacao_sugerida"]["tipo"] == "inferencia"
    assert c["_meta"]["rascunho"] is True
    bad = run_summary(FakeLlm({"motivo": {"texto": "Cliente quer cancelar", "tipo": "fato", "evidencia": [999]}}),
                      segs(GOOD), SUM_T)
    assert bad.content["motivo"]["tipo"] == "inferencia" and bad.warnings


def test_note_is_marked_draft_and_has_link():
    out = run_summary(MockLlm(), segs(GOOD), SUM_T)
    note = summary_to_note(out.content, "https://x/sd-console/qa/avaliacoes/1", 92.0, [])
    assert note.startswith("**[RASCUNHO IA") and "https://x/sd-console/qa/avaliacoes/1" in note
    assert "recomendação" in note


def test_verify_evidence_tolerates_wrong_index():
    ss = segs(GOOD)
    seg, _ = verify_evidence({"segment_idx": 7, "quote": "já corrigi o e-mail e reenviei o voucher"}, ss)
    assert seg.idx == 9
    assert verify_evidence({"segment_idx": 0, "quote": "ok"}, ss) == (None, None)


def test_one_word_evidence_only_when_whole_segment():
    """Achado no e2e real: o Whisper separou "Tchau." num segmento próprio e o encerramento ficou sem evidência."""
    ss = segs([(0.0, 1.0, "Tá bom."), (1.2, 1.8, "Tchau.")])
    seg, _ = verify_evidence({"segment_idx": 1, "quote": "Tchau."}, ss)
    assert seg is not None and seg.idx == 1
    assert verify_evidence({"segment_idx": 0, "quote": "bom"}, ss) == (None, None)
