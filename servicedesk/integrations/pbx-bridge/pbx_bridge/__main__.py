"""CLI: python -m pbx_bridge <comando>

  serve                      sobe o HTTP (webhook/health) + worker + poller (porta PORT, padrão 8080)
  poll-once                  uma passada do Report02 e processa a fila (exige ENABLED=true)
  work-once                  processa a fila pendente uma vez
  ingest FILE                enfileira um payload (JSON/form) de arquivo, como se viesse do webhook
  backfill [--limit N] [--dry-run] [--sleep S] [--label L] [--inbox-id I] [--conversation ID ...]
  estimate --urls FILE       HEAD em URLs de gravação (tamanho/autenticação), sem baixar conteúdo
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .app import Bridge, create_app, setup_logging
from .config import Settings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pbx_bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("poll-once")
    sub.add_parser("work-once")
    p = sub.add_parser("ingest")
    p.add_argument("file")
    p.add_argument("--content-type", default="application/json")
    b = sub.add_parser("backfill")
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--sleep", type=float, default=3.0)
    b.add_argument("--label", default="55pbx")
    b.add_argument("--inbox-id", type=int)
    b.add_argument("--conversation", type=int, action="append")
    e = sub.add_parser("estimate")
    e.add_argument("--urls", required=True)
    a = ap.parse_args(argv)
    s = Settings.from_env()
    setup_logging(s.log_level)

    if a.cmd == "serve":
        import uvicorn
        uvicorn.run(create_app(s), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")),
                    proxy_headers=False, access_log=False, log_level="warning")
        return 0
    if a.cmd == "estimate":
        from .backfill import estimate
        urls = [l.strip() for l in open(a.urls) if l.strip()]
        r = estimate(urls)
        if os.environ.get("ESTIMATE_DETAIL") != "1":
            r.pop("itens")
        print(json.dumps(r, indent=1))
        return 0
    if a.cmd == "backfill":
        from .backfill import run
        missing = [p for p in s.problems() if p in ("CHATWOOT_URL", "CHATWOOT_API_TOKEN", "CHATWOOT_ACCOUNT_ID")]
        if missing:
            print("Configuração incompleta: " + ", ".join(missing), file=sys.stderr)
            return 2
        br = Bridge(s)
        print(json.dumps(run(s, br.store, br.cw, a.limit, a.dry_run, a.sleep, a.label, a.inbox_id, a.conversation),
                         indent=1))
        return 0
    if not s.enabled:
        print("ENABLED=false: nada é processado.", file=sys.stderr)
        return 3
    br = Bridge(s)
    if a.cmd == "ingest":
        with open(a.file, "rb") as f:
            print(json.dumps(br.ingest(f.read(), a.content_type, "manual")))
        br.work_once()
    elif a.cmd == "poll-once":
        print(json.dumps(br.poll_once()))
        br.work_once()
    elif a.cmd == "work-once":
        print(json.dumps({"processados": br.work_once()}))
    print(json.dumps(br.store.counts()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
