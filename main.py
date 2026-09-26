from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from ugc_flow.captcha import get_balance
from ugc_flow.config import ROOT, Settings, load_settings, proxy_count
from ugc_flow.mailer import check_login, check_pasted_link, recent_headers
from ugc_flow.profile import dot_alias
from ugc_flow.runner import Account, export_accounts, join_existing, list_accounts, run_one

EXPORT_FILE = ROOT / "accounts.csv"
MAX_THREADS = 5
STAGGER_SEC = 3.0

os.system("")
G, R, Y, C, D, B, X = (f"\033[{c}m" for c in ("92", "91", "93", "96", "2", "1", "0"))
_print_lock = threading.Lock()


def say(msg: str = "") -> None:
    with _print_lock:
        print(msg, flush=True)


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"{C}?{X} {prompt}{hint} : ").strip()
    except EOFError:
        val = ""
    return val or default


def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = ask(prompt, str(default))
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        say(f"{R}Entre un nombre entre {lo} et {hi}.{X}")


# ---------------------------------------------------------------- actions


def prompt_link(email: str) -> str | None:
    say(f"\n{Y}{B}Mail d'activation envoyé à {email}{X}")
    say(f"{D}  Ouvre le mail « UGC - Confirmez votre inscription à MON COMPTE »,")
    say(f"  copie le lien du bouton de confirmation et colle-le ici.{X}")
    while True:
        raw = ask("Lien d'activation (vide = abandonner ce compte)")
        if not raw:
            return None
        url, why = check_pasted_link(raw, email)
        if url:
            return url
        say(f"{R}Lien refusé : {why}.{X}")


def modes(settings: Settings) -> str:
    if settings.proxy_source:
        proxy = f"{G}proxy{X} ({proxy_count(settings.proxy_file)})"
    else:
        why = "désactivé" if settings.proxy_available else "aucun proxy trouvé"
        proxy = f"{Y}connexion directe{X} {D}({why}){X}"
    if settings.use_imap:
        mail = f"{G}IMAP auto{X}"
    else:
        why = "désactivé" if settings.imap_available else "pas de mot de passe IMAP"
        mail = f"{Y}lien collé à la main{X} {D}({why}){X}"
    return f"réseau : {proxy}   mail : {mail}"


def plan_emails(settings: Settings, count: int) -> list[str | None]:
    """None = adresse catch-all aléatoire. Sinon l'adresse Gmail, puis des alias à points."""
    if settings.catchall_domains:
        return [None] * count
    base = settings.imap_user.strip()
    if "@" not in base:
        say(f"{R}Pas de domaine catch-all et pas d'adresse dans IMAP_USER.{X}")
        return []
    say(f"\n{Y}Pas de domaine catch-all.{X}")
    say(f"Le premier compte utilise l'adresse complète : {B}{base}{X}")
    emails: list[str | None] = [base]
    if count == 1:
        return emails
    use_dots = ask(
        "Utiliser des alias avec des points pour les comptes suivants ? (o/n)", "o"
    ).lower().startswith("o")
    if not use_dots:
        say(f"{Y}Un seul compte sera créé (l'adresse complète).{X}")
        return emails
    used = {a.email.lower() for a in list_accounts(settings.runs_dir)}
    used.add(base.lower())
    for _ in range(count - 1):
        alias = dot_alias(base, used)
        used.add(alias.lower())
        emails.append(alias)
    say(f"{D}{len(emails) - 1} alias, par exemple {emails[1]}{X}")
    return emails


def create_accounts(settings: Settings, count: int, threads: int) -> None:
    emails = plan_emails(settings, count)
    if not emails:
        return
    count = len(emails)
    manual = not settings.use_imap
    threads = max(1, min(threads, MAX_THREADS, count))
    if manual and threads > 1:
        say(f"{Y}Lien à coller à la main : un compte à la fois.{X}")
        threads = 1
    say(f"\n{B}Création de {count} compte(s), {threads} en parallèle{X}")
    say(f"{D}{modes(settings)}{X}\n")
    started = time.time()
    ok = 0
    stop = threading.Event()

    def worker(idx: int) -> dict:
        if stop.is_set():
            return {"ok": False, "error": "annulé"}
        tag = f"{D}[{idx:02d}/{count:02d}]{X}"
        t0 = time.time()
        res = run_one(
            settings,
            on_step=lambda s: say(f"{tag} {s}…"),
            ask_link=prompt_link if manual else None,
            email=emails[idx - 1],
        )
        res["_elapsed"] = time.time() - t0
        res["_tag"] = tag
        return res

    def report(res: dict) -> None:
        nonlocal ok
        export_accounts(list_accounts(settings.runs_dir), EXPORT_FILE)
        tag, secs = res.get("_tag", ""), res.get("_elapsed", 0)
        net = f"{res['proxy_kb']} Ko proxy" if res.get("proxy") and "proxy_kb" in res else "direct"
        if res.get("ok"):
            ok += 1
            say(f"{tag} {G}OK{X} {res['email']}  fidélité ✓  {D}({secs:.0f}s, {net}){X}")
        elif res.get("error") != "annulé":
            say(f"{tag} {R}ÉCHEC{X} {res.get('email', '')}  {res.get('error')}  {D}({secs:.0f}s){X}")

    if threads == 1:
        try:
            for i in range(1, count + 1):
                report(worker(i))
        except KeyboardInterrupt:
            say(f"\n{Y}Arrêté.{X}")
    else:
        pool = ThreadPoolExecutor(max_workers=threads)
        futures = []
        try:
            for i in range(1, count + 1):
                futures.append(pool.submit(worker, i))
                if i < count and i <= threads:
                    time.sleep(STAGGER_SEC)
            for fut in as_completed(futures):
                report(fut.result())
        except KeyboardInterrupt:
            stop.set()
            say(f"\n{Y}Arrêt demandé : on termine les comptes déjà en cours…{X}")
            pool.shutdown(wait=True, cancel_futures=True)
        finally:
            pool.shutdown(wait=True)

    total = time.time() - started
    say(f"\n{B}Terminé : {G}{ok}{X}{B}/{count} compte(s) OK en {total:.0f}s{X}")
    n = export_accounts(list_accounts(settings.runs_dir), EXPORT_FILE)
    say(f"{D}{n} compte(s) OK dans {EXPORT_FILE.name}{X}")


