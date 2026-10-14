"""CLI: python -m qa_pipeline <comando>

  api                         API do console de QA (uvicorn, porta PORT)
  worker                      worker assíncrono (consome sd:events)
  migrate                     alembic upgrade head (schema qa, version_table em qa)
  process-once                aplica eventos pendentes e processa 1 job (diagnóstico)
  reprocess <recording_id> [full|analysis] "<motivo>"
  new-service-token <nome> <tenant> <escopos,separados>
"""
from __future__ import annotations

import os
import sys

from . import logutil
from .config import get_settings


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "api"
    s = get_settings()
    logutil.setup(s.log_level)
    if cmd == "api":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(s), host="0.0.0.0", port=s.port, proxy_headers=True, forwarded_allow_ips="*",
                    log_config=None)
        return 0
    if cmd == "worker":
        from .runner import run_worker
        run_worker(s)
        return 0
    if cmd == "migrate":
        from alembic import command
        from alembic.config import Config
        cfg = Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"))
        command.upgrade(cfg, argv[1] if len(argv) > 1 else "head")
        return 0
    if cmd == "process-once":
        from .runner import build_pipeline, consume_once
        pipe = build_pipeline(s)
        pipe.bus.ensure_group()
        print("eventos:", consume_once(pipe, block_ms=100), "jobs:", pipe.run_due(1), "sdops:", pipe.deliver_sdops())
        return 0
    if cmd == "reprocess":
        from .runner import build_pipeline
        pipe = build_pipeline(s)
        job = pipe.request_reprocess(s.tenant_default, argv[1], argv[2] if len(argv) > 2 else "full", "cli", "admin",
                                     argv[3] if len(argv) > 3 else "reprocessamento manual")
        print(f"job {job.id} run {job.run} status {job.status}")
        return 0
    if cmd == "new-service-token":
        from .auth import new_service_token
        tok, line = new_service_token(argv[1], argv[2].split(","), argv[3].split(","))
        print("TOKEN (exibido uma vez):", tok)
        print("QA_SERVICE_TOKENS entry:", line)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
