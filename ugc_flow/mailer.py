from __future__ import annotations

import email as email_lib
import imaplib
import os
import poplib
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.header import decode_header, make_header
from email.message import Message
from urllib.parse import parse_qs, urlsplit

from ugc_flow.profile import gmail_base

# hôte IMAP, hôte POP3. Le port est 993 ou 995.
PRESETS: dict[str, tuple[str, str]] = {
    "gmail.com": ("imap.gmail.com", "pop.gmail.com"),
    "googlemail.com": ("imap.gmail.com", "pop.gmail.com"),
    "outlook.com": ("outlook.office365.com", "outlook.office365.com"),
    "outlook.fr": ("outlook.office365.com", "outlook.office365.com"),
    "hotmail.com": ("outlook.office365.com", "outlook.office365.com"),
    "hotmail.fr": ("outlook.office365.com", "outlook.office365.com"),
    "live.com": ("outlook.office365.com", "outlook.office365.com"),
    "live.fr": ("outlook.office365.com", "outlook.office365.com"),
    "msn.com": ("outlook.office365.com", "outlook.office365.com"),
    "yahoo.com": ("imap.mail.yahoo.com", "pop.mail.yahoo.com"),
    "yahoo.fr": ("imap.mail.yahoo.com", "pop.mail.yahoo.com"),
    "icloud.com": ("imap.mail.me.com", "imap.mail.me.com"),
    "me.com": ("imap.mail.me.com", "imap.mail.me.com"),
    "gmx.fr": ("imap.gmx.com", "pop.gmx.com"),
    "gmx.com": ("imap.gmx.com", "pop.gmx.com"),
    "orange.fr": ("imap.orange.fr", "pop.orange.fr"),
    "wanadoo.fr": ("imap.orange.fr", "pop.orange.fr"),
    "free.fr": ("imap.free.fr", "pop.free.fr"),
    "laposte.net": ("imap.laposte.net", "pop.laposte.net"),
    "sfr.fr": ("imap.sfr.fr", "pop.sfr.fr"),
    "numericable.fr": ("imap.sfr.fr", "pop.sfr.fr"),
}


def resolve_host(user: str, protocol: str, host_override: str = "") -> tuple[str, int]:
    """Hôte et port SSL. `host_override` gagne sur le preset du domaine."""
    port = 995 if protocol == "pop3" else 993
    if host_override:
        return host_override, port
    domain = user.lower().rsplit("@", 1)[-1]
    preset = PRESETS.get(domain)
    if not preset:
        raise ValueError(f"hôte inconnu pour @{domain} — renseigne MAIL_HOST")
    return preset[1 if protocol == "pop3" else 0], port


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
    """Valide un lien d'activation saisi manuellement. Renvoie (url, "") ou (None, raison)."""
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


def _header_line(msg: Message) -> str:
    parts = [str(make_header(decode_header(msg.get(h, "")))) for h in ("Date", "From", "To", "Subject")]
    return " | ".join(parts)


def _same_box(target: str, text: str) -> bool:
    want = gmail_base(target)
    found = re.findall(r"[\w.+-]+@[\w.-]+", text.lower())
    return any(gmail_base(addr) == want for addr in found)


def _address_headers(msg: Message) -> str:
    return " ".join(_decode(msg.get(h)) for h in ("To", "Delivered-To", "X-Original-To", "Cc"))


def _worth_opening(target: str, msg: Message) -> bool:
    """Vrai si les en-têtes peuvent être le mail d'activation. Évite de télécharger le corps sinon."""
    subject = str(msg.get("Subject") or "").lower()
    if _same_box(target, _address_headers(msg)):
        return True
    return "ugc" in subject or "inscription" in subject


def _link_from(target: str, msg: Message) -> str | None:
    headers = _address_headers(msg)
    hay = _body(msg) + " " + str(msg.get("Subject") or "")
    if not _same_box(target, headers) and not _same_box(target, hay):
        return None
    return activation_link(hay)


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, imaplib.IMAP4.abort):
        return False
    if not isinstance(exc, (imaplib.IMAP4.error, poplib.error_proto)):
        return False
    text = str(exc).lower()
    return any(hint in text for hint in ("auth", "login", "credential", "password", "mot de passe", "identifiant"))


