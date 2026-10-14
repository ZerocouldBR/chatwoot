"""Textos das notas privadas, no mesmo conteúdo que a integração 55PBX gravava no Zendesk."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .normalize import NA, call_datetime, digits

DISCONNECTION_TEXT = {"operador": "Ligação terminada pelo operador", "cliente": "Ligação terminada pelo cliente"}


def _v(c: Dict[str, Any], k: str) -> str:
    v = c.get(k)
    return NA if v in (None, "") else str(v)


def subject(c: Dict[str, Any]) -> str:
    name = c.get("client_name") or ""
    return ("55PBX: Registro de ligação do número: " + name).strip()


def local_number(c: Dict[str, Any]) -> str:
    """Número como o Zendesk mostrava (sem DDI/DDD quando vier junto)."""
    n = digits(c.get("number"))
    if not n:
        return NA
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) in (10, 11):
        n = n[2:]
    return n


def ddd(c: Dict[str, Any]) -> str:
    if c.get("area_code"):
        return str(c["area_code"])
    n = digits(c.get("number"))
    if n.startswith("55") and len(n) in (12, 13):
        return n[2:4]
    if len(n) in (10, 11):
        return n[:2]
    return NA


def date_text(c: Dict[str, Any], tz: int = -3) -> str:
    d = call_datetime(c, tz)
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else NA


def registro(c: Dict[str, Any], tz: int = -3) -> str:
    lines = [
        "**Registro de ligação 55PBX:**",
        "",
        "CPF: " + _v(c, "cpf"),
        "Tipo da ligação: " + _v(c, "type"),
        "Número: " + local_number(c),
        "Ramal: " + _v(c, "branch"),
        "Central: " + _v(c, "central"),
        "DDD: " + ddd(c),
        "Data da ligação: " + date_text(c, tz),
        "Call ID: " + _v(c, "call_id"),
        "URA: " + (c.get("ura") or c.get("ivr") or NA),
        "Fila: " + _v(c, "queue"),
        "Order: " + _v(c, "order"),
        "Telefone de saída: " + (c.get("number_input") or "Telefone de entrada indisponível."),
    ]
    if c.get("agent_name"):
        lines.append("Agente: " + str(c["agent_name"]))
    if c.get("client_name"):
        lines.append("Nome do usuário: " + str(c["client_name"]))
    return "\n".join(lines)


def atualizacao(c: Dict[str, Any], audio_attached: bool = False) -> str:
    lines = [
        "**Atualização de ligação da 55PBX:**",
        "",
        "Tipo de ligação: " + _v(c, "type"),
        "Tempo falado (s): " + _v(c, "spoken"),
        "Tempo total de ligação (s): " + _v(c, "total_duration"),
    ]
    if c.get("waiting") is not None:
        lines.append("Tempo de espera (s): " + str(c["waiting"]))
    lines.append("URL do Áudio: " + (c.get("audio_url") or "sem gravação"))
    if audio_attached:
        lines.append("")
        lines.append("Gravação anexada abaixo (MP3).")
    return "\n".join(lines)


def acao_desconexao(c: Dict[str, Any]) -> Optional[str]:
    d = c.get("disconnection")
    if not d:
        return None
    return "**Registro de AÇÃO da 55PBX:**\n\n" + DISCONNECTION_TEXT.get(d, "Ligação terminada: " + str(d))


def acao_humor(c: Dict[str, Any]) -> Optional[str]:
    h = c.get("humor")
    if h is None:
        return None
    return "**Registro de AÇÃO da 55PBX:**\n\nHumor do Cliente: %s/5" % h


def gravacao(c: Dict[str, Any]) -> str:
    return "**Gravação da ligação 55PBX** (Call ID %s)\n\nOriginal: %s" % (_v(c, "call_id"), c.get("audio_url") or NA)


def call_attributes(c: Dict[str, Any]) -> Dict[str, Any]:
    """Atributos personalizados pbx_* da conversa (só os conhecidos)."""
    m = {
        "pbx_call_id": c.get("call_id"),
        "pbx_tipo": c.get("type"),
        "pbx_ramal": c.get("branch"),
        "pbx_fila": c.get("queue"),
        "pbx_numero": c.get("e164") or (digits(c.get("number")) or None),
        "pbx_duracao_total": c.get("total_duration"),
        "pbx_tempo_falado": c.get("spoken"),
        "pbx_tempo_espera": c.get("waiting"),
        "pbx_desconexao": c.get("disconnection"),
        "pbx_ura": c.get("ura") or c.get("ivr"),
        "pbx_humor": c.get("humor"),
        "pbx_agente": c.get("agent_name"),
    }
    return {k: v for k, v in m.items() if v not in (None, "")}
