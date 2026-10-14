"""Leitura tolerante dos payloads da 55PBX (Report02, webhook "Tempo real por URL") e utilitários.

O formato do webhook não é público. Aceitamos JSON (objeto, lista, ou embrulhado em data/call/payload/
data_report02) e form-urlencoded, e procuramos os campos do Report02 e variações óbvias (sem diferenciar
maiúsculas, hífen, underline ou camelCase). O que não tiver call_id volta como "não reconhecido".
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl

NA = "Informação não disponível para esta ligação"

# campo normalizado -> aliases (já em forma "chave normalizada": minúsculas, só [a-z0-9])
ALIASES: Dict[str, List[str]] = {
    "call_id": ["callid", "idcall", "callidorigin", "uniqueid", "linkedid", "idligacao", "ligacaoid", "callidentifier"],
    "ws_ticket_id": ["wsticketid", "ticketid"],
    "agent_name": ["name", "agentname", "agent", "agente", "nomeagente", "operator", "operador", "username"],
    "disconnection": ["calldisconnection", "disconnection", "desconexao", "hangupby", "hangup", "terminatedby", "endedby"],
    "total_duration": ["calltimetotalduration", "totalduration", "duration", "duracao", "duracaototal", "calltime", "tempototal"],
    "waiting": ["calltimewaiting", "waiting", "waittime", "tempoespera", "holdtime", "queuetime"],
    "spoken": ["calltimespoken", "spoken", "talktime", "billsec", "tempofalado", "callduration", "conversationtime"],
    "audio_url": ["callurlaudio", "urlaudio", "audiourl", "audio", "recording", "recordingurl", "gravacao", "urlgravacao", "record"],
    "branch": ["branchnumberagent", "branch", "ramal", "extension", "agentbranch", "branchnumber", "ramalagente"],
    "number": ["callnumber", "number", "numero", "phone", "telefone", "phonenumber", "callernumber", "callerid", "clientnumber", "destination", "destino"],
    "area_code": ["callareacode", "areacode", "ddd"],
    "country_code": ["wgcountrycode", "countrycode", "ddi"],
    "state": ["wfstates", "state", "estado", "uf"],
    "call_date": ["calldate", "date", "data", "datadaligacao", "dataligacao"],
    "call_hour": ["wbcallhour", "callhour", "hour", "hora"],
    "queue": ["queuename", "queue", "fila", "nomefila"],
    "type": ["typecall", "calltype", "type", "tipo", "tipoligacao", "tipodaligacao", "direction", "sentido"],
    "number_input": ["callnumberinput", "numberinput", "telefonedeentrada", "telefonedesaida", "did", "inputnumber"],
    "cpf": ["calldocument", "document", "cpf", "documento"],
    "order": ["callorder", "order", "pedido"],
    "ura": ["wayura", "ura", "ivr", "ivrpath"],
    "ura_time": ["calltimeura", "uratime", "tempoura"],
    "attended_at": ["wltimeattended", "timeattended", "attendedat"],
    "central": ["central", "company", "companyid", "centralnumber", "pbx"],
    "humor": ["humor", "humordocliente", "mood", "quizscore", "score", "nota", "satisfaction"],
    "client_name": ["clientname", "contactname", "nomedousuario", "nomeusuario", "customername", "nomecliente"],
    "event": ["event", "evento", "action", "acao", "status"],
}
_INDEX = {}
for _k, _al in ALIASES.items():
    _INDEX[re.sub(r"[^a-z0-9]", "", _k)] = _k
    for _a in _al:
        _INDEX.setdefault(_a, _k)

EMPTY = {"", "undefined", "null", "none", "nan", "-", NA.lower(), "informação não disponível", "telefone de entrada indisponível."}


def norm_key(k: str) -> str:
    k = unicodedata.normalize("NFKD", str(k)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", k)


def slug(s: str) -> str:
    """Normaliza nome (sem acento, minúsculas, espaços simples)."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def queue_key(q: str) -> str:
    s = slug(q)
    s = re.sub(r"^\d+\s*-\s*", "", s)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return str(v).strip().lower() in EMPTY


def clean(v: Any) -> Optional[str]:
    if is_empty(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def to_seconds(v: Any) -> Optional[int]:
    """'00:01:05' -> 65; '65' -> 65; 65.4 -> 65."""
    v = clean(v)
    if v is None:
        return None
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}", v):
        parts = [int(p) for p in v.split(":")]
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        return sec
    try:
        return int(float(v.replace(",", ".")))
    except ValueError:
        return None