def _uid_bodies(fetched) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for item in fetched or []:
        if not isinstance(item, tuple) or len(item) < 2 or not isinstance(item[1], (bytes, bytearray)):
            continue
        meta = item[0].decode("ascii", errors="replace") if isinstance(item[0], bytes) else str(item[0])
        found = re.search(r"UID (\d+)", meta)
        if found:
            out.append((found.group(1), bytes(item[1])))
    return out


def _highest_uid(fetched) -> int:
    best = 0
    for item in fetched or []:
        meta = item[0] if isinstance(item, tuple) else item
        if isinstance(meta, bytes):
            meta = meta.decode("ascii", errors="replace")
        if not isinstance(meta, str):
            continue
        found = re.search(r"UID (\d+)", meta)
        if found:
            best = max(best, int(found.group(1)))
    return best


def _is_ugc_header(msg: Message) -> bool:
    sender = _decode(msg.get("From")).lower()
    try:
        subject = str(make_header(decode_header(_decode(msg.get("Subject"))))).lower()
    except Exception:
        subject = _decode(msg.get("Subject")).lower()
    return "ugcmailing" in sender or "confirmez" in subject or "mon compte" in subject


def _imap_literals(fetched) -> list[bytes]:
    out: list[bytes] = []
    for item in fetched or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
            out.append(bytes(item[1]))
    return out


def activation_target(msg: Message) -> tuple[str, str] | None:
    """(adresse, lien) si le message contient le lien d'activation UGC."""
    link = activation_link(_body(msg) + " " + str(msg.get("Subject") or ""))
    if not link:
        return None
    target = (parse_qs(urlsplit(link).query).get("emailCompte") or [""])[0].lower()
    if not target:
        return None
    return target, link


def load_activation_links(host: str, user: str, password: str, wanted: set[str], progress=None) -> dict[str, str]:
    """Lit d'un coup les mails UGC déjà reçus. Une recherche, puis des téléchargements groupés."""
    note = progress or (lambda _m: None)
    links: dict[str, str] = {}
    note("connexion IMAP")
    mail = _login_imap(host, user, password)
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%d-%b-%Y")
        for folder in ("INBOX", "[Gmail]/Spam", "[Gmail]/Tous les messages"):
            if wanted and wanted <= {addr for addr, link in links.items() if "relance-activation" not in link}:
                break
            try:
                typ, _ = mail.select(folder, readonly=True)
            except imaplib.IMAP4.error:
                continue
            if typ != "OK":
                continue
            note(f"recherche dans {folder}")
            typ, data = mail.uid("SEARCH", f'(SINCE {since} FROM "ugcmailing.fr" SUBJECT "Confirmez")')
            if typ != "OK" or not data or not data[0]:
                typ, data = mail.uid("SEARCH", f'(SINCE {since} FROM "ugcmailing.fr")')
            if typ != "OK" or not data or not data[0]:
                note(f"rien dans {folder}")
                continue
            uids = [u.decode() if isinstance(u, bytes) else str(u) for u in data[0].split()]
            uids.reverse()
            note(f"{len(uids)} mails dans {folder}")
            for i in range(0, len(uids), 12):
                if wanted and wanted <= {addr for addr, link in links.items() if "relance-activation" not in link}:
                    break
                chunk = ",".join(uids[i : i + 12])
                typ, fetched = mail.uid("FETCH", chunk, "(BODY.PEEK[])")
                if typ != "OK":
                    continue
                for raw in _imap_literals(fetched):
                    found = activation_target(email_lib.message_from_bytes(raw))
                    if not found:
                        continue
                    addr, link = found
                    previous = links.get(addr)
                    if previous is None or ("relance-activation" in previous and "relance-activation" not in link):
                        links[addr] = link
                ready = {addr for addr, link in links.items() if "relance-activation" not in link}
                note(f"{len(ready)} liens d'origine")
                if wanted and wanted <= ready:
                    break
        return links
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def _imap_literal(fetched) -> bytes:
    if not fetched or not fetched[0] or not isinstance(fetched[0], tuple):
        return b""
    raw = fetched[0][1]
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else b""


def pop_candidates(lines: list[bytes] | None, seen: set[str], limit: int = 40) -> list[tuple[int, str]]:
    """Derniers messages POP dont l'identifiant UIDL n'a pas déjà été lu."""
    pairs: list[tuple[int, str]] = []
    for line in lines or []:
        text = line.decode("ascii", errors="replace").strip()
        if not text:
            continue
        num, uid = text.split(None, 1)
        pairs.append((int(num), uid))
    pending = [(num, uid) for num, uid in pairs if uid not in seen]
    return pending[-limit:]


