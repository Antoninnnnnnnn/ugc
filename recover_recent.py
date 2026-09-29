"""Reprend les 50 derniers mails reçus : active, connecte, adhère, ajoute au CSV.

À lancer une fois : py recover_recent.py
Puis supprimer ce fichier.
"""
from __future__ import annotations

import email as email_lib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from ugc_flow.config import ROOT, load_settings
from ugc_flow.fidelity import join_fidelity
from ugc_flow.mailer import _imap_literals, _login_imap, activation_target
from ugc_flow.profile import Person
from ugc_flow.runner import Account, append_account, export_accounts, list_accounts
from ugc_flow.session import UgcSession
from ugc_flow.signup import SignupError, _login

LIMIT = 50
EXPORT = ROOT / "accounts.csv"
THREADS = 8
_print = threading.Lock()
_csv = threading.Lock()


def say(msg: str) -> None:
    with _print:
        print(msg, flush=True)


def recent_links(host: str, user: str, password: str, limit: int) -> dict[str, str]:
    """Les `limit` derniers messages de la boîte, sans recherche sur toute la boîte."""
    say("connexion IMAP")
    mail = _login_imap(host, user, password)
    links: dict[str, str] = {}
    try:
        typ, data = mail.select("INBOX", readonly=True)
        if typ != "OK" or not data or not data[0]:
            return links
        count = int(data[0])
        start = max(1, count - limit + 1)
        say(f"lecture des messages {start} à {count}")
        for seq in range(start, count + 1, 10):
            end = min(seq + 9, count)
            typ, fetched = mail.fetch(f"{seq}:{end}", "(BODY.PEEK[])")
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
        return links
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def person_of(run: Path) -> Person:
    c = json.loads((run / "credentials.json").read_text(encoding="utf-8-sig"))
    return Person(
        email=c["email"],
        password=c["password"],
        first_name=c["first_name"],
        last_name=c["last_name"],
        birth=date.fromisoformat(c["birth"]),
        phone="",
        postal=c.get("postal") or "75011",
        city="",
    )


def pending_runs() -> dict[str, Path]:
    """Dernier dossier encore non abouti pour chaque adresse."""
    chosen: dict[str, Path] = {}
    done: set[str] = set()
    for d in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir()):
        cred = d / "credentials.json"
        if not cred.exists():
            continue
        c = json.loads(cred.read_text(encoding="utf-8-sig"))
        email = str(c.get("email") or "").lower()
        if not email:
            continue
        res = {}
        if (d / "result.json").exists():
            res = json.loads((d / "result.json").read_text(encoding="utf-8-sig"))
        if res.get("ok"):
            done.add(email)
            chosen.pop(email, None)
            continue
        if email in done:
            continue
        chosen[email] = d
    return chosen


def save(run: Path, result: dict) -> None:
    (run / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def resume(settings, link: str, run: Path, n: int, total: int) -> bool:
    result = json.loads((run / "result.json").read_text(encoding="utf-8-sig")) if (run / "result.json").exists() else {}
    person = person_of(run)
    tag = f"[{n:02d}/{total:02d}]"
    try:
        with UgcSession(settings.ugc_base, settings.proxy_source, run / "retry") as sess:
            say(f"{tag} activation {person.email}")
            act = sess.get(link, "activation")
            if "bien activé" not in act.text:
                raise SignupError(f"activation non confirmée ({act.url})")
            result["activated"] = True
            result["signup_accepted"] = True
            say(f"{tag} connexion")
            _login(sess, settings, person, None)
            result["logged_in"] = True
            say(f"{tag} fidélité")
            points = join_fidelity(sess, person)
            result["fid_joined"] = True
            result["fid_points"] = points
            result["ok"] = points is None or points >= 100
            result.pop("error", None)
            save(run, result)
            if result["ok"]:
                acc = Account(run.name, person.email, person.password, True, points, True, "")
                with _csv:
                    append_account(acc, EXPORT)
            say(f"{tag} OK {person.email}")
            return bool(result["ok"])
    except Exception as exc:
        result["error"] = str(exc)
        save(run, result)
        say(f"{tag} ÉCHEC {person.email}  {exc}")
        return False


def main() -> None:
    settings = load_settings()
    host, _port = settings.endpoint()
    links = recent_links(host, settings.imap_user, settings.imap_password, LIMIT)
    say(f"{len(links)} liens d'activation dans les {LIMIT} derniers mails")
    runs = pending_runs()
    todo = [(runs[addr], link) for addr, link in links.items() if addr in runs]
    unknown = [addr for addr in links if addr not in runs]
    say(f"{len(todo)} comptes à reprendre, {len(unknown)} mails sans dossier local")
    for addr in unknown:
        say(f"  sans dossier : {addr}")
    if not todo:
        return
    ok = 0
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futs = [pool.submit(resume, settings, link, run, i, len(todo)) for i, (run, link) in enumerate(todo, 1)]
        for fut in as_completed(futs):
            ok += int(fut.result())
    n = export_accounts(list_accounts(settings.runs_dir), EXPORT)
    say(f"Terminé : {ok}/{len(todo)} repris. {n} OK dans {EXPORT.name}")


if __name__ == "__main__":
    main()
