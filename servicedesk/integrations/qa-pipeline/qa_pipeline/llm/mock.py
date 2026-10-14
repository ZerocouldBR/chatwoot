"""LLM MOCK (padrão): regras determinísticas por palavras-chave em pt-BR.

NÃO é IA. Serve para exercitar o pipeline inteiro (prompt -> JSON -> validação -> nota -> alertas ->
nota no Chatwoot) sem custo e sem enviar dados a terceiros, e para os testes automatizados. Devolve
exatamente o mesmo formato JSON pedido aos LLMs reais, com citações literais dos segmentos.
A qualidade do julgamento é limitada: um bom atendimento é reconhecido por expressões típicas
("meu nome é", "entendo", "protocolo"...), não por compreensão.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

from .providers import LlmProvider, LlmResponse


def _n(s: str) -> str:
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _find(segs: List[dict], patterns: List[str], window: Optional[tuple] = None) -> Optional[dict]:
    for s in segs:
        if window and not (window[0] <= s["start"] <= window[1]):
            continue
        t = _n(s["text"])
        if any(re.search(p, t) for p in patterns):
            return s
    return None


def _quote(seg: dict, max_words: int = 25) -> str:
    words = seg["text"].split()
    return " ".join(words[:max_words])


def _ev(seg):
    return {"segment_idx": seg["idx"], "quote": _quote(seg)} if seg else None


GREETING = [r"\bbom dia\b", r"\bboa tarde\b", r"\bboa noite\b", r"\bola\b"]
IDENT = [r"meu nome e", r"aqui e o", r"aqui e a", r"\bfala o\b", r"\bfala a\b", r"b2b reservas"]
VERIFY = [r"confirmar a sua identidade", r"\bcpf\b", r"codigo da reserva", r"numero do pedido", r"por seguranca",
          r"confirmar (o|um|seu)"]
EMPATHY = [r"\bentendo\b", r"\bcompreendo\b", r"sinto muito", r"\blamento\b", r"peco desculpas",
           r"fique tranquil", r"vamos resolver"]
RUDE = [r"nao e comigo", r"nao tem o que fazer", r"ligar outra hora", r"problema (e )?seu", r"ja falei"]
DIAG = [r"estou verificando", r"vou verificar", r"identifiquei", r"verifiquei", r"o problema (e|foi)",
        r"pode me (informar|confirmar)", r"qual (e|o|a)"]
RESOLVE = [r"ja corrigi", r"reenviei", r"foi resolvid", r"esta resolvid", r"enviei", r"vou retornar",
           r"retorno (em|ate)", r"prazo", r"ate amanha"]
NO_SOLUTION = [r"nao tem o que fazer", r"nao resolvem nada", r"ninguem (me )?(explicou|resolve)",
               r"continua sem", r"vou ver se alguem"]
CLOSING = [r"mais alguma coisa", r"algo mais", r"posso ajudar em mais", r"agradeco", r"obrigad[oa] pela",
           r"tenha um bom", r"boa tarde!?$", r"bom dia!?$"]
REGISTER = [r"registrei", r"vou registrar no", r"anotei", r"registrado no ticket"]
LGPD_GOOD = [r"nao precisa me falar", r"link seguro", r"nao vou registrar esse numero"]
ALERTS = {
    "cliente_sem_solucao": (NO_SOLUTION, "alta"),
    "compromisso_retorno": ([r"vou retornar", r"te ligo", r"alguem te liga", r"retorno (em|ate)", r"entro em contato"],
                            "media"),
    "reclamacao": ([r"reclamacao", r"\babsurdo\b", r"\bpessimo\b", r"procon", r"reclame aqui"], "alta"),
    "pedido_supervisor": ([r"supervisor", r"gerente", r"falar com (o )?responsavel"], "alta"),
    "recorrencia": ([r"terceira vez", r"segunda vez", r"de novo", r"ja liguei", r"novamente"], "media"),
    "oportunidade_base_conhecimento": ([r"como (eu )?faco", r"nao sei (como|informar)", r"nao encontrei"], "baixa"),
    "informacao_conflitante": ([r"da ultima vez me disseram", r"me falaram outra coisa"], "media"),
}


class MockLlm(LlmProvider):
    name = "mock"
    model = "regras-ptbr-v1"

    def complete_json(self, system, user, *, task, context=None) -> LlmResponse:
        ctx = context or {}
        segs = ctx.get("segments") or []
        if task == "qa":
            return LlmResponse(self._qa(segs, ctx), self.name, self.model)
        return LlmResponse(self._summary(segs), self.name, self.model)

    # ---------------- QA ----------------
    def _qa(self, segs, ctx):
        cov = ctx.get("coverage") or {}
        start_cov = cov.get("start_s", 0) <= 5
        end_cov = not cov.get("partial", False)
        crit = []

        def add(key, status, score=None, just="", seg=None, conf=0.6, sug=None):
            crit.append({"key": key, "status": status, "score": score, "justification": just,
                         "evidence": _ev(seg), "confidence": conf, "suggestion": sug})

        first = segs[0] if segs else None
        g = _find(segs, GREETING, (0, 25))
        i = _find(segs, IDENT, (0, 25))
        if g and i:
            add("saudacao", "observed", 100, "Cumprimentou e se identificou na abertura.", i)
        elif g or i:
            add("saudacao", "observed", 50, "Abertura incompleta: cumprimento ou identificação ausente.", g or i,
                sug="Use a abertura padrão: empresa, nome e pergunta pelo interlocutor.")
        elif start_cov and first:
            add("saudacao", "not_observed", None, "Abertura transcrita sem cumprimento nem identificação.", first,
                sug="Use a abertura padrão: empresa, nome e pergunta pelo interlocutor.")
        else:
            add("saudacao", "not_applicable", None, "Início da ligação não transcrito.")

        v = _find(segs, VERIFY)
        prot = _find(segs, [r"protocolo"])
        if v and prot:
            add("procedimentos", "observed", 100, "Confirmou dados/identidade e informou protocolo.", v)
        elif v or prot:
            add("procedimentos", "observed", 60, "Seguiu parte do procedimento.", v or prot,
                sug="Confirme a identidade e informe o protocolo em toda ligação.")
        elif segs:
            add("procedimentos", "not_observed", None, "Não houve verificação de cadastro nem protocolo.", segs[0],
                sug="Confirme a identidade do cliente e informe o protocolo.")

        e = _find(segs, EMPATHY)
        r = _find(segs, RUDE)
        if r:
            add("empatia", "observed", 10, "Resposta que transfere o problema ao cliente sem acolhimento.", r,
                sug="Reconheça a necessidade do cliente e assuma a condução do caso.")
        elif e:
            add("empatia", "observed", 90, "Reconheceu a necessidade do cliente.", e)
        else:
            add("empatia", "not_applicable", None, "Sem trecho que permita avaliar escuta ativa com evidência.",
                conf=0.3)

        d = _find(segs, DIAG)
        if d and not r:
            add("diagnostico", "observed", 85, "Investigou e explicou o problema.", d)
        elif d:
            add("diagnostico", "observed", 30, "Pergunta pontual, sem investigar o problema.", d,
                sug="Investigue a causa antes de encaminhar.")
        elif segs:
            add("diagnostico", "not_observed", None, "Não houve investigação do problema.", segs[0],
                sug="Faça perguntas para entender o problema.")

        s = _find(segs, RESOLVE)
        ns = _find(segs, NO_SOLUTION)
        if ns:
            add("resolucao", "observed", 10, "Cliente ficou sem solução nem prazo definido.", ns,
                sug="Defina responsável e prazo, ou acione o time correto durante a ligação.")
        elif s:
            add("resolucao", "observed", 90, "Resolveu ou definiu próximo passo.", s)
        elif segs:
            add("resolucao", "not_observed", None, "Sem resolução nem próximos passos.", segs[-1])

        tail_from = (segs[-1]["end"] - 30) if segs else 0
        c = _find(segs, CLOSING, (tail_from, 1e9))
        if not end_cov:
            add("encerramento", "not_applicable", None, "Trecho final não transcrito (áudio incompleto).")
        elif c and _find(segs, [r"mais alguma coisa", r"algo mais", r"posso ajudar em mais"], (tail_from, 1e9)):
            add("encerramento", "observed", 100, "Verificou pendências e encerrou cordialmente.", c)
        elif c:
            add("encerramento", "observed", 70, "Encerrou cordialmente sem verificar outras demandas.", c,
                sug="Pergunte se há algo mais antes de encerrar.")
        elif segs:
            add("encerramento", "observed", 20, "Encerramento abrupto.", segs[-1],
                sug="Agradeça e confirme os próximos passos antes de encerrar.")

        reg = _find(segs, REGISTER)
        lg = _find(segs, LGPD_GOOD)
        if reg or lg:
            add("registro", "observed", 100 if reg and lg else 80,
                "Mencionou o registro e/ou protegeu dado sensível.", reg or lg)
        else:
            add("registro", "not_applicable", None, "Registro no sistema não é verificável no áudio.", conf=0.5)

        alerts = []
        for typ, (pats, sev) in ALERTS.items():
            seg = _find(segs, pats)
            if seg:
                alerts.append({"type": typ, "severity": sev, "description": f"Indício de {typ.replace('_', ' ')}.",
                               "evidence": _ev(seg)})
        for m in ctx.get("mandatory") or []:
            if not _find(segs, [_n(p) for p in m.get("patterns", [])]) and end_cov and segs:
                alerts.append({"type": "script_descumprido", "severity": "media",
                               "description": f"Frase obrigatória ausente: {m.get('label')}.",
                               "evidence": _ev(segs[-1])})
        return {"criteria": crit, "alerts": alerts}

    # ---------------- Resumo ----------------
    def _summary(self, segs):
        def item(seg, tipo="fato", texto=None):
            if not seg:
                return None
            return {"texto": texto or seg["text"], "tipo": tipo, "evidencia": [seg["idx"]]}

        motivo = _find(segs, [r"estou ligando", r"eu fiz uma reserva", r"quero ", r"gostaria", r"preciso",
                              r"nao chegou", r"foi cancelada"])
        verif = [s for s in segs if any(re.search(p, _n(s["text"])) for p in DIAG + VERIFY)][:3]
        sol = _find(segs, [r"ja corrigi", r"reenviei", r"enviei", r"resolvid"])
        comp = [s for s in segs if any(re.search(p, _n(s["text"])) for p in ALERTS["compromisso_retorno"][0])]
        pend = _find(segs, NO_SOLUTION)
        text_all = _n(" ".join(s["text"] for s in segs))
        if "voucher" in text_all:
            cat, sub = "Reservas", "Voucher"
        elif "cancelad" in text_all:
            cat, sub = "Reservas", "Cancelamento"
        elif "cartao" in text_all or "cobranca" in text_all or "financeiro" in text_all:
            cat, sub = "Financeiro", "Pagamento"
        else:
            cat, sub = "Suporte", "Dúvida geral"
        return {
            "motivo": item(motivo),
            "problema": item(motivo, "inferencia", "Problema descrito pelo cliente no trecho citado.") if motivo else None,
            "contexto": None,
            "verificacoes": [item(s) for s in verif],
            "solucao": item(sol),
            "pendencias": [item(pend)] if pend else [],
            "compromissos": [item(s) for s in comp],
            "retorno": item(comp[0]) if comp else None,
            "proxima_acao": ({"texto": "Cumprir o retorno combinado.", "tipo": "inferencia", "evidencia": [comp[0]["idx"]]}
                             if comp else ({"texto": "Tratar a pendência e contatar o cliente.", "tipo": "inferencia",
                                            "evidencia": [pend["idx"]]} if pend else None)),
            "classificacao_sugerida": {"categoria": cat, "subcategoria": sub, "tipo": "inferencia", "confianca": 0.5},
        }
