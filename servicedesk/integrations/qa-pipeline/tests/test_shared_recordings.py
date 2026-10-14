"""Gravações do sd-ops lidas pelo qa-pipeline pelo volume compartilhado (INTEGRACAO-55PBX.md §17).

1. As duas imagens declaram o mesmo grupo "sdrec" (gid fixo): grupo principal do sd-ops (uid 10001) e suplementar
   do qa (uid 10002).
2. Com root (CI/containers de teste), processos reais com os uids/gids das imagens: o sd-ops grava com o storage
   DELE (sd_ops.storage.LocalStorage, modos 0640/0750) e o qa lê com o storage DELE (qa_pipeline.storage.LocalStorage);
   um uid de fora do grupo não lê e o qa não consegue apagar nem sobrescrever.
A prova com as imagens construídas e um volume Docker de verdade é `servicedesk/integrations/dev/shared_recordings_e2e.sh`.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

import pytest

from qa_pipeline.storage import LocalStorage

HERE = os.path.dirname(os.path.abspath(__file__))
INTEGRATIONS = os.path.dirname(os.path.dirname(HERE))
SDOPS_DIR = os.path.join(INTEGRATIONS, "pbx-bridge")
SDOPS_UID, QA_UID, OTHER_UID = 10001, 10002, 10003
KEY = "recordings/b2b/2026/10/14/call-42.mp3"
AUDIO = b"ID3" + b"\x00" * 2048


def _dockerfile(name: str) -> str:
    with open(os.path.join(INTEGRATIONS, name, "Dockerfile"), encoding="utf-8") as fh:
        return fh.read()


def _gid(text: str) -> int:
    return int(re.search(r"^ARG SDREC_GID=(\d+)$", text, re.M).group(1))


def test_both_images_share_the_same_fixed_group():
    sdops, qa = _dockerfile("pbx-bridge"), _dockerfile("qa-pipeline")
    assert _gid(sdops) == _gid(qa) == 10010
    for text in (sdops, qa):
        assert 'groupadd --gid "$SDREC_GID" sdrec' in text
    # sd-ops: grupo PRINCIPAL (arquivos novos já nascem no grupo); qa: membro (suplementar)
    assert re.search(r'useradd --uid 10001 --gid "\$SDREC_GID"', sdops)
    assert re.search(r"useradd --uid 10002 --groups sdrec", qa)
    assert "chown -R pbx:sdrec /data" in sdops and "chmod 750 /data/recordings" in sdops


def _run_as(uid: int, gid: int, groups: list, fn) -> int:
    """Roda fn() num processo filho com uid/gid/grupos dados; devolve o código de saída (0 = ok)."""
    pid = os.fork()
    if pid == 0:  # filho
        code = 1
        try:
            os.setgroups(groups)
            os.setgid(gid)
            os.setuid(uid)
            code = fn() or 0
        except BaseException as exc:  # noqa: BLE001
            sys.stderr.write(f"uid {uid}: {type(exc).__name__}: {exc}\n")
            code = 3 if isinstance(exc, PermissionError) else 2
        finally:
            os._exit(code)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


@pytest.mark.skipif(not hasattr(os, "fork") or os.geteuid() != 0, reason="precisa de root para trocar de uid")
def test_qa_reads_the_file_written_by_sdops(monkeypatch):
    sys.path.insert(0, SDOPS_DIR)
    try:
        from sd_ops.storage import LocalStorage as SdOpsStorage
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"sd_ops não importável: {exc}")
    gid = 10010
    root = tempfile.mkdtemp(prefix="sdrec-")
    os.chown(root, SDOPS_UID, gid)  # como o volume novo herda da imagem: pbx:sdrec
    os.chmod(root, 0o750)
    monkeypatch.setenv("SDOPS_STORAGE_FILE_MODE", "0640")
    monkeypatch.setenv("SDOPS_STORAGE_DIR_MODE", "0750")

    def write():
        os.umask(0o022)
        SdOpsStorage(root).put(KEY, AUDIO, "audio/mpeg")

    def read():
        dest = tempfile.mkdtemp()
        path = LocalStorage(root).fetch(KEY, dest, 10 * 1024 * 1024)
        with open(path, "rb") as fh:
            return 0 if fh.read() == AUDIO else 4

    def tamper():
        try:
            os.unlink(os.path.join(root, KEY))
        except PermissionError:
            pass
        else:
            return 5
        try:
            with open(os.path.join(root, KEY), "ab"):
                return 6
        except PermissionError:
            return 0

    # sd-ops: uid 10001, grupo principal sdrec (como na imagem)
    assert _run_as(SDOPS_UID, gid, [], write) == 0
    st = os.stat(os.path.join(root, KEY))
    assert (st.st_uid, st.st_gid, st.st_mode & 0o777) == (SDOPS_UID, gid, 0o640)
    # qa: uid 10002, grupo principal próprio + suplementar sdrec (como na imagem) -> lê
    assert _run_as(QA_UID, QA_UID, [gid], read) == 0
    # ... mas não apaga nem altera
    assert _run_as(QA_UID, QA_UID, [gid], tamper) == 0
    # controle: o mesmo uid do qa SEM o grupo comum não lê (era o problema do §15.4), nem outro uid qualquer
    assert _run_as(QA_UID, QA_UID, [], read) != 0
    assert _run_as(OTHER_UID, OTHER_UID, [], read) != 0
