from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import quote

_cache: dict[str, tuple[float, list[str]]] = {}
_cache_lock = threading.Lock()
_rr_idx = 0


def parse_proxy_line(line: str) -> str:
    """Convert http://host:port:user:pass into http://user:pass@host:port."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        raise ValueError("empty proxy line")
    scheme, rest = raw.split("://", 1)
    host, port, user, password = rest.split(":", 3)
    return (
        f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
    )


def load_proxies(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"proxy file missing: {path}")
    mtime = path.stat().st_mtime
    key = str(path.resolve())
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == mtime:
            return list(cached[1])

    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        out.append(parse_proxy_line(line))
    if not out:
        raise RuntimeError(f"no proxies in {path}")

    with _cache_lock:
        _cache[key] = (mtime, out)
    return list(out)


def pick_proxy(path: Path) -> str:
    proxies = load_proxies(path)
    global _rr_idx
    with _cache_lock:
        proxy = proxies[_rr_idx % len(proxies)]
        _rr_idx += 1
    return proxy
