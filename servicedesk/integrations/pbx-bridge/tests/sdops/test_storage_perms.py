"""Storage local das gravações: modos configuráveis e grupo comum com o qa-pipeline (INTEGRACAO-55PBX.md §17)."""
from __future__ import annotations

import json
import os
import stat

from sd_ops.__main__ import main
from sd_ops.storage import LocalStorage

KEY = "recordings/b2b/2026/10/14/call-1.mp3"


def _mode(path: str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_default_modes_stay_private(tmp_path, monkeypatch):
    monkeypatch.delenv("SDOPS_STORAGE_FILE_MODE", raising=False)
    monkeypatch.delenv("SDOPS_STORAGE_DIR_MODE", raising=False)
    st = LocalStorage(str(tmp_path / "rec"))
    st.put(KEY, b"audio", "audio/mpeg")
    path = tmp_path / "rec" / KEY
    assert _mode(str(path)) == 0o600
    assert _mode(str(path.parent)) == 0o700
    assert _mode(str(tmp_path / "rec")) == 0o700


def test_shared_modes_apply_to_every_new_directory_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SDOPS_STORAGE_FILE_MODE", "0640")
    monkeypatch.setenv("SDOPS_STORAGE_DIR_MODE", "0750")
    old_umask = os.umask(0o077)  # nem um umask restritivo tira a leitura do grupo
    try:
        st = LocalStorage(str(tmp_path / "rec"))
        st.put(KEY, b"audio", "audio/mpeg")
    finally:
        os.umask(old_umask)
    path = tmp_path / "rec" / KEY
    assert _mode(str(path)) == 0o640
    for d in [path.parent, path.parent.parent, path.parent.parent.parent, tmp_path / "rec" / "recordings", tmp_path / "rec"]:
        assert _mode(str(d)) == 0o750, d
    assert st.get(KEY) == b"audio"
    assert not [n for n in os.listdir(path.parent) if n.startswith(".up-")]


def test_group_is_forced_when_configured(tmp_path, monkeypatch):
    gid = os.getgid()  # o próprio grupo: chown permitido sem root
    monkeypatch.setenv("SDOPS_STORAGE_GID", str(gid))
    st = LocalStorage(str(tmp_path / "rec"), file_mode=0o640, dir_mode=0o750)
    st.put(KEY, b"x", "audio/mpeg")
    assert os.stat(tmp_path / "rec" / KEY).st_gid == gid
    assert st.gid == gid


def test_fix_permissions_migrates_old_private_recordings(tmp_path, monkeypatch, capsys):
    old = LocalStorage(str(tmp_path / "rec"), file_mode=0o600, dir_mode=0o700)
    old.put(KEY, b"antigo", "audio/mpeg")
    old.put("recordings/b2b/2026/10/13/call-0.mp3", b"antigo", "audio/mpeg")

    monkeypatch.setenv("SDOPS_STORAGE_DIR", str(tmp_path / "rec"))
    monkeypatch.setenv("SDOPS_STORAGE_FILE_MODE", "0640")
    monkeypatch.setenv("SDOPS_STORAGE_DIR_MODE", "0750")
    assert main(["storage-fix-perms"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["files"] == 2 and out["skipped"] == 0 and out["file_mode"] == "0o640"
    assert _mode(str(tmp_path / "rec" / KEY)) == 0o640
    assert _mode(str((tmp_path / "rec" / KEY).parent)) == 0o750
    # idempotente
    assert main(["storage-fix-perms"]) == 0
