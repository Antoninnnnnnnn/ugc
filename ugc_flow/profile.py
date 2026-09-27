from __future__ import annotations

import random
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import date

from ugc_flow.parse import FormField, HtmlForm

FIRST = [
    "Lucas", "Hugo", "Louis", "Liam", "Adam", "Arthur", "Noah", "Gabriele",
    "Emma", "Jade", "Louise", "Alice", "Chloe", "Lea", "Manon", "Ines",
]
LAST = [
    "Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard", "Durand",
    "Dubois", "Moreau", "Laurent", "Simon", "Michel", "Lefebvre", "Garcia",
]


@dataclass
class Person:
    email: str
    password: str
    first_name: str
    last_name: str
    birth: date
    phone: str
    postal: str
    city: str


def parse_emails(text: str) -> list[str]:
    """Adresses collées d'un bloc : virgules, points-virgules, espaces ou retours à la ligne."""
    found = re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", text.lower())
    out: list[str] = []
    seen: set[str] = set()
    for addr in found:
        if addr not in seen:
            seen.add(addr)
            out.append(addr)
    return out


def gmail_base(email: str) -> str:
    """Adresse canonique : Gmail ignore les points du local-part."""
    local, _, domain = email.strip().lower().partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def dot_alias(email: str, used: set[str]) -> str:
    """Autre placement de points, même boîte Gmail. `used` contient les adresses déjà prises."""
    local, domain = gmail_base(email).split("@", 1)
    gaps = len(local) - 1
    if gaps < 1:
        raise ValueError("adresse trop courte pour un alias avec des points")
    taken = {u.lower() for u in used}
    for _ in range(500):
        mask = secrets.randbelow((1 << gaps) - 1) + 1
        chars: list[str] = []
        for i, ch in enumerate(local):
            chars.append(ch)
            if i < gaps and (mask >> i) & 1:
                chars.append(".")
        alias = f"{''.join(chars)}@{domain}"
        if alias not in taken:
            return alias
    raise RuntimeError("plus d'alias à points disponible")


def make_person(domains: tuple[str, ...], email: str | None = None) -> Person:
    if email:
        addr = email
    elif domains:
        addr = "u" + uuid.uuid4().hex[:12] + "@" + random.choice(domains)
    else:
        raise ValueError("ni domaine catch-all ni adresse e-mail")
    alphabet = string.ascii_letters + string.digits
    password = "Ug" + "".join(secrets.choice(alphabet) for _ in range(10)) + "9!"
    year = random.randint(1984, 1999)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return Person(
        email=addr,
        password=password,
        first_name=random.choice(FIRST),
        last_name=random.choice(LAST),
        birth=date(year, month, day),
        phone="06" + "".join(str(random.randint(0, 9)) for _ in range(8)),
        postal=random.choice(["75011", "69003", "33000", "13001", "31000"]),
        city=random.choice(["Paris", "Lyon", "Bordeaux", "Marseille", "Toulouse"]),
    )


def _norm(name: str) -> str:
    return name.lower().replace(".", " ").replace("_", " ").replace("-", " ")


def _value_for(field: FormField, person: Person) -> str | None:
    n = _norm(field.name)
    t = field.type
    if field.name == "inscriptionBean.moinsSeizeAns":
        return None
    if field.name in {"inscriptionBean.checked", "inscriptionBean.seizeAns"}:
        return "on"
    if field.name == "inscriptionBean.subscribeNewsLetters":
        return None
    if field.name == "inscriptionBean.tutorEmail":
        return None
    if field.name == "inscriptionBean.birthday":
        return None
    if t == "hidden":
        if "email" in n and not field.value:
            return person.email
        return field.value
    if "tutor" in n:
        return None
    if t == "email" or n.endswith("email") or "email" in n:
        return person.email
    if t == "password" or "password" in n or "motdepasse" in n.replace(" ", "") or "mdp" in n.split() or n.endswith("confirm"):
        return person.password
    if any(k in n for k in ("prenom", "firstname", "first name", "given")):
        return person.first_name
    if any(k in n for k in ("nom", "lastname", "last name", "surname", "family")) and "pre" not in n:
        if "prenom" in n:
            return person.first_name
        return person.last_name
    if "birthday" in n:
        return None
    if any(k in n for k in ("naissance", "birth", "date naissance")):
        if field.tag == "select":
            return _select_date_part(field, person)
        if "jour" in n or n.endswith("jour"):
            return f"{person.birth.day:02d}"
        if "mois" in n or "month" in n:
            return f"{person.birth.month:02d}"
        if "annee" in n or "année" in n or "year" in n:
            return str(person.birth.year)
        return person.birth.strftime("%d/%m/%Y")
    if "jour" in n:
        return _pick_option(field, f"{person.birth.day:02d}", str(person.birth.day))
    if "mois" in n:
        return _pick_option(field, f"{person.birth.month:02d}", str(person.birth.month))
    if "annee" in n or "année" in n:
        return _pick_option(field, str(person.birth.year))
    if any(k in n for k in ("tel", "phone", "mobile")):
        return person.phone
    if any(k in n for k in ("postal", "cp", "zip")):
        return person.postal
    if "ville" in n or "city" in n:
        return person.city
    if any(k in n for k in ("civilite", "civility", "genre", "gender", "title", "sexe")):
        return _pick_civilite(field)
    if t == "checkbox":
        if any(k in n for k in ("cgu", "cgv", "condition", "fidel", "club", "optin", "accept", "consent")):
            return "on"
        if "seizeans" in n and "moins" in n:
            return None
        if "seizeans" in n:
            return "on"
        if field.required:
            return "on"
        return None
    if t == "radio":
        if any(k in n for k in ("civilite", "genre", "sexe", "mr", "mme")):
            return field.value or "MR"
        return field.value or None
    return None


def _pick_option(field: FormField, *candidates: str) -> str:
    opts = [o for o in field.options if o != ""]
    for c in candidates:
        if c in opts:
            return c
        for o in opts:
            if o.lstrip("0") == c.lstrip("0") and o != "":
                return o
    return field.value or (opts[1] if len(opts) > 1 else (opts[0] if opts else ""))


def _select_date_part(field: FormField, person: Person) -> str:
    n = _norm(field.name)
    if "jour" in n or "day" in n:
        return _pick_option(field, f"{person.birth.day:02d}", str(person.birth.day))
    if "mois" in n or "month" in n:
        return _pick_option(field, f"{person.birth.month:02d}", str(person.birth.month))
    if "an" in n or "year" in n:
        return _pick_option(field, str(person.birth.year))
    return person.birth.isoformat()


def _pick_civilite(field: FormField) -> str:
    opts = [o for o in field.options if o]
    for key in ("MR", "M", "1", "Monsieur", "M."):
        if key in opts:
            return key
    return field.value or (opts[0] if opts else "MR")


def fill_inscription(form: HtmlForm, person: Person) -> dict[str, str]:
    data: dict[str, str] = {}
    unknown: list[str] = []
    for field in form.fields:
        if not field.name:
            continue
        if field.type == "submit" or field.type == "button" or field.type == "image":
            continue
        val = _value_for(field, person)
        if val is None:
            if field.type == "hidden":
                if field.value:
                    data[field.name] = field.value
                continue
            if field.required and field.type != "checkbox":
                unknown.append(field.name)
            elif field.value:
                data[field.name] = field.value
            continue
        data[field.name] = val
        if field.type == "checkbox":
            data[field.name] = val
    if "page" not in data:
        data["page"] = "30058"
    if unknown:
        raise ValueError("champs required inconnus: " + ", ".join(unknown))
    return data
