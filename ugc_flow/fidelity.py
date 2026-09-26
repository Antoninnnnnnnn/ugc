from __future__ import annotations

import re

from ugc_flow.parse import parse_forms, soup, struts_errors
from ugc_flow.profile import Person
from ugc_flow.session import UgcSession

FID_BASE = "https://fidelite.ugc.fr"
ADHESION_URL = f"{FID_BASE}/adhesion.html"


class FidelityError(RuntimeError):
    pass


def membership_payload(html: str, person: Person) -> dict[str, str]:
    forms = [f for f in parse_forms(html, FID_BASE) if f.form_id == "membershipForm"]
    if not forms:
        raise FidelityError("membershipForm absent de adhesion.html")
    names = {f.name for f in forms[0].fields}
    email = next((f.value for f in forms[0].fields if f.name == "membership.email"), "") or person.email
    data = {
        "membership.cardnumber": "",
        "membership.email": email,
        "membership.firstname": person.first_name,
        "membership.lastname": person.last_name,
        # jQuery UI datepicker fr: dateFormat "dd/mm/y" (année sur 2 chiffres)
        "membership.birthday": person.birth.strftime("%d/%m/%y"),
        "membership.zipCode": person.postal,
        "membership.country": "France",
        "membership.newsletter": "true",
        "__checkbox_membership.newsletter": "true",
        "membership.cgu": "true",
        "__checkbox_membership.cgu": "true",
        "method:join": "Submit",
    }
    missing = [k for k in data if k.startswith("membership.") and k not in names]
    if missing:
        raise FidelityError("champs membership inattendus: " + ", ".join(missing))
    return data


def fid_points(html: str) -> int | None:
    text = re.sub(r"\s+", " ", soup(html).get_text(" ", strip=True))
    m = re.search(r"Mes points fid[ée]lit[ée]\s*:\s*(\d+)\s*POINTS", text, re.I)
    return int(m.group(1)) if m else None


def _blind_payload(person: Person) -> dict[str, str]:
    html = (
        '<form id="membershipForm">'
        + "".join(
            f'<input name="membership.{n}"/>'
            for n in ("cardnumber", "email", "firstname", "lastname", "birthday", "zipCode", "country", "newsletter", "cgu")
        )
        + "</form>"
    )
    return membership_payload(html, person)


def join_fidelity(sess: UgcSession, person: Person, *, verify_points: bool = False) -> int | None:
    if not verify_points:
        # Formulaire connu : POST direct, sans télécharger adhesion.html (~27 Ko).
        sess.referer = ADHESION_URL
        blind = sess.post(ADHESION_URL, "fid-join-direct", _blind_payload(person), follow=False)
        loc = sess.location(blind)
        sess.last_join_location = loc
        if "catalogue" in loc:
            return None
    page = sess.get(ADHESION_URL, "fid-adhesion")
    if "membershipForm" not in page.text:
        raise FidelityError(f"adhesion.html sans formulaire ({page.url}) — session non transmise ?")
    payload = membership_payload(page.text, person)
    posted = sess.post(ADHESION_URL, "fid-join", payload, follow=verify_points)
    if posted.is_redirect:
        # Succès = 302 vers le catalogue ; on ne télécharge pas le catalogue (~45 Ko).
        sess.last_join_location = sess.location(posted)
        return None
    errs = struts_errors(posted.text)
    if errs and "membershipForm" in posted.text:
        raise FidelityError("adhésion refusée: " + " | ".join(errs[:6]))
    points = fid_points(posted.text)
    if points is None:
        raise FidelityError(f"adhésion: réponse inattendue ({posted.url})")
    return points
