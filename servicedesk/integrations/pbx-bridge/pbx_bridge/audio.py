"""Download da gravação e conversão para MP3 mono (ffmpeg)."""
from __future__ import annotations

import fnmatch
import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx


class AudioError(Exception):
    def __init__(self, msg: str, permanent: bool = False):
        super().__init__(msg)
        self.permanent = permanent


def host_allowed(url: str, patterns: List[str]) -> bool:
    """Proteção contra SSRF: só baixa de hosts permitidos (padrão *.55pbx.com)."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    h = u.hostname.lower()
    for p in patterns:
        p = p.lower()
        if fnmatch.fnmatch(h, p) or (p.startswith("*.") and h == p[2:]):
            return True
    return False


def download(url: str, max_bytes: int, timeout: float = 120.0, headers: Optional[Dict[str, str]] = None,
             client: Optional[httpx.Client] = None) -> bytes:
    c = client or httpx.Client(timeout=timeout, follow_redirects=False)
    try:
        with c.stream("GET", url, headers=headers or {}) as r:
            if r.status_code in (404, 410):
                raise AudioError("gravação não encontrada (HTTP %d)" % r.status_code)
            if r.status_code in (401, 403):
                raise AudioError("gravação exige autenticação (HTTP %d)" % r.status_code, permanent=True)
            if r.status_code != 200:
                raise AudioError("HTTP %d ao baixar gravação" % r.status_code)
            cl = r.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                raise AudioError("gravação maior que o limite (%s bytes)" % cl, permanent=True)
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise AudioError("gravação maior que o limite", permanent=True)
            if not buf:
                raise AudioError("gravação vazia")
            return bytes(buf)
    except httpx.TransportError as e:
        raise AudioError("falha de rede ao baixar gravação: %s" % type(e).__name__)
    finally:
        if client is None:
            c.close()


def to_mp3(data: bytes, ffmpeg: str = "ffmpeg", bitrate: str = "32k", timeout: int = 300) -> bytes:
    with tempfile.TemporaryDirectory(prefix="pbxaudio-") as d:
        src = os.path.join(d, "in")
        dst = os.path.join(d, "out.mp3")
        with open(src, "wb") as f:
            f.write(data)
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", src,
               "-vn", "-ac", "1", "-ar", "16000", "-codec:a", "libmp3lame", "-b:a", bitrate, dst]
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except FileNotFoundError:
            raise AudioError("ffmpeg não encontrado (FFMPEG_BIN)", permanent=True)
        except subprocess.TimeoutExpired:
            raise AudioError("ffmpeg excedeu o tempo")
        if p.returncode != 0 or not os.path.exists(dst):
            raise AudioError("ffmpeg falhou: %s" % p.stderr.decode(errors="replace")[-300:], permanent=True)
        with open(dst, "rb") as f:
            return f.read()


def fetch_mp3(url: str, allowed: List[str], max_mb: int, ffmpeg: str, bitrate: str,
              headers: Optional[Dict[str, str]] = None) -> Tuple[bytes, int]:
    """Devolve (mp3, tamanho do original)."""
    if not host_allowed(url, allowed):
        raise AudioError("host da gravação fora de AUDIO_ALLOWED_HOSTS", permanent=True)
    raw = download(url, max_mb * 1024 * 1024, headers=headers)
    return to_mp3(raw, ffmpeg, bitrate), len(raw)


def mp3_name(call_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in call_id)
    return "ligacao-55pbx-%s.mp3" % safe
