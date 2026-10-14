"""Rubrica de QA (seção 8.3 do prompt mestre) e regra de pontuação transparente.

Status por critério:
- observed (observado): o comportamento aparece na transcrição; nota 0..100 com evidência textual.
- not_observed (não observado): o critério se aplica, o trecho em que deveria ocorrer foi
  transcrito e o comportamento NÃO ocorreu. Entra com nota 0. Exige indicar o trecho inspecionado.
- not_applicable (não aplicável): não se aplica à ligação OU não é verificável no áudio
  (ex.: registro no sistema, trecho não transcrito, evidência inválida). NÃO conta como falha.

Regra de redistribuição (exibida ao usuário em cada avaliação):
  A = critérios observados ou não observados (aplicáveis)
  nota = Σ_{i∈A} peso_i × nota_i / Σ_{i∈A} peso_i
  peso efetivo_i = peso_i × 100 / Σ_{i∈A} peso_i   (o peso dos não aplicáveis é redistribuído
  proporcionalmente entre os aplicáveis)
  Se Σ_{i∈A} peso_i < QA_MIN_APPLICABLE_WEIGHT (50): sem nota ("evidência insuficiente") e tarefa
  de revisão humana.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

DEFAULT_RUBRIC = {
    "code": "padrao",
    "version": 1,
    "name": "Rubrica padrão de atendimento telefônico",
    "criteria": [
        {"key": "saudacao", "label": "Saudação e identificação", "weight": 10, "window": "inicio",
         "description": "Cumprimenta, identifica a empresa e a si mesmo e pergunta com quem fala.",
         "audio_verifiable": True},
        {"key": "procedimentos", "label": "Aderência aos procedimentos", "weight": 10, "window": None,
         "description": "Confirma a identidade/cadastro antes de tratar dados, segue o fluxo e informa o protocolo.",
         "audio_verifiable": True},
        {"key": "empatia", "label": "Escuta ativa e empatia", "weight": 15, "window": None,
         "description": "Reconhece a necessidade do cliente, não interrompe, demonstra interesse em resolver.",
         "audio_verifiable": True},
        {"key": "diagnostico", "label": "Diagnóstico e clareza", "weight": 20, "window": None,
         "description": "Faz perguntas pertinentes, verifica o problema e explica com clareza.",
         "audio_verifiable": True},
        {"key": "resolucao", "label": "Resolução e próximos passos", "weight": 25, "window": None,
         "description": "Resolve ou encaminha com responsável e prazo; deixa claros os próximos passos.",
         "audio_verifiable": True},
        {"key": "encerramento", "label": "Encerramento", "weight": 10, "window": "fim",
         "description": "Verifica se há algo mais, agradece e encerra cordialmente.",
         "audio_verifiable": True},
        {"key": "registro", "label": "Registro e conformidade", "weight": 10, "window": None,
         "description": "Registro no ticket e conformidade (LGPD, não solicitar dados sensíveis). O registro no "
                        "sistema não é audível: só pontuar com menção explícita ou violação audível.",
         "audio_verifiable": False},
    ],
    "mandatory_phrases": [
        {"key": "protocolo", "label": "Informar o número de protocolo", "patterns": ["protocolo"]},
    ],
    "redistribution_rule": (
        "nota = soma(peso x nota) / soma(peso) apenas dos critérios observados ou não observados; "
        "o peso dos critérios não aplicáveis é redistribuído proporcionalmente entre os aplicáveis "
        "(peso efetivo = peso x 100 / soma dos pesos aplicáveis). Não observado vale 0. Não aplicável "
        "(inclui não verificável no áudio) não conta como falha. Com menos de 50 pontos de peso "
        "aplicável a avaliação fica sem nota e vai para revisão humana."
    ),
}

STATUSES = ("observed", "not_observed", "not_applicable")
STATUS_LABEL = {"observed": "observado", "not_observed": "não observado", "not_applicable": "não aplicável"}


@dataclass
class CriterionResult:
    key: str
    label: str
    weight: int
    status: str
    score: Optional[float]
    justification: str = ""
    evidence_text: Optional[str] = None
    evidence_start_s: Optional[float] = None
    evidence_end_s: Optional[float] = None
    evidence_segment_idx: Optional[int] = None
    evidence_verified: bool = False
    confidence: Optional[float] = None
    suggestion: Optional[str] = None
    flags: Optional[List[str]] = None
    effective_weight: float = 0.0


def validate_rubric(criteria: List[dict]) -> None:
    keys = [c["key"] for c in criteria]
    if len(keys) != len(set(keys)):
        raise ValueError("chaves de critério repetidas")
    if any(int(c["weight"]) <= 0 for c in criteria):
        raise ValueError("peso deve ser positivo")
    if sum(int(c["weight"]) for c in criteria) != 100:
        raise ValueError("a soma dos pesos deve ser 100")


def compute_score(results: List[CriterionResult], min_applicable_weight: int = 50) -> Dict:
    applicable = [r for r in results if r.status in ("observed", "not_observed")]
    na = [r for r in results if r.status == "not_applicable"]
    total_w = sum(r.weight for r in applicable)
    for r in results:
        r.effective_weight = round(r.weight * 100.0 / total_w, 3) if (r in applicable and total_w) else 0.0
        if r.status == "not_observed":
            r.score = 0.0
        if r.status == "not_applicable":
            r.score = None
    explanation = {
        "regra": DEFAULT_RUBRIC["redistribution_rule"],
        "peso_aplicavel": total_w,
        "nao_aplicaveis": [{"criterio": r.key, "peso": r.weight} for r in na],
        "fator": round(100.0 / total_w, 4) if total_w else None,
    }
    if total_w < min_applicable_weight:
        explanation["resultado"] = (f"sem nota: só {total_w} pontos de peso verificáveis "
                                    f"(mínimo {min_applicable_weight})")
        return {"score": None, "applicable_weight": total_w, "redistribution": explanation}
    score = sum(r.weight * float(r.score or 0) for r in applicable) / total_w
    explanation["resultado"] = (f"{len(na)} critério(s) não aplicável(is) somando {100 - total_w} pontos de peso "
                                f"redistribuídos entre {len(applicable)} aplicável(is) (fator {100.0 / total_w:.4f})"
                                if na else "todos os critérios aplicáveis; sem redistribuição")
    return {"score": round(score, 2), "applicable_weight": total_w, "redistribution": explanation}
