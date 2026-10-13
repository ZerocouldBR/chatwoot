"""Cliente do Report02 da 55PBX (manual "Integração GET Web Services")."""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any, Dict, List
from urllib.parse import quote

import httpx

log = logging.getLogger("pbx_bridge.pbx_api")


class PbxError(Exception):
    pass


def fmt_date(d: dt.datetime, tz_hours: int = -3) -> str:
    """'Fri May 22 2020 00:00:00 GMT -0300' (formato exigido pela API)."""
    tz = dt.timezone(dt.timedelta(hours=tz_hours))
    d = d.astimezone(tz)
    sign = "-" if tz_hours < 0 else "+"
    return d.strftime("%a %b %d %Y %H:%M:%S") + " GMT %s%02d00" % (sign, abs(tz_hours))


class PbxApi:
    def __init__(self, base_url: str, key: str, key_header: str = "key", queue: str = "all_queues",
                 number: str = "all_numbers", agent: str = "all_agent", tz_hours: int = -3, timeout: float = 180.0,
                 retries: int = 4, client: httpx.Client = None, sleep=time.sleep):
        self.base = base_url.rstrip("/")
        self.key = key
        self.key_header = key_header
        self.queue, self.number, self.agent = queue, number, agent
        self.tz = tz_hours
        self.http = client or httpx.Client(timeout=timeout)
        self.retries = retries
        self.sleep = sleep

    def report02_url(self, start: dt.datetime, end: dt.datetime) -> str:
        seg = [fmt_date(start, self.tz), fmt_date(end, self.tz), self.queue, self.number, self.agent,
               "report_02", "undefined", "undefined", str(self.tz)]
        return self.base + "/" + "/".join(quote(s, safe="") for s in seg)

    def report02(self, start: dt.datetime, end: dt.datetime) -> List[Dict[str, Any]]:
        if not self.key:
            raise PbxError("PBX_API_KEY não configurada")
        url = self.report02_url(start, end)
        last: Exception = PbxError("sem tentativa")
        for attempt in range(self.retries + 1):
            try:
                r = self.http.get(url, headers={self.key_header: self.key, "Accept": "application/json"})
                if r.status_code == 200:
                    body = r.json()
                    rows = body.get("data_report02") if isinstance(body, dict) else body
                    if rows is None:
                        rows = []
                    if not isinstance(rows, list):
                        raise PbxError("resposta sem data_report02")
                    return rows
                if r.status_code in (401, 403):
                    raise PbxError("55PBX recusou a chave (HTTP %d): confira PBX_API_KEY e PBX_API_KEY_HEADER" % r.status_code)
                last = PbxError("55PBX HTTP %d" % r.status_code)
            except (httpx.TransportError, ValueError) as e:
                last = e
            if attempt < self.retries:
                delay = min(5 * 2 ** attempt, 120)
                log.warning("Report02 falhou (%s); nova tentativa em %ss", type(last).__name__, delay)
                self.sleep(delay)
        raise PbxError(str(last))
