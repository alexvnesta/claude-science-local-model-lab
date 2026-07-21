#!/usr/bin/env python3
"""Authenticate local API helpers through a Claude Science login URL."""

from __future__ import annotations

import html.parser
import http.cookiejar
import subprocess
import urllib.parse
import urllib.request
from typing import Any


class LoginFormParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form":
            self.current = {
                "action": values.get("action") or "",
                "method": (values.get("method") or "get").lower(),
                "fields": {},
            }
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and values.get("name"):
            self.current["fields"][str(values["name"])] = values.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.current = None


def cookie_value(jar: http.cookiejar.CookieJar, name: str) -> str | None:
    for cookie in jar:
        if cookie.name == name:
            return str(cookie.value)
    return None


def nonce_form_request(
    response: Any,
    body: bytes,
    login_url: str,
) -> urllib.request.Request:
    parser = LoginFormParser()
    parser.feed(body.decode("utf-8", "replace"))
    login_origin = urllib.parse.urlparse(login_url)
    for form in parser.forms:
        action = urllib.parse.urljoin(response.geturl(), form["action"])
        action_url = urllib.parse.urlparse(action)
        if (
            form["method"] != "post"
            or action_url.scheme != login_origin.scheme
            or action_url.netloc != login_origin.netloc
            or action_url.path != "/api/auth/nonce"
        ):
            continue
        return urllib.request.Request(
            action,
            data=urllib.parse.urlencode(form["fields"]).encode("utf-8"),
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
    raise RuntimeError("Claude Science login did not expose the nonce confirmation form")


def login(
    opener: urllib.request.OpenerDirector,
    jar: http.cookiejar.CookieJar,
    args: Any,
) -> str:
    url_output = subprocess.check_output(
        [
            args.app_cli,
            "url",
            "--data-dir",
            args.data_dir,
            "--config",
            args.config,
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    login_url = url_output.splitlines()[0].strip()
    response = opener.open(login_url, timeout=10)
    body = response.read()

    if cookie_value(jar, "operon_auth") is None:
        opener.open(nonce_form_request(response, body, login_url), timeout=10).read()

    if cookie_value(jar, "operon_auth") is None:
        raise RuntimeError("Claude Science login did not set operon_auth")
    csrf = cookie_value(jar, "operon_csrf")
    if csrf is None:
        raise RuntimeError("Claude Science login did not set operon_csrf")
    return csrf
