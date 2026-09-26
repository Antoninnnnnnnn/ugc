from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    ugc_base: str
    catchall_domains: tuple[str, ...]
    imap_host: str
    imap_user: str
    imap_password: str
    captcha_provider: str
    captcha_api_key: str
    proxy_file: Path
    imap_timeout_sec: int
    runs_dir: Path
    use_proxy: bool = True
    use_imap: bool = True
    captcha_use_proxy: bool = False
    keep_dumps: bool = False
    friendly_sitekey: str = "FCMR306TFOLA6D49"

    @property
    def proxy_available(self) -> bool:
        return proxy_count(self.proxy_file) > 0

    @property
    def imap_available(self) -> bool:
        return bool(self.imap_user and self.imap_password)

    @property
    def proxy_source(self) -> Path | None:
        return self.proxy_file if self.use_proxy and self.proxy_available else None


def proxy_count(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    return sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))


def _mode(name: str, available: bool) -> bool:
    """auto (défaut) = actif si configuré ; 0 = désactivé ; 1 = actif si configuré."""
    raw = os.getenv(name, "auto").strip().lower()
    if raw in ("0", "false", "no", "off", "non"):
        return False
    return available


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    domains = tuple(
        d.strip().lower()
        for d in os.getenv("CATCHALL_DOMAINS", "").split(",")
        if d.strip()
    )
    proxy_path = Path(os.getenv("PROXY_FILE", "proxy.txt"))
    if not proxy_path.is_absolute():
        proxy_path = ROOT / proxy_path
    imap_user = os.getenv("IMAP_USER", "")
    imap_password = os.getenv("IMAP_APP_PASSWORD", "").replace(" ", "")
    return Settings(
        ugc_base=os.getenv("UGC_BASE", "https://www.ugc.fr").rstrip("/"),
        catchall_domains=domains,
        imap_host=os.getenv("IMAP_HOST", "imap.gmail.com"),
        imap_user=imap_user,
        imap_password=imap_password,
        captcha_provider=os.getenv("CAPTCHA_PROVIDER", "capmonster").lower(),
        captcha_api_key=os.getenv("CAPTCHA_API_KEY", ""),
        proxy_file=proxy_path,
        imap_timeout_sec=int(os.getenv("IMAP_TIMEOUT_SEC", "180")),
        runs_dir=ROOT / "runs",
        use_proxy=_mode("USE_PROXY", proxy_count(proxy_path) > 0),
        use_imap=_mode("USE_IMAP", bool(imap_user and imap_password)),
        captcha_use_proxy=os.getenv("CAPTCHA_USE_PROXY", "0").lower() in ("1", "true", "yes"),
        keep_dumps=os.getenv("KEEP_DUMPS", "0").lower() in ("1", "true", "yes"),
    )
