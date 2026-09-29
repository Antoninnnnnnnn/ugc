import time

import pytest


def test_capmonster_waits_when_busy(monkeypatch):
    from ugc_flow import captcha

    answers = [
        {"errorId": 1, "errorCode": "ERROR_NO_SLOT_AVAILABLE"},
        {"errorId": 1, "errorCode": "ERROR_TOO_MUCH_REQUESTS"},
        {"errorId": 0, "taskId": 42},
    ]
    monkeypatch.setattr(captcha, "_call", lambda url, payload: answers.pop(0))
    monkeypatch.setattr(captcha.time, "sleep", lambda _s: None)
    assert captcha._create("https://x/createTask", "k", {}) == "42"


def test_capmonster_stops_on_real_error(monkeypatch):
    from ugc_flow import captcha

    monkeypatch.setattr(captcha, "_call", lambda url, payload: {"errorId": 1, "errorCode": "ERROR_ZERO_BALANCE"})
    monkeypatch.setattr(captcha.time, "sleep", lambda _s: None)
    with pytest.raises(captcha.CaptchaError, match="ZERO_BALANCE"):
        captcha._create("https://x/createTask", "k", {})


def test_background_token_runs_while_the_caller_continues():
    from ugc_flow.signup import _fresh, _in_background

    started = time.time()
    fut = _in_background(lambda: (time.sleep(0.3), "TOK")[1])
    assert time.time() - started < 0.1
    assert _fresh(fut) == "TOK"


def test_stale_or_failed_token_is_dropped():
    from ugc_flow.signup import _fresh, _in_background

    old = _in_background(lambda: "TOK")
    old.result()
    assert _fresh(old, max_age=-1) is None

    def boom() -> str:
        raise RuntimeError("captcha")

    assert _fresh(_in_background(boom)) is None
    assert _fresh(None) is None
