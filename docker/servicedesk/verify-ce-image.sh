#!/usr/bin/env bash
# Verifica que uma imagem do ServiceDesk é CE pura (sem enterprise/) e que ela sobe.
#   docker/servicedesk/verify-ce-image.sh <imagem:tag>
# Sai com código != 0 (e "FALHA: ...") se:
#   - /app/enterprise ou /app/spec/enterprise existir na imagem;
#   - CW_EDITION não for "ce";
#   - ChatwootApp.enterprise? for verdadeiro ou ChatwootApp.extensions não for vazio;
#   - a aplicação não preparar o banco, não bootar ou não responder em /api;
#   - os assets do tema ServiceDesk não estiverem no build do Vite.
# Usa containers temporários de Postgres e Redis numa rede própria, removidos ao final.
# Não usa nenhum banco real: tudo é criado e apagado aqui.
set -euo pipefail

IMAGE="${1:?uso: $0 <imagem:tag>}"
RUN_ID="sdverify-$$-$RANDOM"
NET="$RUN_ID-net"
PG="$RUN_ID-pg"
REDIS="$RUN_ID-redis"
APP="$RUN_ID-app"
PG_IMAGE="${VERIFY_PG_IMAGE:-pgvector/pgvector:pg16}"
REDIS_IMAGE="${VERIFY_REDIS_IMAGE:-redis:7-alpine}"

fail() { echo "FALHA: $*" >&2; exit 1; }
cleanup() {
  docker rm -f "$APP" "$PG" "$REDIS" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Roda um comando na imagem sem o entrypoint e sem DISABLE_ENTERPRISE
# (com essa variável definida, enterprise? retorna nil mesmo com o diretório presente).
in_image() { docker run --rm --entrypoint env "$IMAGE" -u DISABLE_ENTERPRISE "$@"; }

echo ">> 1/6 /app/enterprise ausente"
in_image sh -c 'test ! -e /app/enterprise' || fail "/app/enterprise existe na imagem"
in_image sh -c 'test ! -e /app/spec/enterprise' || fail "/app/spec/enterprise existe na imagem"

echo ">> 2/6 CW_EDITION=ce"
edition=$(in_image sh -c 'printf %s "${CW_EDITION:-}"')
[ "$edition" = "ce" ] || fail "CW_EDITION='$edition' (esperado 'ce')"

echo ">> 3/6 ChatwootApp.enterprise? (Ruby puro)"
in_image ruby -e '
  require "/app/lib/chatwoot_app"
  ent = ChatwootApp.enterprise?
  ext = ChatwootApp.extensions
  puts "enterprise?=#{ent.inspect} extensions=#{ext.inspect}"
  exit((ent || ext.any?) ? 1 : 0)
' || fail "ChatwootApp.enterprise? verdadeiro (Ruby puro)"

echo ">> 4/6 assets do tema ServiceDesk no build do Vite"
in_image sh -c 'test -f /app/public/vite/.vite/manifest.json || test -f /app/public/vite/manifest.json' \
  || fail "manifest do Vite ausente"
in_image sh -c 'grep -lq "sd-status" /app/public/vite/assets/*.css' \
  || fail "CSS do tema ServiceDesk (sd-status) ausente no build"

echo ">> 5/6 Postgres e Redis temporários"
PG_PASS=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" -e POSTGRES_PASSWORD="$PG_PASS" "$PG_IMAGE" >/dev/null
docker run -d --name "$REDIS" --network "$NET" "$REDIS_IMAGE" >/dev/null
for _ in $(seq 1 60); do
  docker exec "$PG" pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 2
done
docker exec "$PG" pg_isready -U postgres >/dev/null 2>&1 || fail "postgres temporário não ficou pronto"

APP_ENV=(
  -e RAILS_ENV=production -e NODE_ENV=production -e INSTALLATION_ENV=docker
  -e SECRET_KEY_BASE="$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  -e FRONTEND_URL=http://localhost:3000 -e RAILS_LOG_TO_STDOUT=true -e LOG_LEVEL=warn
  -e POSTGRES_HOST="$PG" -e POSTGRES_USERNAME=postgres -e POSTGRES_PASSWORD="$PG_PASS"
  -e POSTGRES_DATABASE=chatwoot_verify -e REDIS_URL="redis://$REDIS:6379"
  -e ENABLE_ACCOUNT_SIGNUP=false
)
app_run() { docker run --rm --network "$NET" "${APP_ENV[@]}" --entrypoint env "$IMAGE" -u DISABLE_ENTERPRISE "$@"; }

app_run bundle exec rails db:chatwoot_prepare || fail "db:chatwoot_prepare falhou"

echo ">> 6/6 boot da aplicação: ChatwootApp.enterprise? e /api"
app_run bundle exec rails runner '
  ent = ChatwootApp.enterprise?
  ext = ChatwootApp.extensions
  const = Object.const_defined?(:Enterprise, false)
  puts "rails: enterprise?=#{ent.inspect} extensions=#{ext.inspect} Enterprise definido=#{const}"
  exit((ent || ext.any? || const) ? 1 : 0)
' || fail "ChatwootApp.enterprise? verdadeiro (app bootada)"

docker run -d --name "$APP" --network "$NET" "${APP_ENV[@]}" --entrypoint env "$IMAGE" -u DISABLE_ENTERPRISE \
  bundle exec rails s -p 3000 -b 0.0.0.0 >/dev/null
ok=""
for _ in $(seq 1 60); do
  if body=$(docker exec "$APP" wget -qO- http://127.0.0.1:3000/api 2>/dev/null); then ok=1; break; fi
  sleep 3
done
if [ -z "$ok" ]; then
  docker logs --tail 80 "$APP" >&2 || true
  fail "a aplicação não respondeu em /api"
fi
echo "/api: $body"

echo "OK: imagem CE sem enterprise ($IMAGE)"
