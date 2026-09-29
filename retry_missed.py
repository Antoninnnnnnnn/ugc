"""Reprise ponctuelle du lot 20260928_22 : inscription faite, mail non lu.

À lancer une fois : py retry_missed.py
Puis supprimer ce fichier.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from ugc_flow.config import ROOT, load_settings
from ugc_flow.fidelity import join_fidelity
from ugc_flow.mailer import load_activation_links
from ugc_flow.profile import Person
from ugc_flow.runner import Account, append_account, export_accounts, list_accounts
from ugc_flow.session import UgcSession
from ugc_flow.signup import SignupError, _login

BATCH = "20260928_225238"
EXPORT = ROOT / "accounts.csv"
THREADS = 15
_print = threading.Lock()
_csv = threading.Lock()


def say(msg: str) -> None:
    with _print:
        print(msg, flush=True)


def targets() -> list[Path]:
    out = []
    for d in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir() and p.name.startswith(BATCH)):
        res = json.loads((d / "result.json").read_text(encoding="utf-8-sig"))
        if res.get("signup_accepted") and not res.get("activated") and not res.get("ok"):
            out.append(d)
    return out


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


def save(run: Path, result: dict) -> None:
    (run / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def resume(settings, link: str, run: Path, n: int, total: int) -> bool:
    result = json.loads((run / "result.json").read_text(encoding="utf-8-sig"))
    person = person_of(run)
    tag = f"[{n:02d}/{total:02d}]"
    try:
        with UgcSession(settings.ugc_base, settings.proxy_source, run / "retry") as sess:
            say(f"{tag} activation {person.email}")
            act = sess.get(link, "activation")
            if "bien activé" not in act.text:
                raise SignupError(f"activation non confirmée ({act.url})")
            result["activated"] = True
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
    runs = targets()
    if not runs:
        say("Rien à reprendre.")
        return
    people = [(run, person_of(run)) for run in runs]
    wanted = {p.email.lower() for _, p in people}
    say(f"{len(runs)} comptes. Lecture groupée des mails UGC…")
    host, _port = settings.endpoint()
    links = load_activation_links(
        host, settings.imap_user, settings.imap_password, wanted, progress=say
    )
    found = [(run, p, links.get(p.email.lower())) for run, p in people]
    missing = [p.email for _, p, link in found if not link]
    say(f"{sum(1 for _r, _p, link in found if link)} liens pour ce lot, {len(missing)} introuvables")
    for email in missing:
        say(f"  pas de mail pour {email}")
    todo = [(run, link) for run, _p, link in found if link]
    if not todo:
        return
    say(f"Activation de {len(todo)} comptes, {THREADS} en parallèle")
    ok = 0
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futs = [pool.submit(resume, settings, link, run, i, len(todo)) for i, (run, link) in enumerate(todo, 1)]
        for fut in as_completed(futs):
            ok += int(fut.result())
    n = export_accounts(list_accounts(settings.runs_dir), EXPORT)
    say(f"Terminé : {ok}/{len(todo)} repris. {n} OK dans {EXPORT.name}")


if __name__ == "__main__":
    main()
