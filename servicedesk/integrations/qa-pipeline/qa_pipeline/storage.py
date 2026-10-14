"""Acesso às gravações por adapter. Padrão: volume local compartilhado com o sd-ops (somente leitura).

O qa-pipeline nunca baixa da 55PBX: quem baixa, valida e guarda é o sd-ops (A2), que publica
`recording.stored` com a `storage_key`. Aqui só lemos o objeto, conferimos tamanho e sha256 e
copiamos para um arquivo temporário (apagado ao fim do processamento).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from typing import Optional

from .config import Settings


class StorageError(RuntimeError):
    def __init__(self, message: str, code: str, permanent: bool = False):
        super().__init__(message)
        self.code = code
        self.permanent = permanent


class NotFound(StorageError):
    def __init__(self, key: str):
        super().__init__(f"objeto ainda não disponível: {key}", code="audio_not_found")


def _safe_key(key: str) -> str:
    key = (key or "").strip().lstrip("/")
    if not key or ".." in key.split("/") or "\\" in key or "\x00" in key:
        raise StorageError("storage_key inválida", code="bad_key", permanent=True)
    return key


class Storage:
    def fetch(self, key: str, dest_dir: str, max_bytes: int) -> str:  # pragma: no cover
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    def fetch(self, key: str, dest_dir: str, max_bytes: int) -> str:
        key = _safe_key(key)
        path = os.path.realpath(os.path.join(self.root, key))
        if not path.startswith(self.root + os.sep):
            raise StorageError("storage_key fora da raiz", code="bad_key", permanent=True)
        if not os.path.isfile(path):
            raise NotFound(key)
        size = os.path.getsize(path)
        if size == 0:
            raise StorageError("arquivo vazio", code="audio_empty", permanent=True)
        if size > max_bytes:
            raise StorageError(f"arquivo maior que o limite ({size} bytes)", code="audio_too_large", permanent=True)
        dst = os.path.join(dest_dir, os.path.basename(key))
        shutil.copyfile(path, dst)
        return dst


class S3Storage(Storage):
    """S3/MinIO. Requer `boto3` (não incluído na imagem padrão: pip install boto3)."""

    def __init__(self, s: Settings):
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise StorageError("boto3 não instalado para STORAGE_BACKEND=s3", code="config", permanent=True) from exc
        self.bucket = s.s3_bucket
        self.client = boto3.client("s3", endpoint_url=s.s3_endpoint or None, region_name=s.s3_region,
                                   aws_access_key_id=s.s3_access_key or None,
                                   aws_secret_access_key=s.s3_secret_key or None)

    def fetch(self, key: str, dest_dir: str, max_bytes: int) -> str:  # pragma: no cover (sem S3 no DEV)
        key = _safe_key(key)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise NotFound(key) from exc
            raise StorageError(f"S3 indisponível: {type(exc).__name__}", code="storage_unavailable") from exc
        if head["ContentLength"] > max_bytes:
            raise StorageError("arquivo maior que o limite", code="audio_too_large", permanent=True)
        dst = os.path.join(dest_dir, os.path.basename(key))
        self.client.download_file(self.bucket, key, dst)
        return dst


def build_storage(s: Settings) -> Storage:
    if s.storage_backend == "s3":
        return S3Storage(s)
    return LocalStorage(s.storage_local_root)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_mime(path: str) -> Optional[str]:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "audio/webm"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def tempdir() -> str:
    return tempfile.mkdtemp(prefix="qa-")