def norm_type(v: Any) -> Optional[str]:
    v = clean(v)
    if v is None:
        return None
    s = slug(v)
    if s in ("ativo", "outbound", "out", "saida", "outgoing", "efetuada", "realizada", "active"):
        return "ativo"
    if s in ("receptivo", "inbound", "in", "entrada", "incoming", "recebida", "receptive"):
        return "receptivo"
    if s in ("interno", "internal", "interna", "ramal"):
        return "interno"
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or None


def norm_disconnection(v: Any) -> Optional[str]:
    v = clean(v)
    if v is None:
        return None
    s = slug(v)
    if any(w in s for w in ("operator", "operador", "agent", "agente", "atendente")):
        return "operador"
    if any(w in s for w in ("client", "cliente", "customer", "caller", "origem")):
        return "cliente"
    return v


def norm_humor(v: Any) -> Optional[int]:
    v = clean(v)
    if v is None:
        return None
    m = re.match(r"\s*(\d+)", v)
    return int(m.group(1)) if m else None


def digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def to_e164(number: Any, area_code: Any = None, country_code: Any = None) -> Optional[str]:
    """Telefone em E.164 (+55DDD...). Ramais e números curtos devolvem None."""
    raw = str(number or "").strip()
    n = digits(raw)
    if not n:
        return None
    cc = digits(country_code) or "55"
    if raw.startswith("+") and 8 <= len(n) <= 15:
        return "+" + n
    n = n.lstrip("0") if len(n) > 11 else n
    if n.startswith("0") and len(n) in (11, 12):  # 0 + DDD + número
        n = n[1:]
    if cc == "55":
        if n.startswith("55") and len(n) in (12, 13):
            return "+" + n
        if len(n) in (10, 11):
            return "+55" + n
        if len(n) in (8, 9):
            ddd = digits(area_code)
            if len(ddd) == 2:
                return "+55" + ddd + n
            return None
        return None
    if n.startswith(cc) and 8 <= len(n) <= 15:
        return "+" + n
    if 6 <= len(n) + len(cc) <= 15:
        return "+" + cc + n
    return None


def mobile_variants(e164: str) -> List[str]:
    """+55DD9XXXXXXXX <-> +55DDXXXXXXXX (contatos antigos sem o 9º dígito)."""
    out = [e164]
    if e164.startswith("+55"):
        local = e164[5:]
        if len(local) == 9 and local[0] == "9":
            out.append(e164[:5] + local[1:])
        elif len(local) == 8 and local[0] in "6789":
            out.append(e164[:5] + "9" + local)
    return out


_DIG = re.compile(r"\d{5,}")


def mask(s: Any) -> str:
    """Mascara sequências de 5+ dígitos (telefone, CPF, número em URL de gravação)."""
    return _DIG.sub(lambda m: m.group(0)[:2] + "*" * (len(m.group(0)) - 4) + m.group(0)[-2:], str(s))


def mask_payload(obj: Any, limit: int = 2000) -> str:
    try:
        txt = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        txt = str(obj)
    return mask(txt)[:limit]


# ---------------------------------------------------------------- parsing
def parse_body(body: bytes, content_type: str = "") -> Tuple[List[Dict[str, Any]], Any]:
    """Devolve (lista de registros planos, objeto bruto decodificado)."""
    text = body.decode("utf-8", errors="replace").strip()
    ct = (content_type or "").lower()
    obj: Any = None
    if "json" in ct or text[:1] in ("{", "["):
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
    if obj is None and ("=" in text and "form" in ct or re.match(r"^[\w\-.%\[\]]+=", text)):
        pairs = parse_qsl(text, keep_blank_values=True)
        obj = {}
        for k, v in pairs:
            obj[k] = v
        # campos com JSON embutido (ex.: data={...})
        for k in list(obj):
            v = obj[k]
            if isinstance(v, str) and v[:1] in ("{", "["):
                try:
                    obj[k] = json.loads(v)
                except ValueError:
                    pass
    if obj is None:
        return [], text
    return list(_records(obj)), obj


