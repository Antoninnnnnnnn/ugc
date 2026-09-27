import imaplib

import pytest

from ugc_flow.mailer import Pop3Mailbox, _PollingMailbox, _is_auth_failure, pop_candidates


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