def show_accounts(settings: Settings, show_failed: bool = False) -> list[Account]:
    accounts = list_accounts(settings.runs_dir)
    rows = [a for a in accounts if show_failed or a.ok or a.activated]
    hidden = len(accounts) - len(rows)
    if not rows:
        say(f"{Y}Aucun compte.{X}" + (f" {D}({hidden} échec(s) masqué(s)){X}" if hidden else ""))
        return accounts
    say(f"\n{B}{'#':>3}  {'statut':<7} {'pts':>4}  {'email':<42} mot de passe{X}")
    for i, a in enumerate(rows, 1):
        col = G if a.ok else (Y if a.activated else R)
        pts = a.fid_points or ("✓" if a.ok else "")
        say(f"{i:>3}  {col}{a.status:<7}{X} {pts:>4}  {a.email:<42} {a.password}")
    n_ok = sum(a.ok for a in accounts)
    extra = f", {hidden} échec(s) masqué(s)" if hidden else ""
    say(f"\n{D}{n_ok} OK / {len(accounts)} au total{extra}{X}")
    return accounts


def export(settings: Settings) -> None:
    n = export_accounts(list_accounts(settings.runs_dir), EXPORT_FILE)
    say(f"{G}{n} compte(s) OK exportés dans {EXPORT_FILE}{X}  {D}(email;password;points;statut;run_id){X}")


def finish_join(settings: Settings) -> None:
    pending = [a for a in list_accounts(settings.runs_dir) if a.activated and not a.ok]
    if not pending:
        say(f"{Y}Aucun compte activé sans fidélité.{X}")
        return
    for i, a in enumerate(pending, 1):
        say(f"{i:>3}  {a.email}")
    idx = ask_int("Quel compte (0 = annuler)", 0, 0, len(pending))
    if not idx:
        return
    acc = pending[idx - 1]
    say(f"{D}Connexion + adhésion pour {acc.email}…{X}")
    try:
        pts = join_existing(settings, settings.runs_dir / acc.run_id)
        say(f"{G}OK : {pts} points{X}")
    except Exception as exc:
        say(f"{R}Échec : {exc}{X}")


def mailbox(settings: Settings) -> None:
    if not settings.imap_available:
        say(f"{Y}Pas d'identifiants IMAP dans .env (IMAP_USER / IMAP_APP_PASSWORD).{X}")
        return
    needle = ask("Filtre (vide = tous les mails UGC)", "ugc")
    try:
        lines = recent_headers(settings.imap_host, settings.imap_user, settings.imap_password, needle)
    except Exception as exc:
        say(f"{R}IMAP : {exc}{X}")
        return
    for line in lines[-40:]:
        say(f"  {line}")
    say(f"{D}{len(lines)} mail(s) sur 24 h{X}")


def check_config(settings: Settings) -> None:
    say(f"\n{B}Configuration{X}")
    say(f"  Domaines      : {', '.join(settings.catchall_domains)}")
    say(f"  Modes         : {modes(settings)}")
    n = proxy_count(settings.proxy_file)
    say(f"  Proxies       : {G if n else Y}{n}{X} ({settings.proxy_file.name})")
    try:
        bal = get_balance(settings.captcha_provider, settings.captcha_api_key)
        col = G if bal >= 0.5 else Y
        say(f"  Captcha       : {settings.captcha_provider}  solde {col}{bal:.2f} ${X}")
    except Exception as exc:
        say(f"  Captcha       : {R}{exc}{X}")
    if not settings.imap_available:
        say(f"  IMAP          : {Y}non configuré{X}")
        return
    try:
        check_login(settings.imap_host, settings.imap_user, settings.imap_password)
        say(f"  IMAP          : {G}OK{X} ({settings.imap_user})")
    except Exception as exc:
        say(f"  IMAP          : {R}{exc}{X}")


