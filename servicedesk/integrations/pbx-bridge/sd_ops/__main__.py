"""CLI: python -m sd_ops <comando>

  serve                         HTTP (webhooks, API, URA, health) + workers (porta PORT, padrão 8080)
  migrate [--revision head]     Alembic (schema ops no banco SDOPS_DATABASE_URL)
  downgrade --revision R        volta a migration (rollback)
  work-once                     processa inbox e outbox até esvaziar o que está pronto
  poll-once                     uma passada do Report02 (janela POLL_LOOKBACK_MIN) + processamento
  reconcile --from ISO --to ISO reconciliação histórica pelo Report02 (blocos de 6 h)
  seed-tenant ...               cadastra/atualiza um tenant (idempotente)
  new-service-token NOME [--profile n8n|qa-pipeline] [--scopes a,b] [--tenants b2b]
                                gera token de serviço (mostra uma vez) e a linha para SDOPS_SERVICE_TOKENS;
                                NOME igual a um perfil (n8n, qa-pipeline) usa os escopos dele
  export-openapi [ARQ]          grava o OpenAPI (padrão: openapi.json ao lado do pacote)
  new-settings-key              gera uma chave Fernet para SDOPS_SETTINGS_KEY (cofre da tela Telefonia 55PBX)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sd_ops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    mg = sub.add_parser("migrate")
    mg.add_argument("--revision", default="head")
    dg = sub.add_parser("downgrade")
    dg.add_argument("--revision", required=True)
    sub.add_parser("work-once")
    sub.add_parser("poll-once")
    rc = sub.add_parser("reconcile")
    rc.add_argument("--from", dest="frm", required=True)
    rc.add_argument("--to", required=True)
    rc.add_argument("--tenant")
    st = sub.add_parser("seed-tenant")
    st.add_argument("--id", required=True)
    st.add_argument("--name", required=True)
    st.add_argument("--account-id", type=int, required=True)
    st.add_argument("--inbox-id", type=int)
    st.add_argument("--integration-user-id", type=int)
    st.add_argument("--prefix", default="SD")
    st.add_argument("--webhook-secret-env", help="variável com o segredo do webhook (o hash vai para o banco)")
    st.add_argument("--webhook-token-env", help="variável com o token do header 'token' da 55PBX")
    st.add_argument("--chatwoot-token-env", help="variável com o token do usuário de integração")
    st.add_argument("--ura-token-env", help="variável com o token do Menu Dinâmico (header X-SD-URA-Token)")
    nt = sub.add_parser("new-service-token")
    nt.add_argument("name")
    nt.add_argument("--profile", help="perfil de escopos (n8n, qa-pipeline); padrão: o NOME, se for um perfil")
    nt.add_argument("--scopes", default="", help="escopos extras separados por vírgula")
    nt.add_argument("--tenants", default="", help="tenants separados por vírgula (padrão: SDOPS_DEFAULT_TENANT; * = todos)")
    sub.add_parser("new-settings-key")
    ex = sub.add_parser("export-openapi")
    ex.add_argument("file", nargs="?")
    a = ap.parse_args(argv)

    from .config import OpsSettings
    from . import obs
    s = OpsSettings.from_env()
    obs.setup_logging(s.bridge.log_level, s.log_json)

    if a.cmd == "new-settings-key":
        from .settings_store import new_key
        print(new_key())
        print("Guarde no sd-ops.env como SDOPS_SETTINGS_KEY (trocar a chave exige a anterior: "
              "SDOPS_SETTINGS_KEY=nova,antiga até regravar os segredos pela tela).", file=sys.stderr)
        return 0
    if a.cmd == "new-service-token":
        from .auth import SERVICE_PROFILES, new_service_token, service_token_entry
        profile = a.profile or (a.name if a.name in SERVICE_PROFILES else None)
        if profile and profile not in SERVICE_PROFILES:
            print("perfil desconhecido: %s (válidos: %s)" % (profile, ", ".join(SERVICE_PROFILES)), file=sys.stderr)
            return 2
        tenants = [x.strip() for x in a.tenants.split(",") if x.strip()] or [s.default_tenant]
        try:
            entry = service_token_entry(a.name, "", tenants, profile, [x.strip() for x in a.scopes.split(",") if x.strip()])
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not entry[a.name]["scopes"]:
            print("AVISO: token sem escopos (use --profile ou --scopes); só servirá para /auth/me", file=sys.stderr)
        t = new_service_token()
        entry[a.name]["sha256"] = t["sha256"]
        print("token (guarde agora, não é mostrado de novo): %s" % t["token"])
        print("perfil: %s | escopos: %s" % (profile or "-", ", ".join(entry[a.name]["scopes"]) or "-"))
        print(json.dumps(entry))
        return 0
    if a.cmd == "export-openapi":
        from .app import create_app
        os.environ.setdefault("SDOPS_DATABASE_URL", "postgresql+psycopg://x@127.0.0.1:1/x")
        s.database_url = s.database_url or "postgresql+psycopg://x@127.0.0.1:1/x"
        s.storage_dir = s.storage_dir if os.access(os.path.dirname(s.storage_dir) or "/", os.W_OK) else "/tmp/sdops-openapi"
        app = create_app(s, start_workers=False)
        path = a.file or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(app.openapi(), f, ensure_ascii=False, indent=1, sort_keys=True)
        print(path)
        return 0
    if not s.database_url:
        print("SDOPS_DATABASE_URL não configurada", file=sys.stderr)
        return 2
    if a.cmd == "migrate":
        from .bootstrap import migrate
        migrate(s.database_url, a.revision)
        print("migrate OK (%s)" % a.revision)
        return 0
    if a.cmd == "downgrade":
        from .bootstrap import downgrade
        downgrade(s.database_url, a.revision)
        print("downgrade OK (%s)" % a.revision)
        return 0
    if a.cmd == "seed-tenant":
        from . import db
        from .bootstrap import seed_tenant
        eng = db.make_engine(s.database_url)
        ura = {"type": "token", "header": "X-SD-URA-Token", "ref": a.ura_token_env} if a.ura_token_env else None
        with eng.begin() as conn:
            out = seed_tenant(conn, a.id, a.name, a.account_id, a.inbox_id, a.integration_user_id, a.prefix,
                              os.environ.get(a.webhook_secret_env) if a.webhook_secret_env else None,
                              a.webhook_token_env, a.chatwoot_token_env, ura)
        print(json.dumps(out))
        return 0
    if a.cmd == "serve":
        if os.environ.get("SDOPS_MIGRATE_ON_START", "").lower() in ("1", "true", "yes", "sim"):
            from .bootstrap import migrate
            migrate(s.database_url)
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(s), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")),
                    proxy_headers=False, access_log=False, log_level="warning")
        return 0
    from .app import Services
    svc = Services(s)
    if a.cmd == "work-once":
        print(json.dumps({"processados": svc.worker.run_until_idle()}))
    elif a.cmd == "poll-once":
        print(json.dumps(svc.worker.poll_once()))
        svc.worker.run_until_idle()
    elif a.cmd == "reconcile":
        def p(x):
            d = dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        print(json.dumps(svc.worker.reconcile(a.tenant or s.default_tenant, p(a.frm), p(a.to), "historical")))
        svc.worker.run_until_idle(200)
    print(json.dumps(svc.health(full=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
