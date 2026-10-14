"""Normalização dos registros 55PBX para o sd-ops.

Reaproveita pbx_bridge.normalize (leitura tolerante do Report02 e do webhook) e acrescenta o que o manual
"Integração REST" (v2.0) e o readme "Realtime > Objeto de resposta" documentam e a ponte não lia:
central_id, branch_mask, branch_email, call_status, call_transfer_id, call_terminal, call_audio_file,
call_total_time, call_rating*, call_cost; e call_id_origin do Report02.

Inconsistência do manual: a tabela diz call_time = "tempo efetivo" e call_duration = "duração total", mas os dois
exemplos oficiais trazem call_time > call_duration (no PDF, 11 = 3 falados + 8 de espera). PBX_RT_TIME_FIELDS
escolhe a leitura (padrão "examples": call_time = total, call_duration = falado; "descriptions" = a tabela). Se o
falado ficar maior que o total, os valores são trocados e a anomalia é registrada. call_total_time vence como total.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from pbx_bridge.normalize import (call_datetime, clean, digits, has_end_data, norm_key, normalize, slug,
                                  to_e164, to_seconds)

# chaves do webhook em tempo real (forma norm_key) que a normalização legada não conhece ou lê errado
RT_KEYS = {
    "centralid": "central_id",
    "branchmask": "branch",
    "branchemail": "branch_email",
    "branchlinenumber": "branch_line_number",
    "callstatus": "status_raw",
    "calltransferid": "transfer_id",
    "callterminal": "terminal",
    "callaudiofile": "audio_file",
    "calltotaltime": "rt_total_time",
    "calltime": "rt_call_time",
    "callduration": "rt_call_duration",
    "callidorigin": "origin_call_id",
    "callticketid": "provider_ticket_id",
    "callcost": "cost",
    "wucallcost": "cost",
    "calltax": "tax",
    "calltaxtype": "tax_type",
    "callbalance": None,           # saldo da conta: descartado (não é dado da ligação)
    "callrating": "rating",
    "callratingweight": "rating_weight",
    "callratingtype": "rating_type",
    "callratingyes": "rating_yes",
    "callratingno": "rating_no",
    "callratingformid": "rating_form_id",
    "callratingname": "rating_name",
    "totalcallabandonedura": "report_abandoned_ura",
    "wtagentscalled": "agents_called",
    "wxqueueoverflow": "queue_overflow",
    "wyqueuemaskagent": None,
    "wybranchmaskagent": "branch_mask_agent",
    "wlattendeddate": "attended_date",
    "wlattendedhour": "attended_hour",
}

# campos do tempo real que a normalização legada lê por outro nome
RENAME = {"callqueue": "queue_name", "callura": "way_ura", "callcountrycode": "wg_country_code"}

ISODATE = re.compile(r"""ISODate\(\s*["']([^"']*)["']\s*\)""")


def fix_isodate(text: str) -> str:
    """O exemplo do manual usa o literal Mongo ISODate("…") no JSON: troca por string."""
    return ISODATE.sub(lambda m: '"%s"' % m.group(1), text)


def canonicalize(rec: Dict[str, Any], time_fields: str = "examples") -> Tuple[Dict[str, Any], List[str]]:
    """Registro bruto (webhook ou Report02) -> (dados normalizados, anomalias)."""
    anomalies: List[str] = []
    legacy_in: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for k, v in rec.items():
        nk = norm_key(k)
        if nk in RENAME:
            legacy_in[RENAME[nk]] = v
            continue
        if nk in RT_KEYS:
            target = RT_KEYS[nk]
            if target and clean(v) is not None:
                extra[target] = v
            continue
        legacy_in[k] = v
    out = normalize(legacy_in)

    # ramal: branch_mask (tempo real) vence; Report02 usa branch_number_agent (lido pela normalização legada)
    if extra.get("branch") is not None and "branch" not in out:
        out["branch"] = clean(extra["branch"])
    extra.pop("branch", None)

    # tempos do webhook em tempo real
    ct, cd, tt = (to_seconds(extra.pop(k, None)) for k in ("rt_call_time", "rt_call_duration", "rt_total_time"))
    if ct is not None or cd is not None or tt is not None:
        # "examples" (padrão): os 2 exemplos oficiais trazem call_time > call_duration e, no do PDF,
        # call_time = call_duration + call_time_waiting (11 = 3 + 8): call_time = total, call_duration = falado.
        # "descriptions": a tabela do manual (call_time = "efetivo", call_duration = "total").
        spoken, total = (cd, ct) if time_fields in ("examples", "inverted") else (ct, cd)
        if tt is not None:
            total = tt
        if spoken is not None and total is not None and spoken > total:
            spoken, total = total, spoken
            anomalies.append("time_fields_swapped")
        if spoken is not None:
            out["spoken"] = spoken
        if total is not None:
            out["total_duration"] = total

    for k in ("central_id", "branch_email", "branch_line_number", "status_raw", "transfer_id", "terminal",
              "audio_file", "origin_call_id", "provider_ticket_id", "tax_type", "rating_type", "rating_form_id",
              "rating_name", "queue_overflow", "branch_mask_agent", "agents_called", "attended_date", "attended_hour"):
        c = clean(extra.get(k))
        if c is not None:
            out[k] = c
    for k in ("cost", "tax", "rating", "rating_weight", "rating_yes", "rating_no", "report_abandoned_ura"):
        c = clean(extra.get(k))
        if c is not None:
            try:
                out[k] = float(str(c).replace(",", "."))
            except ValueError:
                anomalies.append("bad_number:" + k)
    if out.get("central_id") and not out.get("central"):
        out["central"] = out["central_id"]
    if out.get("transfer_id") and out.get("transfer_id") == out.get("call_id"):
        out.pop("transfer_id")
    if out.get("origin_call_id") and out.get("origin_call_id") == out.get("call_id"):
        out.pop("origin_call_id")
    if out.get("status_raw"):
        out["status_key"] = re.sub(r"[^a-z0-9]+", "_", slug(out["status_raw"])).strip("_")
    t = out.get("type")
    if t in ("active",):
        out["type"] = "ativo"
    elif t in ("receptive",):
        out["type"] = "receptivo"
    if out.get("call_date") and str(out["call_date"]).lower().startswith("invalid"):
        out.pop("call_date")
        anomalies.append("call_date_invalid")
    return out, anomalies


def phase(d: Dict[str, Any], source: str) -> str:
    """start | end | transfer | report (sem campo oficial: fase inferida)."""
    if source == "report02":
        return "report"
    if d.get("transfer_id"):
        return "transfer"
    if has_end_data(d) or d.get("status_raw"):
        return "end"
    return "start"


RANK = {"start": 1, "end": 2, "transfer": 2, "report": 2}


def started_at(d: Dict[str, Any], tz_hours: int, fallback: dt.datetime) -> dt.datetime:
    t = call_datetime(d, tz_hours)
    return t.astimezone(dt.timezone.utc) if t else fallback


def e164(d: Dict[str, Any]) -> Optional[str]:
    if d.get("type") == "interno":
        return None
    return to_e164(d.get("number"), d.get("area_code"), d.get("country_code"))


def mask_e164(n: Optional[str]) -> Optional[str]:
    if not n:
        return None
    return n[:6] + "*" * max(0, len(n) - 10) + n[-4:] if len(n) > 10 else n[:3] + "****"


def branch_digits(d: Dict[str, Any]) -> Optional[str]:
    b = digits(d.get("branch"))
    return b or None
