from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from ugc_flow.proxy import pick_proxy

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


class UgcSession:
    def __init__(self, base: str, proxy_file: Path | None, dump_dir: Path) -> None:
        self.base = base.rstrip("/")
        self.dump_dir = dump_dir
        self.dump_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_file = proxy_file
        self._n = 0
        self.traffic: list[tuple[str, int, int]] = []
        self.last_join_location = ""
        self.referer = f"{self.base}/login.html"
        self.proxy = pick_proxy(proxy_file) if proxy_file else None
        self.client = self._open_client()

    def _open_client(self) -> httpx.Client:
        return httpx.Client(
            proxy=self.proxy,
            follow_redirects=True,
            timeout=httpx.Timeout(45.0, connect=20.0),
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
                "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )

    def _rotate_proxy(self) -> None:
        saved = [(c.name, c.value, c.domain, c.path) for c in self.client.cookies.jar]
        self.client.close()
        if self.proxy_file:
            self.proxy = pick_proxy(self.proxy_file)
        self.client = self._open_client()
        for name, value, domain, path in saved:
            self.client.cookies.set(name, value, domain=domain, path=path)

    def _send(self, call) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(5):
            try:
                response = call()
            except httpx.TransportError as exc:
                last = exc
                if attempt == 4 or not self.proxy_file:
                    raise
                self._rotate_proxy()
                continue
            if response.status_code in (502, 503) and attempt < 4 and self.proxy_file:
                self._rotate_proxy()
                continue
            return response
        if last:
            raise last
        raise RuntimeError("requête échouée")

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> UgcSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _account(self, name: str, r: httpx.Response) -> None:
        for resp in [*r.history, r]:
            body = int(resp.request.headers.get("content-length") or 0)
            sent = body + sum(len(k) + len(v) + 4 for k, v in resp.request.headers.raw)
            recv = resp.num_bytes_downloaded + sum(len(k) + len(v) + 4 for k, v in resp.headers.raw)
            self.traffic.append((f"{name} {resp.status_code} {resp.headers.get('content-encoding', '-')}", sent, recv))

    @property
    def traffic_bytes(self) -> int:
        return sum(s + r for _, s, r in self.traffic)

    def dump(self, name: str, content: str | bytes, suffix: str = ".html") -> Path:
        self._n += 1
        path = self.dump_dir / f"{self._n:02d}-{name}{suffix}"
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def location(r: httpx.Response) -> str:
        return str(r.url.join(r.headers["location"])) if r.is_redirect else ""

    def url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base + path

    def get(self, path: str, name: str, *, follow: bool = True) -> httpx.Response:
        def call() -> httpx.Response:
            return self.client.get(self.url(path), headers={"Referer": self.referer}, follow_redirects=follow)

        r = self._send(call)
        if r.status_code == 403 and self.proxy_file:
            self._rotate_proxy()
            r = self._send(call)
        self._account(name, r)
        self.referer = str(r.url)
        self.dump(name, r.text)
        return r

    def post(
        self,
        path: str,
        name: str,
        data: dict[str, Any],
        *,
        ajax: bool = False,
        follow: bool = True,
    ) -> httpx.Response:
        target = httpx.URL(self.url(path))
        headers = {
            "Origin": f"{target.scheme}://{target.host}",
            "Referer": self.referer,
            "Content-Type": "application/x-www-form-urlencoded",
            "Sec-Fetch-Site": "same-origin" if target.host == httpx.URL(self.referer).host else "same-site",
        }
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "text/html, */*; q=0.01"
            headers["Sec-Fetch-Dest"] = "empty"
            headers["Sec-Fetch-Mode"] = "cors"
        else:
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-User"] = "?1"
        def call() -> httpx.Response:
            return self.client.post(target, data=data, headers=headers, follow_redirects=follow)

        r = self._send(call)
        self._account(name, r)
        self.referer = str(r.url)
        self.dump(name, r.text)
        safe = {str(k): ("***" if any(x in str(k).lower() for x in ("pass", "mdp", "captcha")) else str(v)) for k, v in data.items()}
        self.dump(name + "-post", json.dumps(safe, ensure_ascii=False, indent=2), suffix=".json")
        return r
