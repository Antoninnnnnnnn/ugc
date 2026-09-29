from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

FRIENDLY_SITEKEY = "FCMR306TFOLA6D49"
FRIENDLY_V2_LIB = "https://cdn.jsdelivr.net/npm/@friendlycaptcha/sdk@0.1.31/site.min.js"


class CaptchaError(RuntimeError):
    pass


# Un seul client pour tous les threads : pas de nouvelle poignée TLS à chaque interrogation.
_http = httpx.Client(
    timeout=30.0,
    limits=httpx.Limits(max_connections=400, max_keepalive_connections=100),
)
# Erreurs de charge côté fournisseur : on attend et on renvoie la tâche.
_BUSY = ("ERROR_NO_SLOT_AVAILABLE", "ERROR_TOO_MUCH_REQUESTS", "ERROR_MAXIMUM_TIME_EXCEED")


def _call(url: str, payload: dict) -> dict:
    for attempt in range(5):
        try:
            return _http.post(url, json=payload).json()
        except (httpx.TransportError, ValueError):
            if attempt == 4:
                raise
            time.sleep(1 + attempt)
    raise CaptchaError("fournisseur captcha injoignable")


def solve_friendly_captcha(
    provider: str,
    api_key: str,
    website_url: str,
    sitekey: str = FRIENDLY_SITEKEY,
    *,
    user_agent: str = "",
    proxy_url: str | None = None,
) -> str:
    if not api_key:
        raise CaptchaError("CAPTCHA_API_KEY manquante")
    if provider == "capmonster":
        return _capmonster(api_key, website_url, sitekey, user_agent, proxy_url)
    if provider == "capsolver":
        return _capsolver(api_key, website_url, sitekey)
    raise CaptchaError(f"CAPTCHA_PROVIDER inconnu: {provider}")


def get_balance(provider: str, api_key: str) -> float:
    url = {
        "capmonster": "https://api.capmonster.cloud/getBalance",
        "capsolver": "https://api.capsolver.com/getBalance",
    }.get(provider)
    if not url:
        raise CaptchaError(f"CAPTCHA_PROVIDER inconnu: {provider}")
    body = _call(url, {"clientKey": api_key})
    if body.get("errorId"):
        raise CaptchaError(f"{body.get('errorCode')}: {body.get('errorDescription')}")
    return float(body.get("balance") or 0)


def _capmonster(
    api_key: str, website_url: str, sitekey: str, user_agent: str, proxy_url: str | None
) -> str:
    task: dict = {
        "type": "CustomTask",
        "class": "friendly",
        "websiteURL": website_url,
        "websiteKey": sitekey,
        "metadata": {"apiGetLib": FRIENDLY_V2_LIB},
    }
    if user_agent:
        task["userAgent"] = user_agent
    if proxy_url:
        p = urlsplit(proxy_url)
        task.update(
            {
                "proxyType": p.scheme or "http",
                "proxyAddress": p.hostname,
                "proxyPort": p.port,
                "proxyLogin": p.username or "",
                "proxyPassword": p.password or "",
            }
        )
    last: CaptchaError | None = None
    for _ in range(3):
        try:
            task_id = _create("https://api.capmonster.cloud/createTask", api_key, task)
            sol = _poll("https://api.capmonster.cloud/getTaskResult", api_key, task_id)
        except CaptchaError as exc:
            if "UNSOLVABLE" not in str(exc):
                raise
            last = exc
            continue
        token = (sol.get("data") or {}).get("token") or sol.get("token")
        if token:
            return str(token)
        last = CaptchaError(f"solution CapMonster vide: {sol}")
    raise last or CaptchaError("CapMonster: échec")


def _capsolver(api_key: str, website_url: str, sitekey: str) -> str:
    task = {
        "type": "FriendlyCaptchaTaskProxyless",
        "websiteURL": website_url,
        "websiteKey": sitekey,
    }
    task_id = _create("https://api.capsolver.com/createTask", api_key, task)
    sol = _poll("https://api.capsolver.com/getTaskResult", api_key, task_id)
    token = sol.get("token")
    if not token:
        raise CaptchaError(f"solution CapSolver vide: {sol}")
    return str(token)


def _create(url: str, api_key: str, task: dict) -> str:
    for attempt in range(8):
        body = _call(url, {"clientKey": api_key, "task": task})
        code = str(body.get("errorCode") or "")
        if body.get("errorId") and code in _BUSY and attempt < 7:
            time.sleep(2 + attempt)
            continue
        if body.get("errorId"):
            raise CaptchaError(f"{code}: {body.get('errorDescription')}")
        task_id = body.get("taskId")
        if not task_id:
            raise CaptchaError(f"pas de taskId: {body}")
        return str(task_id)
    raise CaptchaError("fournisseur captcha saturé")


def _poll(url: str, api_key: str, task_id: str) -> dict:
    tid: int | str = int(task_id) if task_id.isdigit() else task_id
    time.sleep(4)
    for _ in range(90):
        body = _call(url, {"clientKey": api_key, "taskId": tid})
        code = str(body.get("errorCode") or "")
        if body.get("errorId") and code != "CAPTCHA_NOT_READY":
            raise CaptchaError(f"{code}: {body.get('errorDescription')}")
        if body.get("status") == "ready":
            return body.get("solution") or {}
        time.sleep(2)
    raise CaptchaError("timeout résolution Friendly Captcha")