# Comptes personnels Microsoft : IMAP n'accepte plus le mot de passe, seulement XOAUTH2.
MICROSOFT_DOMAINS = frozenset(k for k, v in PRESETS.items() if v[0] == "outlook.office365.com")
MICROSOFT_HOSTS = frozenset({"outlook.office365.com", "imap-mail.outlook.com"})
OUTLOOK_SCOPE = ["https://outlook.office.com/IMAP.AccessAsUser.All"]
OUTLOOK_AUTHORITY = "https://login.microsoftonline.com/consumers"
_OUTLOOK_TOKEN = Path(__file__).resolve().parent.parent / ".outlook-token.json"
_outlook_lock = threading.Lock()


def uses_xoauth2(host: str, user: str) -> bool:
    domain = user.lower().rsplit("@", 1)[-1] if "@" in user else ""
    return domain in MICROSOFT_DOMAINS or host.lower() in MICROSOFT_HOSTS


def xoauth2_string(user: str, token: str) -> bytes:
    return f"user={user}\x01auth=Bearer {token}\x01\x01".encode("utf-8")


def _outlook_authority(user: str) -> str:
    domain = user.lower().rsplit("@", 1)[-1] if "@" in user else ""
    if domain in MICROSOFT_DOMAINS:
        return OUTLOOK_AUTHORITY
    return "https://login.microsoftonline.com/common"


def outlook_access_token(user: str, *, interactive: bool) -> str:
    """Jeton IMAP Outlook. Le premier appel affiche un code à saisir sur microsoft.com/devicelogin."""
    client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
    if not client_id:
        raise RuntimeError(
            "Outlook exige OAuth. Ajoute OUTLOOK_CLIENT_ID dans .env "
            "(application Entra, comptes personnels, flux public autorisé)."
        )
    try:
        import msal
    except ImportError as exc:
        raise RuntimeError("module msal manquant — pip install -r requirements.txt") from exc

    with _outlook_lock:
        cache = msal.SerializableTokenCache()
        if _OUTLOOK_TOKEN.exists():
            cache.deserialize(_OUTLOOK_TOKEN.read_text(encoding="utf-8"))
        authority = os.getenv("OUTLOOK_AUTHORITY", "").strip() or _outlook_authority(user)
        app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)
        accounts = app.get_accounts()
        wanted = user.lower()
        match = [a for a in accounts if str(a.get("username") or "").lower() == wanted]
        account = match[0] if match else (accounts[0] if len(accounts) == 1 else None)
        result = app.acquire_token_silent(OUTLOOK_SCOPE, account=account) if account else None
        if not result or "access_token" not in result:
            if not interactive:
                raise RuntimeError("session Outlook expirée — relance le script pour reconnecter la boîte")
            flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPE)
            if "user_code" not in flow:
                raise RuntimeError(flow.get("error_description") or "flux Outlook impossible")
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)
        if cache.has_state_changed:
            _OUTLOOK_TOKEN.write_text(cache.serialize(), encoding="utf-8")
        if not result or "access_token" not in result:
            detail = (result or {}).get("error_description") or "OAuth Outlook échoué"
            raise RuntimeError(detail)
        return result["access_token"]


def prepare_imap(host: str, user: str) -> None:
    """Connexion Outlook sur le fil principal, avant les workers."""
    if uses_xoauth2(host, user):
        outlook_access_token(user, interactive=True)


