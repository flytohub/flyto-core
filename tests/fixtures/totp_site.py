# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""A throwaway site whose second factor is a real TOTP.

`workflows/totp_login_action.yaml` can only be proven end to end against
something that actually rejects a wrong code, so this serves the shape a staff
portal has: credentials, then a one-time password, then an action that the site
records and confirms.

The TOTP check here is written against RFC 6238 directly rather than by calling
``crypto.totp``. A site that validated codes with the same code that generates
them would agree with itself no matter what either side did.
"""
import base64
import hashlib
import hmac
import http.server
import json
import struct
import threading
import time
import uuid
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

USERNAME = "chester"
PASSWORD = "correct horse battery staple"
# RFC 6238's own SHA1 seed. Not a credential for anything.
SECRET_B32 = base64.b32encode(b"12345678901234567890").decode()


def expected_code(at: Optional[float] = None, digits: int = 6, period: int = 30) -> str:
    """RFC 6238, implemented independently of the module under test."""
    counter = int((time.time() if at is None else at) // period)
    key = base64.b32decode(SECRET_B32)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title></head>
<body><h1>{title}</h1>{body}</body></html>"""

_LOGIN = """
<form method="post" action="/login">
  <input name="user" placeholder="Employee ID" autocomplete="username">
  <input name="pass" type="password" placeholder="Password" autocomplete="current-password">
  <button type="submit">Sign in</button>
</form>{error}"""

_OTP = """
<form method="post" action="/otp">
  <input name="code" autocomplete="one-time-code" inputmode="numeric" maxlength="6"
         placeholder="6-digit code">
  <button type="submit">Verify</button>
</form>{error}"""

_ATTENDANCE_READY = """
<div id="attendance">
  <p>Signed in as {user}.</p>
  <button id="clock-in" onclick="document.getElementById('punch').submit()">Clock in</button>
  <form id="punch" method="post" action="/punch"></form>
</div>"""

_ATTENDANCE_DONE = """
<div id="attendance">
  <p>Signed in as {user}.</p>
  <div id="punch-confirmation">Clocked in at {stamp}</div>
</div>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    sessions: Dict[str, Dict[str, object]] = {}
    # Every punch the site actually recorded, across all sessions. A test must
    # assert against what the site registered, not against what the script
    # believes it clicked.
    punches: list = []

    def log_message(self, *args):  # keep the test output readable
        pass

    # ---- helpers -------------------------------------------------------
    def _session(self) -> Optional[Dict[str, object]]:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sid":
                return self.sessions.get(value)
        return None

    def _send(self, status: int, title: str, body: str, cookie: Optional[str] = None):
        page = _PAGE.format(title=title, body=body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        if cookie:
            self.send_header("Set-Cookie", f"sid={cookie}; Path=/")
        self.end_headers()
        self.wfile.write(page)

    def _redirect(self, location: str, cookie: Optional[str] = None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", f"sid={cookie}; Path=/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _form(self) -> Dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode()
        return {k: v[0] for k, v in parse_qs(raw).items()}

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        session = self._session()
        if path in ("/", "/login"):
            self._send(200, "Sign in", _LOGIN.format(error=""))
        elif path == "/otp":
            if not session or session.get("stage") != "otp":
                return self._redirect("/login")
            self._send(200, "Two-step verification", _OTP.format(error=""))
        elif path == "/attendance":
            if not session or session.get("stage") != "in":
                return self._redirect("/login")
            if session.get("punched_at"):
                body = _ATTENDANCE_DONE.format(user=USERNAME, stamp=session["punched_at"])
            else:
                body = _ATTENDANCE_READY.format(user=USERNAME)
            self._send(200, "Attendance", body)
        elif path == "/state":  # test introspection, never used by the workflow
            self.send_response(200)
            payload = json.dumps({"punches": list(self.punches)}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self._send(404, "Not found", "<p>no such page</p>")

    def do_POST(self):
        path = urlparse(self.path).path
        form = self._form()
        session = self._session()
        if path == "/login":
            if form.get("user") == USERNAME and form.get("pass") == PASSWORD:
                sid = uuid.uuid4().hex
                self.sessions[sid] = {"stage": "otp"}
                return self._redirect("/otp", cookie=sid)
            return self._send(200, "Sign in", _LOGIN.format(
                error='<p id="login-error">Wrong employee ID or password.</p>'))
        if path == "/otp":
            if not session or session.get("stage") != "otp":
                return self._redirect("/login")
            # Accept the previous window too: a code generated a moment ago is
            # still legitimate, which is how real servers behave.
            now = time.time()
            if form.get("code") in {expected_code(now), expected_code(now - 30)}:
                session["stage"] = "in"
                return self._redirect("/attendance")
            return self._send(200, "Two-step verification", _OTP.format(
                error='<p id="otp-error">That code is not valid.</p>'))
        if path == "/punch":
            if not session or session.get("stage") != "in":
                return self._redirect("/login")
            if not session.get("punched_at"):
                session["punched_at"] = time.strftime("%H:%M:%S")
                self.punches.append(session["punched_at"])
            return self._redirect("/attendance")
        self._send(404, "Not found", "<p>no such page</p>")


class TotpSite:
    """Serve the site on 127.0.0.1 for the life of a ``with`` block."""

    def __init__(self, port: int = 8080):
        self.port = port
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "TotpSite":
        _Handler.sessions = {}
        _Handler.punches = []
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)
