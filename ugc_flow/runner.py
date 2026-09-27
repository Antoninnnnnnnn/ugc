from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from ugc_flow.config import Settings
from ugc_flow.fidelity import join_fidelity
from ugc_flow.mailer import Mailbox
from ugc_flow.profile import Person
from ugc_flow.session import UgcSession
from ugc_flow.signup import LinkPrompt, _login, run_signup


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def run_one(
    settings: Settings,
    on_step: Callable[[str], None] | None = None,
    ask_link: LinkPrompt | None = None,
    email: str | None = None,
    mailbox: Mailbox | None = None,
) -> dict:
    run_id = new_run_id()
    dump_dir = settings.runs_dir / run_id
    try:
        result = run_signup(settings, dump_dir, on_step, ask_link, email, mailbox=mailbox)
    except Exception as exc:
        result = {"ok": False, "error": repr(exc)}
    dump_dir.mkdir(parents=True, exist_ok=True)
    result["run_id"] = run_id
    if result.get("ok") and not settings.keep_dumps:
        for p in dump_dir.iterdir():
            if p.suffix == ".html" or p.name.endswith("-post.json"):
                p.unlink()
    (dump_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    creds = _read_json(dump_dir / "credentials.json")
    result.setdefault("email", creds.get("email", ""))
    result["password"] = creds.get("password", "")
    return result


@dataclass
class Account:
    run_id: str
    email: str
    password: str
    ok: bool
    fid_points: int | None
    activated: bool
    error: str

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        if self.activated:
            return "ACTIVÉ"
        return "ÉCHEC"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def list_accounts(runs_dir: Path) -> list[Account]:
    out: list[Account] = []
    if not runs_dir.exists():
        return out
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        creds = _read_json(d / "credentials.json")
        if not creds.get("email"):
            continue
        res = _read_json(d / "result.json")
        join = _read_json(d / "join" / "result.json")
        points = join.get("fid_points") or res.get("fid_points")
        out.append(
            Account(
                run_id=d.name,
                email=creds["email"],
                password=creds.get("password", ""),
                ok=bool(res.get("ok") or join.get("ok")),
                fid_points=points,
                activated=bool(res.get("activated") or join.get("ok")),
                error=str(res.get("error") or ""),
            )
        )
    return out


def export_accounts(accounts: list[Account], path: Path, only_ok: bool = True) -> int:
    rows = [a for a in accounts if a.ok or not only_ok]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["email", "password", "points", "statut", "run_id"])
        for a in rows:
            w.writerow([a.email, a.password, a.fid_points or "", a.status, a.run_id])
    return len(rows)


def append_account(acc: Account, path: Path) -> None:
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        if write_header:
            w.writerow(["email", "password", "points", "statut", "run_id"])
        w.writerow([acc.email, acc.password, acc.fid_points or "", acc.status, acc.run_id])


def join_existing(settings: Settings, run_dir: Path) -> int:
    creds = _read_json(run_dir / "credentials.json")
    person = Person(
        email=creds["email"],
        password=creds["password"],
        first_name=creds["first_name"],
        last_name=creds["last_name"],
        birth=date.fromisoformat(creds["birth"]),
        phone="",
        postal=creds.get("postal") or "75011",
        city="",
    )
    out = run_dir / "join"
    with UgcSession(settings.ugc_base, settings.proxy_source, out) as sess:
        _login(sess, settings, person)
        points = join_fidelity(sess, person, verify_points=True) or 0
    (out / "result.json").write_text(
        json.dumps({"ok": points >= 100, "fid_points": points}, indent=2), encoding="utf-8"
    )
    return points
