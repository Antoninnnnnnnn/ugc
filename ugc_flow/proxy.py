from __future__ import annotations

import random
from pathlib import Path
from urllib.parse import quote


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
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        out.append(parse_proxy_line(line))
    if not out:
        raise RuntimeError(f"no proxies in {path}")
    return out


def pick_proxy(path: Path) -> str:
    return random.choice(load_proxies(path))
