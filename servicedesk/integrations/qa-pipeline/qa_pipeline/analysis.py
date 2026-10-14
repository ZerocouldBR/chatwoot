"""Resumo estruturado, QA e alertas a partir da transcrição MASCARADA.

Independe do provedor: monta o prompt versionado, chama o LLM, e VALIDA a resposta:
- evidência precisa ser citação literal de um segmento (senão o critério vira "não aplicável" e
  é sinalizado; nunca vira nota inventada);
- timestamps vêm do segmento encontrado, não do texto do LLM;
- "não observado" exige trecho inspecionado transcrito; critério não verificável no áudio nunca é falha;
- inferências sobre emoção/saúde/características pessoais são removidas;
- todo texto devolvido passa de novo pelo mascaramento de PII.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import prompts
from .llm import LlmProvider
from .pii import mask_text
from .rubric import STATUSES, CriterionResult, compute_score

ALERT_TYPES = {
    "cliente_sem_solucao": "Cliente sem solução",
    "compromisso_retorno": "Compromisso de retorno",
    "reclamacao": "Reclamação",
    "pedido_supervisor": "Pedido de supervisor",
    "informacao_conflitante": "Informação conflitante",
    "quebra_procedimento": "Quebra de procedimento",
    "script_descumprido": "Script obrigatório descumprido",
    "recorrencia": "Recorrência",
    "oportunidade_base_conhecimento": "Oportunidade de base de conhecimento",
}
FORBIDDEN = re.compile(
    r"(voz (tr[eê]mula|nervosa|alterada|embargada)|parec(e|ia) (estar )?(nervos|ansios|irritad|brav|trist|doente|"
    r"idos|jovem|embriagad|choros)|sotaque|faixa et[aá]ria|\bidade\b|estado emocional|depress|ansiedade|"
    r"\bsa[uú]de (mental|do cliente)|orienta[cç][aã]o sexual|religi[aã]o|ra[cç]a\b)", re.IGNORECASE)
SUMMARY_SINGLE = ["motivo", "problema", "contexto", "solucao", "retorno", "proxima_acao"]
SUMMARY_LIST = ["verificacoes", "pendencias", "compromissos"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w\[\]]+", " ", s).split())


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec or 0))
    return f"{sec // 60:02d}:{sec % 60:02d}"


@dataclass
class Seg:
    idx: int
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    channel: Optional[int] = None

    def as_dict(self):
        return {"idx": self.idx, "start": self.start, "end": self.end, "text": self.text, "speaker": self.speaker}


def format_transcript(segs: List[Seg]) -> str:
    lines = []
    for s in segs:
        who = s.speaker or (f"canal {s.channel + 1}" if s.channel is not None else "-")
        lines.append(f"{s.idx} | {fmt_ts(s.start)}-{fmt_ts(s.end)} | {who} | {s.text}")
    return "\n".join(lines)


def verify_evidence(ev, segs: List[Seg]) -> Tuple[Optional[Seg], Optional[str]]:
    """Confere se a citação existe na transcrição. Devolve (segmento, citação) ou (None, None)."""
    if not isinstance(ev, dict):
        return None, None
    quote = str(ev.get("quote") or "").strip()
    nq = _norm(quote)
    by_idx = {s.idx: s for s in segs}
    if not nq:
        return None, None
    if len(nq.split()) < 2:
        # Citação de uma palavra só vale se for o segmento INTEIRO (ex.: "Tchau."), nunca um pedaço solto.
        try:
            s = by_idx.get(int(ev.get("segment_idx")))
        except (TypeError, ValueError):
            s = None
        return (s, quote) if s is not None and _norm(s.text) == nq else (None, None)
    cand = []
    try:
        i = int(ev.get("segment_idx"))
        cand = [by_idx[j] for j in (i, i - 1, i + 1) if j in by_idx]
    except (TypeError, ValueError):
        pass
    for s in cand + segs:
        ns = _norm(s.text)
        if nq in ns:
            return s, quote
    qtok = nq.split()
    for s in cand + segs:
        stok = set(_norm(s.text).split())
        if len(qtok) >= 3 and sum(t in stok for t in qtok) / len(qtok) >= 0.85:
            return s, quote
    return None, None


def _clean_text(text, flags: List[str]) -> str:
    text = str(text or "").strip()
    if FORBIDDEN.search(text):
        flags.append("inferencia_pessoal_removida")
        text = FORBIDDEN.sub("[removido: inferência não permitida]", text)
    return mask_text(text)


@dataclass
class AlertResult:
    type: str
    label: str
    severity: str
    description: str
    evidence_text: str
    start_s: float
    segment_idx: int


@dataclass
class QaOutcome:
    criteria: List[CriterionResult]
    score: Optional[float]
    applicable_weight: int
    redistribution: dict
    confidence: float
    status: str
    alerts: List[AlertResult]
    warnings: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""


def run_qa(llm: LlmProvider, segs: List[Seg], rubric: dict, coverage: dict, prompt_template: str,
           min_applicable_weight: int = 50) -> QaOutcome:
    criteria_def = rubric["criteria"]
    rubric_txt = "\n".join(f"- {c['key']} | {c['label']} | peso {c['weight']} | {c.get('description', '')}"
                           for c in criteria_def)
    mandatory = rubric.get("mandatory_phrases") or []
    mand_txt = "\n".join(f"- {m['label']}" for m in mandatory) or "(nenhuma)"
    cov_txt = (f"{coverage.get('ratio', 1):.0%} do áudio; início {fmt_ts(coverage.get('start_s', 0))}; "
               f"{'INCOMPLETA (final ausente)' if coverage.get('partial') else 'completa'}")
    msgs = prompts.render(prompt_template, rubric=rubric_txt, mandatory=mand_txt, coverage=cov_txt,
                          transcript=format_transcript(segs))
    resp = llm.complete_json(msgs["system"], msgs["user"], task="qa",
                             context={"segments": [s.as_dict() for s in segs], "rubric": criteria_def,
                                      "mandatory": mandatory, "coverage": coverage})
    data = resp.data if isinstance(resp.data, dict) else {}
    warnings: List[str] = []
    got = {}
    for c in data.get("criteria") or []:
        if isinstance(c, dict) and c.get("key"):
            got[str(c["key"])] = c
    covered_end = max((s.end for s in segs), default=0)
    results: List[CriterionResult] = []
    for cd in criteria_def:
        flags: List[str] = []
        raw = got.get(cd["key"])
        r = CriterionResult(key=cd["key"], label=cd["label"], weight=int(cd["weight"]), status="not_applicable",
                            score=None, flags=flags)
        if raw is None:
            flags.append("ausente_na_resposta")
            r.justification = "O avaliador não retornou este critério."
            results.append(r)
            continue
        status = raw.get("status")
        if status not in STATUSES:
            flags.append("status_invalido")
            status = "not_applicable"
        r.justification = _clean_text(raw.get("justification"), flags)
        r.suggestion = _clean_text(raw.get("suggestion"), flags) or None
        try:
            r.confidence = max(0.0, min(1.0, float(raw.get("confidence"))))
        except (TypeError, ValueError):
            r.confidence = None
        seg, quote = verify_evidence(raw.get("evidence"), segs)
        if status in ("observed", "not_observed") and seg is None:
            flags.append("sem_evidencia_verificavel")
            r.justification = ("Sem evidência literal verificável na transcrição; não pontuado. "
                               + (r.justification or "")).strip()
            r.confidence = 0.0
            status = "not_applicable"
        if status == "not_observed" and not cd.get("audio_verifiable", True):
            flags.append("nao_verificavel_no_audio")
            status = "not_applicable"
        if status == "not_observed" and cd.get("window") == "fim" and coverage.get("partial"):
            flags.append("trecho_nao_transcrito")
            status = "not_applicable"
        if status == "observed":
            try:
                r.score = max(0.0, min(100.0, float(raw.get("score"))))
            except (TypeError, ValueError):
                flags.append("nota_invalida")
                status = "not_applicable"
        r.status = status
        if seg is not None and status != "not_applicable":
            r.evidence_text = mask_text(quote)
            r.evidence_start_s, r.evidence_end_s = seg.start, seg.end
            r.evidence_segment_idx = seg.idx
            r.evidence_verified = True
        results.append(r)
    extra = set(got) - {c["key"] for c in criteria_def}
    if extra:
        warnings.append(f"critérios desconhecidos ignorados: {sorted(extra)}")
    sc = compute_score(results, min_applicable_weight)
    appl = [r for r in results if r.status != "not_applicable"]
    conf = (sum((r.confidence or 0) * r.effective_weight for r in appl) / 100.0) if appl else 0.0
    conf *= min(1.0, coverage.get("ratio", 1.0))
    alerts: List[AlertResult] = []
    seen = set()
    for a in data.get("alerts") or []:
        if not isinstance(a, dict):
            continue
        typ = a.get("type")
        if typ not in ALERT_TYPES:
            warnings.append(f"alerta de tipo desconhecido descartado: {typ}")
            continue
        seg, quote = verify_evidence(a.get("evidence"), segs)
        if seg is None:
            warnings.append(f"alerta {typ} descartado: sem evidência literal")
            continue
        if (typ, seg.idx) in seen:
            continue
        seen.add((typ, seg.idx))
        flags = []
        sev = a.get("severity") if a.get("severity") in ("baixa", "media", "alta") else "media"
        alerts.append(AlertResult(type=typ, label=ALERT_TYPES[typ], severity=sev,
                                  description=_clean_text(a.get("description"), flags) or ALERT_TYPES[typ],
                                  evidence_text=mask_text(quote), start_s=seg.start, segment_idx=seg.idx))
    status = "ai_completed" if sc["score"] is not None else "insufficient_evidence"
    if not segs:
        warnings.append("transcrição vazia")
    _ = covered_end
    return QaOutcome(criteria=results, score=sc["score"], applicable_weight=sc["applicable_weight"],
                     redistribution=sc["redistribution"], confidence=round(conf, 3), status=status,
                     alerts=alerts, warnings=warnings, provider=resp.provider, model=resp.model)


@dataclass
class SummaryOutcome:
    content: dict
    warnings: List[str]
    provider: str
    model: str


def run_summary(llm: LlmProvider, segs: List[Seg], prompt_template: str) -> SummaryOutcome:
    msgs = prompts.render(prompt_template, transcript=format_transcript(segs))
    resp = llm.complete_json(msgs["system"], msgs["user"], task="summary",
                             context={"segments": [s.as_dict() for s in segs]})
    data = resp.data if isinstance(resp.data, dict) else {}
    valid_idx = {s.idx for s in segs}
    warnings: List[str] = []

    def clean_item(it, where):
        if not isinstance(it, dict) or not str(it.get("texto") or "").strip():
            return None
        flags: List[str] = []
        ev = [int(i) for i in (it.get("evidencia") or []) if isinstance(i, (int, float, str)) and str(i).isdigit()]
        ev = [i for i in ev if i in valid_idx]
        tipo = it.get("tipo") if it.get("tipo") in ("fato", "inferencia") else "inferencia"
        if tipo == "fato" and not ev:
            tipo = "inferencia"
            flags.append("fato_sem_evidencia_rebaixado")
            warnings.append(f"{where}: 'fato' sem segmento de evidência foi marcado como inferência")
        out = {"texto": _clean_text(it.get("texto"), flags), "tipo": tipo, "evidencia": ev}
        if flags:
            out["flags"] = flags
        return out

    content = {}
    for k in SUMMARY_SINGLE:
        content[k] = clean_item(data.get(k), k)
    for k in SUMMARY_LIST:
        content[k] = [x for x in (clean_item(i, k) for i in (data.get(k) or [])) if x]
    cls = data.get("classificacao_sugerida") if isinstance(data.get("classificacao_sugerida"), dict) else {}
    content["classificacao_sugerida"] = {
        "categoria": mask_text(str(cls.get("categoria") or "")) or None,
        "subcategoria": mask_text(str(cls.get("subcategoria") or "")) or None,
        "tipo": "inferencia",
        "confianca": cls.get("confianca") if isinstance(cls.get("confianca"), (int, float)) else None,
    }
    content["_meta"] = {"rascunho": True, "aviso": "Rascunho gerado por IA: revise antes de tornar definitivo."}
    return SummaryOutcome(content=content, warnings=warnings, provider=resp.provider, model=resp.model)


def summary_to_note(content: dict, link: str, score: Optional[float], alerts: List[AlertResult]) -> str:
    """Texto da nota PRIVADA no Chatwoot (markdown simples)."""
    def line(label, it):
        if not it:
            return None
        tag = "fato" if it.get("tipo") == "fato" else "inferência"
        return f"- **{label}** ({tag}): {it['texto']}"

    out = ["**[RASCUNHO IA: revisar antes de usar]** Resumo automático da ligação", ""]
    for label, k in (("Motivo", "motivo"), ("Problema", "problema"), ("Solução", "solucao"),
                     ("Retorno", "retorno"), ("Próxima ação", "proxima_acao")):
        ln = line(label, content.get(k))
        if ln:
            out.append(ln)
    for label, k in (("Verificação", "verificacoes"), ("Pendência", "pendencias"), ("Compromisso", "compromissos")):
        for it in content.get(k) or []:
            out.append(line(label, it))
    cls = content.get("classificacao_sugerida") or {}
    if cls.get("categoria"):
        out.append(f"- **Classificação sugerida** (inferência): {cls['categoria']} / {cls.get('subcategoria') or '-'}")
    if score is not None:
        out.append(f"- **QA sugerido pela IA**: {float(score):.0f}/100 (recomendação, sujeita a revisão humana)")
    if alerts:
        out.append("- **Alertas**: " + "; ".join(sorted({a.label for a in alerts})))
    out += ["", f"Revisar no console: {link}",
            "_Gerado automaticamente a partir da transcrição com dados pessoais mascarados. Não é decisão._"]
    return "\n".join(x for x in out if x is not None)


def to_jsonable(obj) -> dict:
    return json.loads(json.dumps(obj, default=lambda o: o.__dict__))
