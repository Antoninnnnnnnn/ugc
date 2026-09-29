import imaplib

import pytest

from ugc_flow.mailer import Pop3Mailbox, _PollingMailbox, _is_auth_failure, pop_candidates


def test_uid_bodies_reads_each_message():
    from ugc_flow.mailer import _uid_bodies

    fetched = [
        (b"1 (UID 10 BODY[] {3}", b"aaa"),
        b")",
        (b"2 (UID 11 BODY[] {3}", b"bbb"),
        b")",
    ]
    assert _uid_bodies(fetched) == [("10", b"aaa"), ("11", b"bbb")]


def test_pop_candidates_skips_already_read():
    lines = [b"1 aaa", b"2 bbb", b"", b"3 ccc", b"4 ddd"]
    got = pop_candidates(lines, {"bbb"}, limit=2)
    assert got == [(3, "ccc"), (4, "ddd")]


def test_auth_failure_is_not_a_network_blip():
    assert _is_auth_failure(imaplib.IMAP4.error("AUTHENTICATIONFAILED Invalid credentials"))
    assert not _is_auth_failure(imaplib.IMAP4.abort("socket error: timed out"))
    assert not _is_auth_failure(TimeoutError("timed out"))


def test_poll_retries_a_blip_then_returns_the_link():
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = "a@b.site"
    msg["Subject"] = "UGC"
    msg.set_content("https://www.ugc.fr/go?method:activationMonCompte=Submit&emailCompte=a@b.site&key=K")

    class Box(_PollingMailbox):
        def __init__(self):
            super().__init__("h", "u", "p", "a@b.site", timeout_sec=5, pause_sec=0.01)
            self.calls = 0

        def _fetch(self, seen):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("coupure")
            return [("1", msg)]

    box = Box()
    box.start()
    try:
        link = box.wait_link()
    finally:
        box.stop()
    assert link and "activationMonCompte" in link
    assert box.calls == 3


def test_poll_stops_on_bad_password():
    class Box(_PollingMailbox):
        def __init__(self):
            super().__init__("h", "u", "p", "a@b.site", timeout_sec=5, pause_sec=0.01)
            self.calls = 0

        def _fetch(self, seen):
            self.calls += 1
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED Invalid credentials")

    box = Box()
    box.start()
    try:
        with pytest.raises(RuntimeError, match="AUTHENTICATIONFAILED"):
            box.wait_link()
    finally:
        box.stop()
    assert box.calls == 1


class _FakePop:
    def __init__(self, lines):
        self.lines = lines
        self.retrs: list[int] = []
        self.tops: list[int] = []

    def uidl(self):
        return b"+OK", self.lines, 0

    def top(self, num, _n):
        self.tops.append(num)
        subject = b"Subject: autre\r\nTo: personne@x.com\r\n\r\n"
        if num == 2:
            subject = b"Subject: UGC - Confirmez\r\nTo: a@b.site\r\n\r\n"
        return b"+OK", subject.splitlines(), 0

    def retr(self, num):
        self.retrs.append(num)
        body = (
            b"To: a@b.site\r\nSubject: UGC\r\n\r\n"
            b"https://www.ugc.fr/go?method:activationMonCompte=Submit&key=K"
        )
        return b"+OK", body.splitlines(), 0

    def quit(self):
        return None


def test_pop_downloads_a_matching_mail_once(monkeypatch):
    fake = _FakePop([b"1 aaa", b"2 bbb"])
    monkeypatch.setattr("ugc_flow.mailer._login_pop", lambda *args: fake)
    box = Pop3Mailbox("pop.example", "u", "p", "a@b.site", timeout_sec=5)

    first = box._fetch(set())
    assert [key for key, _msg in first] == ["aaa", "bbb"]
    assert fake.retrs == [2]

    again = box._fetch({"aaa", "bbb"})
    assert again == []
    assert fake.retrs == [2]


def test_highest_uid_reads_the_last_message():
    from ugc_flow.mailer import _highest_uid

    assert _highest_uid([b"12 (UID 500)", b")"]) == 500
    assert _highest_uid([(b"12 (UID 500 BODY[] {1}", b"x"), b")"]) == 500