def _login_imap(host: str, user: str, password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(host, timeout=60)
    if uses_xoauth2(host, user):
        token = outlook_access_token(user, interactive=True)
        mail.authenticate("XOAUTH2", lambda _challenge: xoauth2_string(user, token))
    else:
        mail.login(user, password)
    return mail


def _login_pop(host: str, user: str, password: str) -> poplib.POP3_SSL:
    if uses_xoauth2(host, user):
        raise RuntimeError("Outlook n'accepte plus POP3 par mot de passe. Utilise IMAP.")
    mail = poplib.POP3_SSL(host, timeout=30)
    mail.user(user)
    mail.pass_(password)
    return mail


def check_login(protocol: str, host: str, user: str, password: str) -> None:
    if protocol == "pop3":
        mail = _login_pop(host, user, password)
        try:
            mail.quit()
        except Exception:
            pass
        return
    mail = _login_imap(host, user, password)
    try:
        mail.logout()
    except Exception:
        pass


def recent_headers(protocol: str, host: str, user: str, password: str, needle: str = "") -> list[str]:
    lines: list[str] = []
    if protocol == "pop3":
        mail = _login_pop(host, user, password)
        try:
            count = len(mail.list()[1])
            for num in range(max(1, count - 39), count + 1):
                raw = b"\n".join(mail.top(num, 0)[1])
                msg = email_lib.message_from_bytes(raw)
                line = _header_line(msg)
                if not needle or needle.lower() in line.lower():
                    lines.append(line)
        finally:
            try:
                mail.quit()
            except Exception:
                pass
        return lines
    mail = _login_imap(host, user, password)
    try:
        mail.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d-%b-%Y")
        typ, data = mail.search(None, f"(SINCE {since})")
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        for uid in ids[-80:]:
            typ, fetched = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            raw = fetched[0][1] if typ == "OK" and fetched and fetched[0] else b""
            if not isinstance(raw, (bytes, bytearray)):
                continue
            line = _header_line(email_lib.message_from_bytes(raw))
            if not needle or needle.lower() in line.lower():
                lines.append(line)
        return lines
    finally:
        try:
            mail.logout()
        except Exception:
            pass


class Mailbox:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def wait_link(self) -> str | None:
        raise NotImplementedError


class _PollingMailbox(Mailbox):
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        target_email: str,
        timeout_sec: int,
        pause_sec: float = 8,
    ) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.target_email = target_email.lower()
        self.timeout_sec = timeout_sec
        self.pause_sec = pause_sec
        self._stop = threading.Event()
        self.link: str | None = None
        self.error: str | None = None
        self.last_error: str | None = None
        self.ok_polls = 0
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
            if self._stop.wait(0.2):
                break
        if self.link:
            return self.link
        if self.ok_polls == 0 and self.last_error:
            raise RuntimeError(self.last_error)
        return None

    def _fetch(self, seen: set[str]) -> list[tuple[str, Message]]:
        raise NotImplementedError

    def _run(self) -> None:
        seen: set[str] = set()
        while not self._stop.is_set():
            try:
                found = self._fetch(seen)
                self.ok_polls += 1
                self.last_error = None
                for mid, msg in found:
                    seen.add(mid)
                    picked = _link_from(self.target_email, msg)
                    if picked:
                        self.link = picked
                        return
            except Exception as exc:
                if _is_auth_failure(exc):
                    self.error = str(exc)
                    return
                self.last_error = str(exc)
            self._stop.wait(self.pause_sec)


class ImapMailbox(_PollingMailbox):
    def _fetch(self, seen: set[str]) -> list[tuple[str, Message]]:
        out: list[tuple[str, Message]] = []
        mail = _login_imap(self.host, self.user, self.password)
        try:
            mail.select("INBOX", readonly=True)
            since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d-%b-%Y")
            typ, data = mail.uid("SEARCH", f"(SINCE {since})")
            if typ != "OK" or not data or not data[0]:
                return out
            for uid in data[0].split()[-40:]:
                key = uid.decode() if isinstance(uid, bytes) else str(uid)
                if key in seen:
                    continue
                typ, fetched = mail.uid(
                    "FETCH", key, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DELIVERED-TO X-ORIGINAL-TO CC)])"
                )
                header = email_lib.message_from_bytes(_imap_literal(fetched))
                if not _worth_opening(self.target_email, header):
                    out.append((key, header))
                    continue
                typ, fetched = mail.uid("FETCH", key, "(BODY.PEEK[])")
                raw = _imap_literal(fetched)
                if raw:
                    out.append((key, email_lib.message_from_bytes(raw)))
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        return out


class Pop3Mailbox(_PollingMailbox):
    def _fetch(self, seen: set[str]) -> list[tuple[str, Message]]:
        out: list[tuple[str, Message]] = []
        mail = _login_pop(self.host, self.user, self.password)
        try:
            try:
                _resp, lines, _octets = mail.uidl()
            except poplib.error_proto:
                _resp, listed, _octets = mail.list()
                lines = []
                for item in listed or []:
                    if not item:
                        continue
                    num, size = item.decode("ascii", errors="replace").split(None, 1)
                    lines.append(f"{num} {num}-{size}".encode())
            for num, uid in pop_candidates(lines, seen):
                try:
                    header = email_lib.message_from_bytes(b"\n".join(mail.top(num, 0)[1]))
                    download = _worth_opening(self.target_email, header)
                except poplib.error_proto:
                    header = None
                    download = True
                if not download and header is not None:
                    out.append((uid, header))
                    continue
                raw = b"\n".join(mail.retr(num)[1])
                out.append((uid, email_lib.message_from_bytes(raw)))
        finally:
            try:
                mail.quit()
            except Exception:
                pass
        return out


