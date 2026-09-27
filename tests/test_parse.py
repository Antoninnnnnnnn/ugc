from ugc_flow.proxy import parse_proxy_line
from ugc_flow.parse import email_validation_ok, parse_forms
from ugc_flow.profile import Person, fill_inscription
from datetime import date


def test_proxy_line():
    url = parse_proxy_line(
        "http://core-residential.evomi.com:1000:user:pass_country-FR_session-ABC_lifetime-5"
    )
    assert url.startswith("http://user:")
    assert "@core-residential.evomi.com:1000" in url


def test_activation_link_from_text_mail():
    from ugc_flow.mailer import activation_link

    body = (
        "[https://www.ugc.fr/dynamique/images/logo/x.png]https://www.ugc.fr\n"
        "[https://www.ugc.fr/monCompteInscriptionAction?method:activationMonCompte=Submit"
        "&page=30058&emailCompte=a%40b.c&key=K123]\n"
    )
    link = activation_link(body)
    assert link is not None
    assert link.endswith("key=K123")


def test_membership_payload():
    from ugc_flow.fidelity import membership_payload

    html = """
    <form id="membershipForm" action="/adhesion.html" method="post">
      <input type="text" name="membership.cardnumber" value=""/>
      <input type="text" name="membership.email" value="x@y.z" readonly/>
      <input type="text" name="membership.firstname"/>
      <input type="text" name="membership.lastname"/>
      <input type="text" name="membership.birthday" class="datepicker"/>
      <input type="text" name="membership.zipCode"/>
      <select name="membership.country"><option value="France">France</option></select>
      <input type="checkbox" name="membership.newsletter" value="true"/>
      <input type="hidden" name="__checkbox_membership.newsletter" value="true"/>
      <input type="checkbox" name="membership.cgu" value="true"/>
      <input type="hidden" name="__checkbox_membership.cgu" value="true"/>
    </form>
    """
    person = Person(
        email="x@y.z",
        password="p",
        first_name="Ada",
        last_name="Martin",
        birth=date(1990, 5, 2),
        phone="",
        postal="75011",
        city="",
    )
    data = membership_payload(html, person)
    assert data["membership.birthday"] == "02/05/90"
    assert data["membership.cgu"] == "true"
    assert data["membership.newsletter"] == "true"
    assert data["method:join"] == "Submit"


def test_check_pasted_link():
    from ugc_flow.mailer import check_pasted_link

    good = (
        "https://www.ugc.fr/monCompteInscriptionAction?method:activationMonCompte=Submit"
        "&page=30058&emailCompte=a@b.site&key=K1&mtm_campaign=x"
    )
    assert check_pasted_link(f"  <{good}>  ", "a@b.site")[0] == good
    assert check_pasted_link(good, "other@b.site")[0] is None
    assert check_pasted_link("https://www.ugc.fr/contact.html", "a@b.site")[0] is None
    assert check_pasted_link("bonjour", "a@b.site")[0] is None
    mj = "http://n11u.mjt.lu/lnk/CAAAC/2/abc/aHR0cHM6Ly93d3c"
    assert check_pasted_link(mj, "a@b.site")[0] == mj


def test_mail_presets(monkeypatch, tmp_path):
    from ugc_flow import config
    from ugc_flow.mailer import resolve_host

    assert resolve_host("a@outlook.com", "imap") == ("outlook.office365.com", 993)
    assert resolve_host("a@orange.fr", "pop3") == ("pop.orange.fr", 995)
    assert resolve_host("a@exemple.fr", "imap", "mail.exemple.fr") == ("mail.exemple.fr", 993)

    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("PROXY_FILE", str(tmp_path / "none.txt"))
    monkeypatch.setenv("IMAP_USER", "")
    monkeypatch.setenv("IMAP_APP_PASSWORD", "")
    monkeypatch.setenv("MAIL_USER", "a@yahoo.fr")
    monkeypatch.setenv("MAIL_PASSWORD", "secret")
    monkeypatch.setenv("MAIL_PROTOCOL", "pop3")
    monkeypatch.delenv("USE_IMAP", raising=False)
    s = config.load_settings()
    assert s.mail_protocol == "pop3"
    assert s.endpoint() == ("pop.mail.yahoo.com", 995)