def _records(obj: Any, depth: int = 0) -> Iterable[Dict[str, Any]]:
    if depth > 4:
        return
    if isinstance(obj, list):
        for it in obj:
            yield from _records(it, depth + 1)
        return
    if not isinstance(obj, dict):
        return
    # lista de ligações embrulhada (data_report02, data, calls, ...)
    for k, v in obj.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and norm_key(k) in (
            "datareport02", "data", "calls", "ligacoes", "records", "items", "result", "results"):
            yield from _records(v, depth + 1)
            return
    flat: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, dict) and norm_key(k) in ("data", "call", "payload", "ligacao", "body", "content", "info"):
            for k2, v2 in v.items():
                if not isinstance(v2, (dict, list)):
                    flat.setdefault(k2, v2)
        elif not isinstance(v, (dict, list)):
            flat[k] = v
    yield flat


def normalize(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Registro (Report02 ou webhook) -> campos normalizados (só os presentes)."""
    out: Dict[str, Any] = {}
    extra = {}
    ivr = []
    for k, v in rec.items():
        nk = norm_key(k)
        target = _INDEX.get(nk)
        m = re.match(r"wkivr(\d+)(name|option|optionname)$", nk)
        if m:
            if clean(v):
                ivr.append((int(m.group(1)), m.group(2), clean(v)))
            continue
        if target is None:
            if clean(v) is not None:
                extra[k] = v
            continue
        if target in out and out[target] not in (None, ""):
            continue  # primeiro alias com valor vence
        out[target] = v
    res: Dict[str, Any] = {}
    cid = clean(out.get("call_id"))
    if cid:
        res["call_id"] = cid
    for k in ("ws_ticket_id", "agent_name", "branch", "area_code", "country_code", "state", "queue",
              "number_input", "cpf", "order", "ura", "central", "client_name", "attended_at", "call_date", "call_hour",
              "event"):
        c = clean(out.get(k))
        if c is not None:
            res[k] = c
    num = clean(out.get("number"))
    if num is not None:
        res["number"] = num
    for k in ("total_duration", "waiting", "spoken", "ura_time"):
        s = to_seconds(out.get(k))
        if s is not None:
            res[k] = s
    t = norm_type(out.get("type"))
    if t:
        res["type"] = t
    d = norm_disconnection(out.get("disconnection"))
    if d:
        res["disconnection"] = d
    h = norm_humor(out.get("humor"))
    if h is not None:
        res["humor"] = h
    a = clean(out.get("audio_url"))
    if a and re.match(r"^https?://", a):
        res["audio_url"] = a
    if ivr:
        steps: Dict[int, Dict[str, str]] = {}
        for n, kind, v in ivr:
            steps.setdefault(n, {})[kind] = v
        res["ivr"] = " > ".join(
            "{}: {}".format(s.get("name", "URA %d" % n), s.get("optionname") or s.get("option", ""))
            for n, s in sorted(steps.items()))
    return res


def merge(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(old)
    for k, v in new.items():
        if v is None or v == "":
            continue
        out[k] = v
    return out


def call_datetime(c: Dict[str, Any], tz_hours: int = -3) -> Optional[dt.datetime]:
    """Data/hora local da ligação: call_date (+ call_hour) > attended_at (UTC) > epoch do call_id."""
    tz = dt.timezone(dt.timedelta(hours=tz_hours))
    d = c.get("call_date")
    if d:
        hour = c.get("call_hour") or ""
        s = d if re.search(r"\d{1,2}:\d{2}", d) else (d + " " + hour).strip()
        for fmt, size in (("%d/%m/%Y %H:%M:%S", 19), ("%d/%m/%Y %H:%M", 16), ("%d/%m/%Y", 10),
                          ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
            try:
                return dt.datetime.strptime(s[:size], fmt).replace(tzinfo=tz)
            except ValueError:
                continue
    a = c.get("attended_at")
    if a:
        try:
            return dt.datetime.fromisoformat(a.replace("Z", "+00:00")).astimezone(tz)
        except ValueError:
            pass
    cid = c.get("call_id") or ""
    m = re.match(r"^(\d{10})(\.\d+)?$", cid)
    if m:
        return dt.datetime.fromtimestamp(int(m.group(1)), tz)
    return None


def has_end_data(c: Dict[str, Any]) -> bool:
    """A ligação terminou (temos durações/gravação/desconexão)?"""
    return any(k in c for k in ("total_duration", "spoken", "audio_url", "disconnection"))
