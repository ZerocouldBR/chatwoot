#!/usr/bin/env bash
# e2e dos workflows num n8n DESCARTÁVEL (docker) contra um mock do sd-ops e do Chatwoot.
# Não toca na instância do cliente. Uso: bash tools/e2e/run_e2e.sh [imagem_n8n]
set -euo pipefail
IMG="${1:-n8nio/n8n:latest}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d)"
NET="sdn8n-e2e-$$"
cleanup() { docker rm -f "sd-n8n-$$" "sd-mock-$$" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

python3 "$HERE/prepare.py" "$ROOT/workflows" "$WORK"
cp "$HERE/mock_server.js" "$HERE/scenarios.js" "$WORK/"
chmod -R a+rX "$WORK"

docker network create "$NET" >/dev/null
docker run -d --name "sd-mock-$$" --network "$NET" --network-alias sd-mock -v "$WORK:/e2e:ro" node:24-alpine node /e2e/mock_server.js >/dev/null
docker run -d --name "sd-n8n-$$" --network "$NET" --network-alias sd-n8n -v "$WORK:/e2e:ro" \
  -e N8N_ENCRYPTION_KEY=e2e-somente-teste-0123456789abcdef -e GENERIC_TIMEZONE=America/Sao_Paulo \
  -e N8N_DIAGNOSTICS_ENABLED=false -e N8N_RUNNERS_ENABLED=true -e N8N_SECURE_COOKIE=false \
  --entrypoint sh "$IMG" -c '
    n8n import:credentials --input=/e2e/creds.json &&
    n8n import:workflow --separate --input=/e2e/workflows &&
    for id in $(n8n list:workflow --onlyId 2>/dev/null | grep -E "^[A-Za-z0-9]{16}$"); do n8n publish:workflow --id="$id" >/dev/null 2>&1 || echo "falha ao publicar $id"; done &&
    echo "publicados: $(n8n list:workflow --active=true 2>/dev/null | grep -c "|SD WF")" &&
    exec n8n start' >/dev/null

echo "aguardando o n8n subir..."
# a publicação via CLI (1 processo por workflow) e as migrations levam minutos numa VPS carregada
for i in $(seq 1 180); do
  if docker logs "sd-n8n-$$" 2>&1 | grep -q "Editor is now accessible"; then break; fi
  sleep 5
done
sleep 10
docker logs "sd-n8n-$$" 2>&1 | grep -E "publicados|falha ao publicar|Activated|Editor is now" | tail -5
echo "n8n: $(docker exec "sd-n8n-$$" n8n --version 2>/dev/null | tail -1)"
docker exec "sd-mock-$$" node /e2e/scenarios.js
