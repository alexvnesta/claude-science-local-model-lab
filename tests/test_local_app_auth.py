from __future__ import annotations

import importlib.util
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_auth_module():
    path = ROOT / "scripts" / "local_app_auth.py"
    spec = importlib.util.spec_from_file_location("local_app_auth_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, body: bytes, url: str) -> None:
        self.body = body
        self.url = url

    def read(self) -> bytes:
        return self.body

    def geturl(self) -> str:
        return self.url


def test_login_submits_only_the_nonce_confirmation_form(monkeypatch) -> None:
    auth = load_auth_module()
    jar: list[SimpleNamespace] = []

    class Opener:
        def __init__(self) -> None:
            self.calls: list[str | urllib.request.Request] = []

        def open(self, target, timeout: int):
            self.calls.append(target)
            if len(self.calls) == 1:
                return Response(
                    b'<form method="post" action="/unrelated">'
                    b'<input name="wrong" value="value"></form>'
                    b'<form method="post" action="./api/auth/nonce">'
                    b'<input name="nonce" value="nonce-value">'
                    b'<input name="dest" value="/"></form>',
                    "http://localhost:18765/?nonce=nonce-value",
                )
            jar.extend(
                [
                    SimpleNamespace(name="operon_auth", value="auth-value"),
                    SimpleNamespace(name="operon_csrf", value="csrf-value"),
                ]
            )
            return Response(b"", "http://localhost:18765/api/auth/nonce")

    opener = Opener()
    monkeypatch.setattr(
        auth.subprocess,
        "check_output",
        lambda *args, **kwargs: "http://localhost:18765/?nonce=nonce-value\n",
    )
    args = SimpleNamespace(app_cli="claude-science", data_dir="/tmp/data", config="/tmp/config")

    csrf = auth.login(opener, jar, args)

    assert csrf == "csrf-value"
    assert len(opener.calls) == 2
    request = opener.calls[1]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == "http://localhost:18765/api/auth/nonce"
    assert urllib.parse.parse_qs(request.data.decode("utf-8")) == {
        "dest": ["/"],
        "nonce": ["nonce-value"],
    }


def test_login_fails_closed_without_nonce_confirmation_form(monkeypatch) -> None:
    auth = load_auth_module()
    jar: list[SimpleNamespace] = [SimpleNamespace(name="operon_csrf", value="csrf-value")]

    class Opener:
        def open(self, target, timeout: int):
            return Response(
                b'<form method="post" action="/unrelated"></form>',
                "http://localhost:18765/",
            )

    monkeypatch.setattr(
        auth.subprocess,
        "check_output",
        lambda *args, **kwargs: "http://localhost:18765/?nonce=nonce-value\n",
    )
    args = SimpleNamespace(app_cli="claude-science", data_dir="/tmp/data", config="/tmp/config")

    with pytest.raises(RuntimeError, match="nonce confirmation form"):
        auth.login(Opener(), jar, args)


def test_nonce_form_request_rejects_cross_origin_action() -> None:
    auth = load_auth_module()
    response = Response(
        b'<form method="post" action="https://attacker.example/api/auth/nonce">'
        b'<input name="nonce" value="secret-value"></form>',
        "http://localhost:18765/?nonce=secret-value",
    )

    with pytest.raises(RuntimeError, match="nonce confirmation form"):
        auth.nonce_form_request(
            response,
            response.read(),
            "http://localhost:18765/?nonce=secret-value",
        )


def test_nonce_form_request_rejects_cross_origin_redirect() -> None:
    auth = load_auth_module()
    response = Response(
        b'<form method="post" action="/api/auth/nonce">'
        b'<input name="nonce" value="secret-value"></form>',
        "https://attacker.example/login",
    )

    with pytest.raises(RuntimeError, match="nonce confirmation form"):
        auth.nonce_form_request(
            response,
            response.read(),
            "http://localhost:18765/?nonce=secret-value",
        )