class ManualMailbox(Mailbox):
    def __init__(self, target_email: str, ask_link) -> None:
        self.target_email = target_email
        self._ask = ask_link

    def wait_link(self) -> str | None:
        if self._ask is None:
            return None
        return self._ask(self.target_email)


class SharedMailboxClient(Mailbox):
    def __init__(self, shared: SharedMailbox, email: str, timeout_sec: int) -> None:
        self.shared = shared
        self.email = email
        self.timeout_sec = timeout_sec

    def start(self) -> None:
        self.shared.register(self.email)

    def stop(self) -> None:
        self.shared.unregister(self.email)

    def wait_link(self) -> str | None:
        return self.shared.wait_link(self.email, self.timeout_sec)


class SharedMailbox:
    """Surveille la boîte mail avec une connexion unique pour tous les workers en parallèle."""

    def __init__(
        self,
        protocol: str,
        host: str,
        user: str,
        password: str,
        pause_sec: float = 3.0,
    ) -> None:
        self.protocol = protocol
        self.host = host
        self.user = user
        self.password = password
        self.pause_sec = pause_sec
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._listeners: dict[str, threading.Event] = {}
        self._links: dict[str, str] = {}
        self.error: str | None = None
        self.last_error: str | None = None
        self.ok_polls = 0
        self._auth_fails = 0
        self._imap = None
        self._uid_cursor: dict[str, int] = {}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for ev in self._listeners.values():
                ev.set()
        self._close_imap()

    def _close_imap(self) -> None:
        mail = self._imap
        self._imap = None
        if mail is None:
            return
        try:
            mail.logout()
        except Exception:
            pass

    def register(self, email: str) -> None:
        key = email.lower()
        with self._lock:
            if key not in self._listeners:
                self._listeners[key] = threading.Event()

    def unregister(self, email: str) -> None:
        key = email.lower()
        with self._lock:
            self._listeners.pop(key, None)

    def client(self, email: str, timeout_sec: int) -> SharedMailboxClient:
        return SharedMailboxClient(self, email, timeout_sec)

    def wait_link(self, email: str, timeout_sec: int) -> str | None:
        key = email.lower()
        with self._lock:
            if key in self._links:
                return self._links[key]
            if key not in self._listeners:
                self._listeners[key] = threading.Event()
            ev = self._listeners[key]

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            with self._lock:
                if key in self._links:
                    return self._links[key]
                if self.error:
                    raise RuntimeError(self.error)
            if ev.wait(0.2):
                break
            if self._stop.is_set():
                break

        with self._lock:
            if key in self._links:
                return self._links[key]
            if self.ok_polls == 0 and self.last_error:
                raise RuntimeError(self.last_error)
            return None

    def _deliver(self, email: str, link: str) -> None:
        key = email.lower()
        with self._lock:
            self._links[key] = link
            ev = self._listeners.get(key)
            if ev:
                ev.set()

    def _process_message(self, msg: Message) -> None:
        hay = _body(msg) + " " + str(msg.get("Subject") or "")
        link = activation_link(hay)
        if not link:
            return

        # 1. Email exact dans l'URL de confirmation
        qs = parse_qs(urlsplit(link).query)
        target = (qs.get("emailCompte") or [""])[0].lower()
        if target:
            self._deliver(target, link)
            return

        # 2. Correspondance exacte dans les en-têtes
        headers = _address_headers(msg).lower()
        with self._lock:
            candidates = list(self._listeners.keys())
        for cand in candidates:
            if cand in headers:
                self._deliver(cand, link)
                return

        # 3. Correspondance de boîte (alias Gmail)
        for cand in candidates:
            if _same_box(cand, headers) or _same_box(cand, hay):
                self._deliver(cand, link)
                return

    def _fetch_messages(self, seen: set[str]) -> list[tuple[str, Message]]:
        if self.protocol == "pop3":
            return self._fetch_pop3(seen)
        return self._fetch_imap(seen)

    def _fetch_imap(self, seen: set[str]) -> list[tuple[str, Message]]:
        """Lit seulement les UID apparus depuis le dernier passage.

        Une recherche SUBJECT sur Gmail parcourt toute la boîte et dépasse
        souvent le délai, alors que le mail est déjà visible. Le numéro UID
        du dernier message, lui, répond tout de suite.
        """
        if self._imap is None:
            self._imap = _login_imap(self.host, self.user, self.password)
        mail = self._imap
        try:
            folders = ("INBOX", "Junk") if uses_xoauth2(self.host, self.user) else ("INBOX", "[Gmail]/Spam")
            for folder in folders:
                with self._lock:
                    waiting = [k for k in self._listeners if k not in self._links]
                if self._listeners and not waiting:
                    break
                try:
                    typ, _ = mail.select(folder, readonly=True)
                except imaplib.IMAP4.error:
                    continue
                if typ != "OK":
                    continue
                if folder not in self._uid_cursor:
                    typ, latest = mail.uid("FETCH", "*", "(UID)")
                    highest = _highest_uid(latest) if typ == "OK" else 0
                    if highest <= 0:
                        continue
                    self._uid_cursor[folder] = max(0, highest - 100)
                start = self._uid_cursor[folder] + 1
                typ, fetched = mail.uid(
                    "FETCH", f"{start}:*", "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
                )
                if typ != "OK":
                    continue
                fresh: list[str] = []
                top = self._uid_cursor[folder]
                for uid, raw in _uid_bodies(fetched):
                    number = int(uid)
                    if number <= self._uid_cursor[folder]:
                        continue
                    top = max(top, number)
                    if _is_ugc_header(email_lib.message_from_bytes(raw)):
                        fresh.append(uid)
                for i in range(0, len(fresh), 15):
                    chunk = ",".join(fresh[i : i + 15])
                    typ, bodies = mail.uid("FETCH", chunk, "(UID BODY.PEEK[])")
                    if typ != "OK":
                        continue
                    for uid, raw in _uid_bodies(bodies):
                        seen.add(uid)
                        self._process_message(email_lib.message_from_bytes(raw))
                self._uid_cursor[folder] = top
            return []
        except Exception:
            self._close_imap()
            raise

    def _fetch_pop3(self, seen: set[str]) -> list[tuple[str, Message]]:
        out: list[tuple[str, Message]] = []
        mail = _login_pop(self.host, self.user, self.password)
        try:
            try:
                _resp, lines, _octets = mail.uidl()
            except poplib.error_proto:
                _resp, listed, _octets = mail.list()
                lines = []
                for item in listed or []:
                    if not item:
                        continue
                    num, size = item.decode("ascii", errors="replace").split(None, 1)
                    lines.append(f"{num} {num}-{size}".encode())
            for num, uid in pop_candidates(lines, seen, limit=60):
                try:
                    header = email_lib.message_from_bytes(b"\n".join(mail.top(num, 0)[1]))
                    subj = str(header.get("Subject") or "").lower()
                    with self._lock:
                        listeners = list(self._listeners.keys())
                    addr = _address_headers(header)
                    worth = (
                        "ugc" in subj
                        or "inscription" in subj
                        or "confirmez" in subj
                        or any(_same_box(l, addr) for l in listeners)
                    )
                except poplib.error_proto:
                    worth = True
                if not worth:
                    seen.add(uid)
                    continue
                raw = b"\n".join(mail.retr(num)[1])
                out.append((uid, email_lib.message_from_bytes(raw)))
        finally:
            try:
                mail.quit()
            except Exception:
                pass
        return out

    def _run(self) -> None:
        seen: set[str] = set()
        while not self._stop.is_set():
            try:
                found = self._fetch_messages(seen)
                self.ok_polls += 1
                self.last_error = None
                for mid, msg in found:
                    seen.add(mid)
                    self._process_message(msg)
            except Exception as exc:
                self._close_imap()
                if _is_auth_failure(exc):
                    self._auth_fails += 1
                    self.last_error = str(exc)
                    if self.ok_polls == 0 and self._auth_fails >= 4:
                        self.error = str(exc)
                        with self._lock:
                            for ev in self._listeners.values():
                                ev.set()
                        return
                else:
                    self._auth_fails = 0
                    self.last_error = str(exc)
            else:
                self._auth_fails = 0
            self._stop.wait(self.pause_sec)


def open_mailbox(protocol: str, host: str, user: str, password: str, target_email: str, timeout_sec: int, ask_link) -> Mailbox:
    if protocol == "manual":
        return ManualMailbox(target_email, ask_link)
    kind = Pop3Mailbox if protocol == "pop3" else ImapMailbox
    return kind(host, user, password, target_email, timeout_sec)
