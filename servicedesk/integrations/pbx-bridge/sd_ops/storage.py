"""Storage privado das gravações: adapter S3-compatível. Padrão = volume local; MinIO/S3 opcional por env."""
from __future__ import annotations

import os
import tempfile
from typing import Iterator, Optional, Tuple

from .config import OpsSettings


class StorageError(Exception):
    pass


class LocalStorage:
    backend = "local"

    def __init__(self, root: str, file_mode: Optional[int] = None, dir_mode: Optional[int] = None):
        # Padrão 0600/0700 (só o sd-ops). Para o qa-pipeline (outro uid) ler pelo mesmo volume: grupo comum +
        # SDOPS_STORAGE_FILE_MODE=0640 e SDOPS_STORAGE_DIR_MODE=0750 (ver INTEGRACAO-55PBX.md, painel admin).
        self.file_mode = file_mode if file_mode is not None else int(os.environ.get("SDOPS_STORAGE_FILE_MODE") or "0600", 8)
        self.dir_mode = dir_mode if dir_mode is not None else int(os.environ.get("SDOPS_STORAGE_DIR_MODE") or "0700", 8)
        self.root = os.path.abspath(root)
        os.makedirs(self.root, mode=self.dir_mode, exist_ok=True)
        try:
            os.chmod(self.root, self.dir_mode)
        except OSError:
            pass

    def _path(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root + os.sep):
            raise StorageError("chave fora do storage")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._path(key)
        os.makedirs(os.path.dirname(p), mode=self.dir_mode, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".up-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, self.file_mode)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def size(self, key: str) -> int:
        return os.path.getsize(self._path(key))

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def iter_range(self, key: str, start: int = 0, end: Optional[int] = None, chunk: int = 65536) -> Iterator[bytes]:
        with open(self._path(key), "rb") as f:
            f.seek(start)
            remaining = None if end is None else end - start + 1
            while remaining is None or remaining > 0:
                b = f.read(chunk if remaining is None else min(chunk, remaining))
                if not b:
                    break
                if remaining is not None:
                    remaining -= len(b)
                yield b

    def delete(self, key: str) -> None:
        try:
            os.unlink(self._path(key))
        except FileNotFoundError:
            pass

    def ping(self) -> bool:
        return os.access(self.root, os.W_OK)


class S3Storage:
    backend = "s3"

    def __init__(self, s: OpsSettings):
        import boto3  # dependência opcional, só quando usada
        from botocore.config import Config
        self.bucket = s.s3_bucket
        self.c = boto3.client("s3", endpoint_url=s.s3_endpoint_url or None, region_name=s.s3_region,
                              aws_access_key_id=s.s3_access_key_id or None,
                              aws_secret_access_key=s.s3_secret_access_key or None,
                              config=Config(signature_version="s3v4", retries={"max_attempts": 3}))

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.c.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime, ServerSideEncryption="AES256")

    def size(self, key: str) -> int:
        return int(self.c.head_object(Bucket=self.bucket, Key=key)["ContentLength"])

    def get(self, key: str) -> bytes:
        return self.c.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def iter_range(self, key: str, start: int = 0, end: Optional[int] = None, chunk: int = 65536) -> Iterator[bytes]:
        rng = "bytes=%d-%s" % (start, "" if end is None else end)
        body = self.c.get_object(Bucket=self.bucket, Key=key, Range=rng)["Body"]
        for b in body.iter_chunks(chunk):
            yield b

    def delete(self, key: str) -> None:
        self.c.delete_object(Bucket=self.bucket, Key=key)

    def ping(self) -> bool:
        self.c.head_bucket(Bucket=self.bucket)
        return True


def _make_storage(s: OpsSettings):
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            raise StorageError("S3_BUCKET não configurado")
        return S3Storage(s)
    return LocalStorage(s.storage_dir)


class StorageRouter:
    """Storage por tenant conforme a configuração em vigor (tela > ambiente), sem reiniciar.

    A chave das gravações começa com recordings/<tenant>/..., então o tenant sai da própria chave. Leitura: tenta o
    backend configurado agora e, se o arquivo não estiver lá (ex. trocou de local para S3), cai no volume local,
    onde ficam as gravações antigas. A escrita vai sempre para o backend em vigor."""

    def __init__(self, s: OpsSettings, settings=None):
        self.s, self.settings = s, settings
        self.local = LocalStorage(s.storage_dir)
        self._s3 = {}

    @property
    def backend(self) -> str:
        return self.s.storage_backend

    def _cfg(self, tenant_id: Optional[str]) -> OpsSettings:
        if self.settings is None or not tenant_id:
            return self.s
        return self.settings.effective(tenant_id)

    def for_settings(self, cfg: OpsSettings):
        if cfg.storage_backend != "s3":
            return self.local
        if not cfg.s3_bucket:
            raise StorageError("S3_BUCKET não configurado")
        k = (cfg.s3_endpoint_url, cfg.s3_bucket, cfg.s3_region, cfg.s3_access_key_id, cfg.s3_secret_access_key)
        st = self._s3.get(k)
        if st is None:
            st = self._s3[k] = S3Storage(cfg)
        return st

    @staticmethod
    def _tenant(key: str) -> Optional[str]:
        parts = key.split("/")
        return parts[1] if len(parts) > 2 and parts[0] == "recordings" else None

    def _for(self, key: str):
        return self.for_settings(self._cfg(self._tenant(key)))

    def backend_for(self, key: str) -> str:
        return self._for(key).backend

    def put(self, key: str, data: bytes, mime: str) -> None:
        self._for(key).put(key, data, mime)

    def _read(self, key: str, fn: str, *a, **kw):
        st = self._for(key)
        try:
            return getattr(st, fn)(key, *a, **kw)
        except Exception:  # noqa: BLE001 - arquivo antigo no volume local
            if st is self.local:
                raise
            return getattr(self.local, fn)(key, *a, **kw)

    def size(self, key: str) -> int:
        return self._read(key, "size")

    def get(self, key: str) -> bytes:
        return self._read(key, "get")

    def iter_range(self, key: str, start: int = 0, end: Optional[int] = None, chunk: int = 65536) -> Iterator[bytes]:
        st = self._for(key)
        if st is not self.local:
            try:
                st.size(key)
            except Exception:  # noqa: BLE001
                st = self.local
        return st.iter_range(key, start, end, chunk)

    def delete(self, key: str) -> None:
        self._for(key).delete(key)

    def ping(self) -> bool:
        return self.for_settings(self.s).ping()


def make_storage(s: OpsSettings, settings=None):
    """Com o provider de configuração: roteador por tenant (tela > ambiente). Sem: comportamento original."""
    if settings is not None:
        if s.storage_backend == "s3" and not s.s3_bucket:
            raise StorageError("S3_BUCKET não configurado")
        return StorageRouter(s, settings)
    return _make_storage(s)


def parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    """'bytes=100-' -> (100, size-1). Só um intervalo."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    a, _, b = spec.partition("-")
    try:
        if a == "":
            n = int(b)
            return max(0, size - n), size - 1
        start = int(a)
        end = int(b) if b else size - 1
    except ValueError:
        return None
    if start >= size or start > end:
        return None
    return start, min(end, size - 1)