def test_shared_imap_reads_only_mail_arrived_after_the_cursor():
    import imaplib
    from ugc_flow.mailer import SharedMailbox

    class Fake:
        def __init__(self):
            self.highest = 500
            self.new: dict[int, tuple[bytes, bytes]] = {}
            self.ranges: list[str] = []

        def select(self, folder, readonly=False):
            if folder != "INBOX":
                raise imaplib.IMAP4.error("absent")
            return "OK", [b"1"]

        def uid(self, cmd, spec, query):
            assert cmd == "FETCH"
            if spec == "*":
                return "OK", [f"9 (UID {self.highest})".encode()]
            self.ranges.append(spec)
            start = int(str(spec).split(":")[0])
            if "HEADER.FIELDS" in query:
                items = []
                for uid in sorted(self.new):
                    if uid < start:
                        continue
                    header, _body = self.new[uid]
                    items.append((f"{uid} (UID {uid} BODY[HEADER.FIELDS (FROM SUBJECT)] {{1}}".encode(), header))
                    items.append(b")")
                return "OK", items or [None]
            items = []
            for uid in (int(part) for part in str(spec).split(",")):
                _header, body = self.new[uid]
                items.append((f"{uid} (UID {uid} BODY[] {{1}}".encode(), body))
                items.append(b")")
            return "OK", items

    header = b"From: UGC <moncompte@ugcmailing.fr>\r\nSubject: UGC - Confirmez votre inscription\r\n\r\n"
    body = (
        b"From: UGC <moncompte@ugcmailing.fr>\r\nSubject: UGC - Confirmez\r\n\r\n"
        b"https://www.ugc.fr/x?method:activationMonCompte=Submit&emailCompte=u1@exemple.site&key=K"
    )
    fake = Fake()
    fake.new[501] = (header, body)
    shared = SharedMailbox("imap", "h", "u", "p", pause_sec=0.01)
    shared._imap = fake
    shared.register("u1@exemple.site")

    shared._fetch_imap(set())
    assert "key=K" in shared._links["u1@exemple.site"]
    assert fake.ranges[0] == "401:*"

    shared._links.clear()
    fake.new.clear()
    shared._fetch_imap(set())
    assert "502:*" in fake.ranges


def test_xoauth2_string_matches_the_sasl_format():
    from ugc_flow.mailer import uses_xoauth2, xoauth2_string

    assert xoauth2_string("a@outlook.com", "TOK") == b"user=a@outlook.com\x01auth=Bearer TOK\x01\x01"
    assert uses_xoauth2("outlook.office365.com", "a@outlook.fr")
    assert uses_xoauth2("", "a@hotmail.com")
    assert not uses_xoauth2("imap.gmail.com", "a@gmail.com")


def test_outlook_imap_uses_xoauth2_not_the_password(monkeypatch):
    from ugc_flow.mailer import _login_imap

    class Fake:
        def __init__(self):
            self.mech = ""
            self.blob = b""

        def authenticate(self, mech, callback):
            self.mech = mech
            self.blob = callback(b"")

        def login(self, user, password):
            raise AssertionError(password)

    box = Fake()
    monkeypatch.setattr("ugc_flow.mailer.imaplib.IMAP4_SSL", lambda *a, **k: box)
    monkeypatch.setattr("ugc_flow.mailer.outlook_access_token", lambda *a, **k: "TOK")
    _login_imap("outlook.office365.com", "a@outlook.com", "motdepasse")
    assert box.mech == "XOAUTH2"
    assert box.blob == b"user=a@outlook.com\x01auth=Bearer TOK\x01\x01"


def test_outlook_pop3_is_refused():
    from ugc_flow.mailer import _login_pop

    with pytest.raises(RuntimeError, match="POP3"):
        _login_pop("outlook.office365.com", "a@hotmail.fr", "secret")


def test_shared_mailbox_delivers_to_multiple_clients():
    from email.message import EmailMessage
    from ugc_flow.mailer import SharedMailbox

    shared = SharedMailbox("imap", "h", "u", "p", pause_sec=0.01)

    msg1 = EmailMessage()
    msg1["To"] = "client1@b.site"
    msg1["Subject"] = "UGC 1"
    msg1.set_content("https://www.ugc.fr/go?method:activationMonCompte=Submit&emailCompte=client1@b.site&key=K1")

    msg2 = EmailMessage()
    msg2["To"] = "client2@b.site"
    msg2["Subject"] = "UGC 2"
    msg2.set_content("https://www.ugc.fr/go?method:activationMonCompte=Submit&emailCompte=client2@b.site&key=K2")

    shared._fetch_messages = lambda seen: [("1", msg1), ("2", msg2)]

    c1 = shared.client("client1@b.site", timeout_sec=2)
    c2 = shared.client("client2@b.site", timeout_sec=2)
    c1.start()
    c2.start()
    shared.start()
    try:
        link1 = c1.wait_link()
        link2 = c2.wait_link()
    finally:
        c1.stop()
        c2.stop()
        shared.stop()

    assert link1 and "key=K1" in link1
    assert link2 and "key=K2" in link2


def test_shared_mailbox_stops_on_auth_failure():
    from ugc_flow.mailer import SharedMailbox

    shared = SharedMailbox("imap", "h", "u", "p", pause_sec=0.01)

    def raise_auth(seen):
        raise imaplib.IMAP4.error("AUTHENTICATIONFAILED Invalid credentials")

    shared._fetch_messages = raise_auth

    c = shared.client("a@b.site", timeout_sec=2)
    c.start()
    shared.start()
    try:
        with pytest.raises(RuntimeError, match="AUTHENTICATIONFAILED"):
            c.wait_link()
    finally:
        c.stop()
        shared.stop()