def test_settings_modes(tmp_path, monkeypatch):
    from ugc_flow import config

    monkeypatch.setattr(config, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("PROXY_FILE", str(tmp_path / "none.txt"))
    monkeypatch.setenv("IMAP_USER", "")
    monkeypatch.setenv("IMAP_APP_PASSWORD", "")
    s = config.load_settings()
    assert s.proxy_source is None and not s.use_imap

    (tmp_path / "p.txt").write_text("http://h:1:u:p\n", encoding="utf-8")
    monkeypatch.setenv("PROXY_FILE", str(tmp_path / "p.txt"))
    monkeypatch.setenv("IMAP_USER", "x@gmail.com")
    monkeypatch.setenv("IMAP_APP_PASSWORD", "abcd")
    s = config.load_settings()
    assert s.proxy_source is not None and s.use_imap

    monkeypatch.setenv("USE_PROXY", "0")
    monkeypatch.setenv("USE_IMAP", "0")
    s = config.load_settings()
    assert s.proxy_source is None and not s.use_imap


def test_dot_alias_same_mailbox():
    from ugc_flow.profile import dot_alias, gmail_base

    base = "prenomnom@gmail.com"
    used = {base}
    alias = dot_alias(base, used)
    assert alias != base
    assert "." in alias.split("@")[0]
    assert gmail_base(alias) == base
    again = dot_alias(base, used | {alias})
    assert again != alias


def test_email_ok_empty():
    ok, msg = email_validation_ok("")
    assert ok


def test_email_reject():
    ok, _ = email_validation_ok("<div id='errorField'>Cette adresse est déjà utilisée</div>")
    assert not ok


def test_required_false_and_skip_birthday():
    html = """
    <form id="inscription_form" action="monCompteInscriptionAction!inscription" method="post">
      <input type="hidden" name="page" value="30058"/>
      <input type="text" name="inscriptionBean.email" required="true"/>
      <input type="password" name="inscriptionBean.password" required="true"/>
      <input type="password" name="inscriptionBean.confirm" required="true"/>
      <input type="checkbox" name="inscriptionBean.checked" required/>
      <input type="checkbox" name="inscriptionBean.seizeAns" required/>
      <input type="checkbox" name="inscriptionBean.moinsSeizeAns"/>
      <input type="text" name="inscriptionBean.tutorEmail" required="false"/>
      <input type="text" name="inscriptionBean.birthday" class="datepicker" required="false"/>
    </form>
    """
    forms = parse_forms(html, "https://www.ugc.fr")
    person = Person(
        email="a@b.c",
        password="UgAbcdefg1!",
        first_name="Ada",
        last_name="Martin",
        birth=date(1990, 5, 2),
        phone="0600000000",
        postal="75011",
        city="Paris",
    )
    data = fill_inscription(forms[0], person)
    assert "inscriptionBean.birthday" not in data
    assert "inscriptionBean.tutorEmail" not in data
    assert "inscriptionBean.moinsSeizeAns" not in data
    assert data["inscriptionBean.seizeAns"] == "on"
    assert data["inscriptionBean.checked"] == "on"
    assert data["inscriptionBean.confirm"] == person.password


def test_append_account(tmp_path):
    from ugc_flow.runner import Account, append_account

    csv_path = tmp_path / "accounts.csv"
    acc1 = Account(
        run_id="run1", email="a@b.c", password="pwd", ok=True, fid_points=100, activated=True, error=""
    )
    acc2 = Account(
        run_id="run2", email="x@y.z", password="pwd", ok=True, fid_points=200, activated=True, error=""
    )
    append_account(acc1, csv_path)
    append_account(acc2, csv_path)

    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0] == "email;password;points;statut;run_id"
    assert "a@b.c;pwd;100;OK;run1" in lines[1]
    assert "x@y.z;pwd;200;OK;run2" in lines[2]


def test_proxy_round_robin_and_caching(tmp_path):
    from ugc_flow.proxy import pick_proxy

    f = tmp_path / "proxies.txt"
    f.write_text("http://1.1.1.1:80:u1:p1\nhttp://2.2.2.2:80:u2:p2\n", encoding="utf-8")

    p1 = pick_proxy(f)
    p2 = pick_proxy(f)
    p3 = pick_proxy(f)

    assert p1 != p2
    assert p1 == p3