def settings_menu(settings: Settings) -> Settings:
    while True:
        say(f"\n{B}Paramètres (pour cette session){X}")
        say(f"  {modes(settings)}\n")
        say(f"  {C}1{X}) Proxy : {'ON' if settings.use_proxy else 'OFF'}"
            + ("" if settings.proxy_available else f" {D}(aucun proxy dans {settings.proxy_file.name}){X}"))
        say(f"  {C}2{X}) Mail  : {'IMAP auto' if settings.use_imap else 'lien collé à la main'}"
            + ("" if settings.imap_available else f" {D}(pas de mot de passe IMAP){X}"))
        say(f"  {C}0{X}) Retour")
        choice = ask("Choix", "0")
        if choice == "1":
            if not settings.use_proxy and not settings.proxy_available:
                say(f"{R}Impossible : ajoute des proxies dans {settings.proxy_file.name}.{X}")
            else:
                settings = replace(settings, use_proxy=not settings.use_proxy)
        elif choice == "2":
            if not settings.use_imap and not settings.imap_available:
                say(f"{R}Impossible : mets IMAP_USER / IMAP_APP_PASSWORD dans .env.{X}")
            else:
                settings = replace(settings, use_imap=not settings.use_imap)
        else:
            return settings


# ---------------------------------------------------------------- menu


def header(settings: Settings) -> None:
    accounts = list_accounts(settings.runs_dir)
    try:
        bal = f"{get_balance(settings.captcha_provider, settings.captcha_api_key):.2f} $"
    except Exception:
        bal = f"{R}?{X}"
    say(f"\n{C}{B}  UGC · comptes fidélité{X}")
    say(f"{D}  captcha {settings.captcha_provider}: {X}{bal}{D}  ·  comptes OK: {X}{sum(a.ok for a in accounts)}")
    say(f"{D}  {X}{modes(settings)}")


MENU = [
    ("1", "Créer des comptes"),
    ("2", "Voir les comptes"),
    ("3", "Exporter les comptes OK (accounts.csv)"),
    ("4", "Terminer l'adhésion d'un compte activé"),
    ("5", "Boîte mail"),
    ("6", "Vérifier la configuration"),
    ("7", "Paramètres (proxy / mail)"),
    ("0", "Quitter"),
]


def interactive(settings: Settings) -> int:
    while True:
        header(settings)
        say()
        for key, label in MENU:
            say(f"  {C}{key}{X}) {label}")
        choice = ask("\nChoix", "1")
        try:
            if choice == "1":
                n = ask_int("Combien de comptes", 1, 1, 500)
                t = 1
                if settings.use_imap and n > 1:
                    t = ask_int(f"En parallèle (max {MAX_THREADS})", min(3, n), 1, MAX_THREADS)
                create_accounts(settings, n, t)
            elif choice == "2":
                show_failed = ask("Afficher aussi les échecs ? (o/n)", "n").lower().startswith("o")
                show_accounts(settings, show_failed)
            elif choice == "3":
                export(settings)
            elif choice == "4":
                finish_join(settings)
            elif choice == "5":
                mailbox(settings)
            elif choice == "6":
                check_config(settings)
            elif choice == "7":
                settings = settings_menu(settings)
            elif choice in ("0", "q", "quit", "exit"):
                return 0
            else:
                say(f"{R}Choix inconnu.{X}")
        except KeyboardInterrupt:
            say(f"\n{Y}Annulé.{X}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UGC · création de comptes fidélité (sans argument : menu)")
    sub = parser.add_subparsers(dest="cmd")
    p_create = sub.add_parser("create", help="créer des comptes")
    p_create.add_argument("count", type=int, nargs="?", default=1)
    p_create.add_argument("-t", "--threads", type=int, default=3)
    p_create.add_argument("--no-proxy", action="store_true", help="connexion directe")
    p_create.add_argument("--no-imap", action="store_true", help="coller le lien d'activation à la main")
    p_list = sub.add_parser("list", help="lister les comptes")
    p_list.add_argument("-a", "--all", action="store_true", help="inclure les échecs")
    sub.add_parser("export", help="exporter les comptes OK dans accounts.csv")
    sub.add_parser("check", help="vérifier proxies / captcha / IMAP")
    args = parser.parse_args(argv)

    settings = load_settings()
    try:
        if args.cmd == "create":
            if args.no_proxy:
                settings = replace(settings, use_proxy=False)
            if args.no_imap:
                settings = replace(settings, use_imap=False)
            create_accounts(settings, max(1, args.count), args.threads)
        elif args.cmd == "list":
            show_accounts(settings, args.all)
        elif args.cmd == "export":
            export(settings)
        elif args.cmd == "check":
            check_config(settings)
        else:
            return interactive(settings)
    except KeyboardInterrupt:
        say(f"\n{Y}Interrompu.{X}")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
