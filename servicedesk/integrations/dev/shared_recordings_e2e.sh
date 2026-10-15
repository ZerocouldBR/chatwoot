#!/usr/bin/env sh
# Prova, com as IMAGENS reais e um volume Docker de verdade, que o qa-pipeline lê a gravação salva pelo sd-ops
# (grupo comum "sdrec" gid 10010 + SDOPS_STORAGE_FILE_MODE=0640 / SDOPS_STORAGE_DIR_MODE=0750; INTEGRACAO-55PBX.md §17).
#
#   sh servicedesk/integrations/dev/shared_recordings_e2e.sh            # constrói as duas imagens (qa sem STT) e testa
#   SDOPS_IMG=... QA_IMG=... SKIP_BUILD=1 sh .../shared_recordings_e2e.sh   # testa imagens já construídas (ex.: GHCR)
#
# Monta o volume como nas stacks (infra/vps/sd-ops.stack.yml e qa-pipeline.stack.yml): no sd-ops em /data/recordings
# (leitura e escrita), no qa em /sdops/recordings SOMENTE LEITURA, raiz dos containers somente leitura.
# Sai com 0 e imprime SHARED_RECORDINGS_OK quando tudo confere. Não usa rede nem segredos; apaga o volume no fim.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
SDOPS_IMG=${SDOPS_IMG:-sdrec-e2e/sd-ops:dev}
QA_IMG=${QA_IMG:-sdrec-e2e/qa-pipeline:dev}
VOL=sdrec-e2e-$$
KEY=recordings/b2b/2026/10/14/e2e-call.mp3
fail() { echo "FALHA: $*" >&2; docker volume rm -f "$VOL" >/dev/null 2>&1 || true; exit 1; }

if [ -z "${SKIP_BUILD:-}" ]; then
  docker build -q -t "$SDOPS_IMG" "$HERE/pbx-bridge" >/dev/null || fail "build do sd-ops"
  docker build -q --build-arg WITH_STT=0 -t "$QA_IMG" "$HERE/qa-pipeline" >/dev/null || fail "build do qa-pipeline"
fi
docker volume create "$VOL" >/dev/null
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true' EXIT

echo "1) sd-ops (imagem, usuário padrão) grava a gravação"
docker run --rm --read-only --tmpfs /tmp -v "$VOL:/data/recordings" \
  -e SDOPS_STORAGE_FILE_MODE=0640 -e SDOPS_STORAGE_DIR_MODE=0750 "$SDOPS_IMG" \
  python -c "
import hashlib, os
from sd_ops.storage import LocalStorage
data = b'ID3' + os.urandom(4096)
LocalStorage('/data/recordings').put('$KEY', data, 'audio/mpeg')
print('id', os.getuid(), os.getgid(), os.getgroups())
print('sha', hashlib.sha256(data).hexdigest())
" > /tmp/sdrec-w-$$.txt || fail "sd-ops não gravou"
cat /tmp/sdrec-w-$$.txt
SHA=$(sed -n 's/^sha //p' /tmp/sdrec-w-$$.txt); rm -f /tmp/sdrec-w-$$.txt

echo "2) dono, grupo e modos no volume"
STAT=$(docker run --rm --read-only -v "$VOL:/v:ro" --entrypoint sh "$QA_IMG" -c \
  "stat -c '%u:%g:%a' /v /v/recordings /v/$(dirname $KEY) /v/$KEY | tr '\n' ' '")
echo "   $STAT"
[ "$STAT" = "10001:10010:750 10001:10010:750 10001:10010:750 10001:10010:640 " ] || fail "modos/grupo inesperados: $STAT"

echo "3) qa-pipeline (imagem, usuário padrão) lê pelo próprio storage"
OUT=$(docker run --rm --read-only --tmpfs /tmp -v "$VOL:/sdops/recordings:ro" "$QA_IMG" python -c "
import hashlib, os, tempfile
from qa_pipeline.storage import LocalStorage
p = LocalStorage('/sdops/recordings').fetch('$KEY', tempfile.mkdtemp(), 50 * 1024 * 1024)
print('id', os.getuid(), os.getgid(), sorted(os.getgroups()))
print('sha', hashlib.sha256(open(p, 'rb').read()).hexdigest())
") || fail "qa não leu a gravação"
echo "$OUT" | sed 's/^/   /'
[ "$(echo "$OUT" | sed -n 's/^sha //p')" = "$SHA" ] || fail "conteúdo lido difere do gravado"

echo "4) qa não apaga nem altera (mesmo com o volume em leitura e escrita)"
docker run --rm --read-only -v "$VOL:/sdops/recordings" "$QA_IMG" python -c "
import os, sys
p = '/sdops/recordings/$KEY'
for op in (lambda: os.unlink(p), lambda: open(p, 'ab')):
    try:
        op(); sys.exit('qa conseguiu alterar a gravação')
    except PermissionError:
        pass
" || fail "qa conseguiu alterar a gravação"

echo "5) controle: sem o grupo comum não lê"
for U in 10002:10002 10003:10003; do
  if docker run --rm --read-only --tmpfs /tmp --user "$U" -v "$VOL:/sdops/recordings:ro" "$QA_IMG" python -c "
import tempfile
from qa_pipeline.storage import LocalStorage
LocalStorage('/sdops/recordings').fetch('$KEY', tempfile.mkdtemp(), 50 * 1024 * 1024)
" >/dev/null 2>&1; then fail "uid $U sem o grupo leu a gravação"; fi
  echo "   uid $U: negado (ok)"
done

echo "SHARED_RECORDINGS_OK"
