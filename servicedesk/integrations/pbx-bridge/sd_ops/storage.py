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

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def _path(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root + os.sep):
            raise StorageError("chave fora do storage")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._path(key)
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".up-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o600)
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


def make_storage(s: OpsSettings):
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            raise StorageError("S3_BUCKET não configurado")
        return S3Storage(s)
    return LocalStorage(s.storage_dir)


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
