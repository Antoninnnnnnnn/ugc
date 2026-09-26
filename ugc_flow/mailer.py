from __future__ import annotations

import email as email_lib
import imaplib
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from urllib.parse import parse_qs, urlsplit

from ugc_flow.profile import gmail_base


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _body(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                chunks.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_charset() or "utf-8"
        chunks.append(payload.decode(str(charset), errors="replace"))
    return "\n".join(chunks)


def extract_ugc_links(text: str) -> list[str]:
    raw = re.findall(r"https://www\.ugc\.fr/[^\s\"'<>\]\[]+", text, re.I)
    return list(dict.fromkeys(u.rstrip(").,;").replace("&amp;", "&") for u in raw))


def activation_link(text: str) -> str | None:
    return next((u for u in extract_ugc_links(text) if "activationMonCompte" in u), None)


def check_pasted_link(raw: str, email: str) -> tuple[str | None, str]:
    """Valide un lien d'activation collé à la main. Renvoie (url, "") ou (None, raison)."""
    url = raw.strip().strip("<>[]\"' ").replace("&amp;", "&")
    if not re.match(r"https?://", url, re.I):
        return None, "ce n'est pas une URL"
    host = urlsplit(url).hostname or ""
    if host.endswith("mjt.lu"):
        return url, ""
    if host != "www.ugc.fr" or "activationMonCompte" not in url:
        return None, "ce n'est pas le lien d'activation UGC (bouton du mail « Confirmez votre inscription »)"
    got = (parse_qs(urlsplit(url).query).get("emailCompte") or [""])[0].lower()
    if got and got != email.lower():
        return None, f"ce lien est pour {got}, pas pour {email}"
    return url, ""


def check_login(host: str, user: str, password: str) -> None:
    mail = imaplib.IMAP4_SSL(host)
    try:
        mail.login(user, password)
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def recent_headers(host: str, user: str, password: str, needle: str = "", days: int = 1) -> list[str]:
    mail = imaplib.IMAP4_SSL(host)
    try:
        mail.login(user, password)
        mail.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = mail.search(None, f"(SINCE {since})")
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        lines: list[str] = []
        for uid in ids[-80:]:
            typ, fetched = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            raw = fetched[0][1] if typ == "OK" and fetched and fetched[0] else b""
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email_lib.message_from_bytes(raw)
            parts = [str(make_header(decode_header(msg.get(h, "")))) for h in ("Date", "From", "To", "Subject")]
            line = " | ".join(parts)
            if not needle or needle.lower() in line.lower():
                lines.append(line)
        return lines
    finally:
        try:
            mail.logout()
        except Exception:
            pass


class MailWatcher:
    def __init__(self, host: str, user: str, password: str, target_email: str, timeout_sec: int) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.target_email = target_email.lower()
        self.timeout_sec = timeout_sec
        self._stop = threading.Event()
        self.link: str | None = None
        self.error: str | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def wait_link(self) -> str | None:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            if self.link:
                return self.link
            if self.error:
                raise RuntimeError(self.error)
            time.sleep(2)
        return None

    def _same_box(self, text: str) -> bool:
        want = gmail_base(self.target_email)
        found = re.findall(r"[\w.+-]+@[\w.-]+", text.lower())
        return any(gmail_base(addr) == want for addr in found)

    def _matches(self, msg: Message) -> bool:
        headers = " ".join(
            _decode(msg.get(h)) for h in ("To", "Delivered-To", "X-Original-To", "Cc")
        )
        return self._same_box(headers)

    def _run(self) -> None:
        try:
            seen: set[bytes] = set()
            while not self._stop.is_set():
                mail = imaplib.IMAP4_SSL(self.host)
                try:
                    mail.login(self.user, self.password)
                    mail.select("INBOX")
                    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d-%b-%Y")
                    typ, data = mail.search(None, f"(SINCE {since})")
                    if typ != "OK" or not data or not data[0]:
                        time.sleep(5)
                        continue
                    ids = data[0].split()[-40:]
                    for uid in reversed(ids):
                        if uid in seen:
                            continue
                        typ, fetched = mail.fetch(uid, "(RFC822)")
                        if typ != "OK" or not fetched or not fetched[0]:
                            continue
                        raw = fetched[0][1]
                        if not isinstance(raw, (bytes, bytearray)):
                            continue
                        msg = email_lib.message_from_bytes(raw)
                        seen.add(uid)
                        body = _body(msg)
                        subj = str(msg.get("Subject") or "")
                        hay = body + " " + subj
                        if not self._matches(msg) and not self._same_box(hay):
                            continue
                        picked = activation_link(hay)
                        if picked:
                            self.link = picked
                            return
                finally:
                    try:
                        mail.logout()
                    except Exception:
                        pass
                time.sleep(8)
        except Exception as exc:
            self.error = str(exc)
