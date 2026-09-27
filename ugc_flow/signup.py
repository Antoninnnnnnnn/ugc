from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ugc_flow.captcha import solve_friendly_captcha
from ugc_flow.config import Settings
from ugc_flow.fidelity import FidelityError, join_fidelity
from ugc_flow.mailer import Mailbox, open_mailbox
from ugc_flow.parse import email_validation_ok, hidden_csrf, struts_errors
from ugc_flow.profile import Person, make_person
from ugc_flow.session import UA, UgcSession


class SignupError(RuntimeError):
    pass


def _write_creds(dump_dir: Path, person: Person) -> None:
    (dump_dir / "credentials.json").write_text(
        json.dumps(
            {
                "email": person.email,
                "password": person.password,
                "first_name": person.first_name,
                "last_name": person.last_name,
                "birth": person.birth.isoformat(),
                "postal": person.postal,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


LinkPrompt = Callable[[str], "str | None"]


def run_signup(
    settings: Settings,
    dump_dir: Path,
    on_step: Callable[[str], None] | None = None,
    ask_link: LinkPrompt | None = None,
    email: str | None = None,
    mailbox: Mailbox | None = None,
) -> dict:
    """ask_link(email) est appelé quand le protocole est « manual »."""
    step = on_step or (lambda _s: None)
    if not settings.fetches_mail and ask_link is None:
        raise SignupError("mail automatique désactivé et aucune saisie du lien possible")
    person = make_person(settings.catchall_domains, email)
    dump_dir.mkdir(parents=True, exist_ok=True)
    _write_creds(dump_dir, person)
    if mailbox is not None:
        box = mailbox
    else:
        host, _port = ("", 0)
        if settings.fetches_mail:
            host, _port = settings.endpoint()
        box = open_mailbox(
            settings.mail_protocol,
            host,
            settings.imap_user,
            settings.imap_password,
            person.email,
            settings.imap_timeout_sec,
            ask_link,
        )
    box.start()
    result: dict = {"email": person.email, "ok": False, "proxy": bool(settings.proxy_source)}

    sess: UgcSession | None = None
    try:
        with UgcSession(settings.ugc_base, settings.proxy_source, dump_dir) as sess:
            step("inscription")
            _create_account(sess, settings, person, result)

            step("attente mail" if settings.fetches_mail else "lien d'activation à coller")
            try:
                link = box.wait_link()
            except RuntimeError as exc:
                raise SignupError(str(exc)) from exc
            if not link:
                raise SignupError(
                    "aucun mail d'activation reçu" if settings.fetches_mail else "lien d'activation non fourni"
                )
            step("activation")
            act = sess.get(link, "activation")
            if "bien activé" not in act.text:
                raise SignupError(f"activation non confirmée ({act.url})")
            result["activated"] = True

            step("connexion")
            _login(sess, settings, person, result.pop("csrf", None))
            result["logged_in"] = True

            step("fidélité")
            try:
                points = join_fidelity(sess, person)
            except FidelityError as exc:
                raise SignupError(str(exc)) from exc
            result["fid_joined"] = True
            result["fid_location"] = sess.last_join_location
            if points is not None:
                result["fid_points"] = points
            result["ok"] = points is None or points >= 100
            return result
    except SignupError as exc:
        result["error"] = str(exc)
        return result
    except Exception as exc:
        result["error"] = repr(exc)
        return result
    finally:
        if sess is not None:
            result["proxy_kb"] = round(sess.traffic_bytes / 1024, 1)
            result["traffic"] = [
                {"req": n, "sent": s, "recv": r} for n, s, r in sess.traffic
            ]
        box.stop()


def _create_account(sess: UgcSession, settings: Settings, person: Person, result: dict) -> None:
    login = sess.get("/login.html", "login")
    if login.status_code >= 400:
        raise SignupError(f"GET login.html HTTP {login.status_code}")

    val = sess.post(
        "/monCompteInscriptionAction!validationEmail.action",
        "validation-email",
        {"page": "30058", "inscriptionBean.email": person.email},
        ajax=True,
    )
    ok, msg = email_validation_ok(val.text)
    if not ok:
        raise SignupError(f"validationEmail refusé: {msg}")

    result["csrf"] = hidden_csrf(login.text)

    # Formulaire 30058 connu : on saute la page redirect_form (~45 Ko de HTML).
    sess.referer = f"{settings.ugc_base}/monCompteInscriptionAction.action"
    payload = {
        "page": "30058",
        "inscriptionBean.email": person.email,
        "inscriptionBean.password": person.password,
        "inscriptionBean.confirm": person.password,
        "inscriptionBean.checked": "on",
        "inscriptionBean.seizeAns": "on",
        "frc-captcha-response": _solve(sess, settings, f"{settings.ugc_base}/inscription.html"),
    }
    posted = sess.post("/monCompteInscriptionAction!inscription", "inscription-submit", payload)
    errs = struts_errors(posted.text)
    if errs:
        raise SignupError("inscription refusée: " + " | ".join(errs[:6]))
    if "CLIQUEZ SUR LE LIEN" not in posted.text:
        raise SignupError(f"inscription: page inattendue ({posted.url})")
    result["signup_accepted"] = True


def _login(sess: UgcSession, settings: Settings, person: Person, csrf: str | None = None) -> None:
    if not csrf:
        page = sess.get("/login.html", "login-refresh")
        csrf = hidden_csrf(page.text)
    if not csrf:
        raise SignupError("pas de CSRF pour login")
    sess.referer = f"{settings.ugc_base}/login.html"
    data = {
        "_csrf": csrf,
        "j_username": person.email,
        "j_password": person.password,
        "remember-me": "on",
        "frc-captcha-response": _solve(sess, settings, f"{settings.ugc_base}/login.html"),
    }
    r = sess.post("/j_spring_security_check", "spring-login", data, follow=False)
    # Suivre les 302 pour récupérer les cookies SSO, sans télécharger la page profil (~75 Ko).
    for hop in range(5):
        loc = sess.location(r)
        if not loc:
            break
        if "profilAction" in loc:
            return
        r = sess.get(loc, f"spring-login-hop{hop}", follow=False)
    raise SignupError(f"login refusé ({r.url})")


def _solve(sess: UgcSession, settings: Settings, page_url: str) -> str:
    return solve_friendly_captcha(
        settings.captcha_provider,
        settings.captcha_api_key,
        page_url,
        settings.friendly_sitekey,
        user_agent=UA,
        proxy_url=sess.proxy if settings.captcha_use_proxy else None,
    )
