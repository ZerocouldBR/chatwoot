#!/usr/bin/env bash
# e2e da API de compatibilidade com o Zendesk (M7) com o n8n de verdade, contra o Rails do DEV deste worktree.
# Pré-requisitos: Rails do DEV em 127.0.0.1:${RAILS_PORT:-3530} com ZENDESK_COMPAT_ENABLED=true e o seed
# db/seeds/servicedesk_zendesk_compat_e2e.rb rodado (saída em $WORK/seed.json); imagem n8nio/n8n; exportação dos workflows.
# Uso: run.sh <dir dos workflows exportados> <dir de trabalho> <token>
# O n8n roda num contêiner descartável (rede do host, banco SQLite temporário), nada é gravado no n8n do cliente.
set -euo pipefail
EXPORT_DIR=$1; WORK=$2; TOKEN=$3
HERE=$(cd "$(dirname "$0")" && pwd)
PORT=${E2E_TLS_PORT:-8443}
SUBDOMAIN="127.0.0.1:${PORT}/b2b-reservas"
mkdir -p "$WORK"
[ -f "$WORK/key.pem" ] || openssl req -x509 -newkey rsa:2048 -nodes -keyout "$WORK/key.pem" -out "$WORK/cert.pem" -days 2 -subj /CN=localhost 2>/dev/null
chmod 644 "$WORK/key.pem" "$WORK/cert.pem"  # certificado descartável do e2e; o n8n roda como usuário node
python3 "$HERE/build_workflow.py" "$EXPORT_DIR" "$WORK/seed.json" "$SUBDOMAIN" > "$WORK/workflow.json"
SUNSHINE_AUTH="Basic $(printf 'app_e2e:%s' "$TOKEN" | base64 -w0)"
cat > "$WORK/credentials.json" <<JSON
[
  {"id": "sdZendeskCompat01", "name": "ServiceDesk (compat Zendesk)", "type": "zendeskApi",
   "data": {"subdomain": "$SUBDOMAIN", "email": "agenteia.suporte.e2e@example.com", "apiToken": "$TOKEN"}},
  {"id": "sdSunshineCompat1", "name": "ServiceDesk Sunshine", "type": "httpHeaderAuth",
   "data": {"name": "Authorization", "value": "$SUNSHINE_AUTH"}}
]
JSON
cp "$HERE/tls_proxy.js" "$WORK/"
docker run --rm --network host -v "$WORK":/e2e -e N8N_USER_FOLDER=/tmp/n8n -e N8N_ENCRYPTION_KEY=e2e-m7-descartavel \
  -e NODE_TLS_REJECT_UNAUTHORIZED=0 -e N8N_DIAGNOSTICS_ENABLED=false -e N8N_RUNNERS_ENABLED=false \
  -e PORT="$PORT" -e TARGET="http://127.0.0.1:${RAILS_PORT:-3530}" -e KEY=/e2e/key.pem -e CERT=/e2e/cert.pem \
  --entrypoint sh n8nio/n8n:latest -c '
    node /e2e/tls_proxy.js & sleep 1
    n8n import:credentials --input=/e2e/credentials.json >/dev/null 2>&1
    n8n import:workflow --input=/e2e/workflow.json >/dev/null 2>&1
    n8n execute --id=sdZendeskCompatE2E --rawOutput' > "$WORK/execution.json" 2> "$WORK/execution.err" || true
python3 - "$WORK/execution.json" <<'PY'
import json, re, sys
raw = open(sys.argv[1]).read()
start = raw.find('{') if raw.find('{') >= 0 else 0
try:
    data = json.loads(raw[start:])
except Exception:
    print('saída do n8n não é JSON:', raw[:2000]); sys.exit(1)
runs = data.get('data', {}).get('resultData', {}).get('runData', {}) if 'data' in data else data.get('resultData', {}).get('runData', {})
error = (data.get('data') or data).get('resultData', {}).get('error')
for name, executions in runs.items():
    status = 'erro' if any(e.get('error') for e in executions) else 'ok'
    items = sum(len((e.get('data') or {}).get('main', [[]])[0] or []) for e in executions)
    print(f'{status:4} {name} ({items} item(ns))')
verify = runs.get('verifica', [{}])[0].get('data', {}).get('main', [[{}]])[0]
summary = verify[0]['json'] if verify else {'ok': False, 'falhas': ['verifica não rodou'], 'erro': error}
print(json.dumps(summary, ensure_ascii=False, indent=1))
sys.exit(0 if summary.get('ok') else 1)
PY
