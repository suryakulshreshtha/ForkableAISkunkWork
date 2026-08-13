"""A tiny demo application, served from the standard library.

Without a target there is no end-to-end test, and an air-gapped machine cannot
reach a staging environment. So the agent ships its own: a two-page login flow
on 127.0.0.1 with no framework, no build step and no external assets.

The interesting part is ``?ui=v2``. That variant renames ids, drops
``data-testid`` hooks and rewords labels exactly the way a front-end refactor
does - which is what makes the self-healing demo real rather than staged.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USERS = {"demo": "secret123", "qa.lead": "playwright"}

STYLE = """
:root{--ink:#101a2b;--muted:#5b6880;--line:#dfe3ea;--accent:#0f6e5c;--bad:#a3132b;--bg:#fbfbf9}
*{box-sizing:border-box}
body{margin:0;font:16px/1.55 "Inter",system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--ink);color:#f4f6f8;padding:14px 24px;display:flex;gap:14px;align-items:baseline}
header b{letter-spacing:.14em;text-transform:uppercase;font-size:12px}
header span{font-size:12px;color:#9fb0c6;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
main{max-width:640px;margin:48px auto;padding:0 24px}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}
p.lede{color:var(--muted);margin:0 0 28px}
form{display:grid;gap:16px;border:1px solid var(--line);border-radius:10px;padding:24px;background:#fff}
label{display:block;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
input[type=text],input[type=password]{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:7px;font-size:15px}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{background:var(--accent);color:#fff;border:0;border-radius:7px;padding:12px 18px;font-size:15px;cursor:pointer}
button:hover{filter:brightness(1.08)}
.row{display:flex;gap:10px;align-items:center}
.error{border-left:3px solid var(--bad);background:#fdf2f4;color:var(--bad);padding:10px 14px;border-radius:4px;font-size:14px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);font-size:14px}
th{background:#f2f4f7;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
tr:last-child td{border-bottom:0}
.meta{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--muted);margin-top:22px}
a{color:var(--accent)}
"""


def _page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{STYLE}</style></head><body>"
        "<header><b>Forkable Ops</b><span>offline demo target</span></header>"
        f"<main>{body}</main></body></html>"
    ).encode()


def login_form(variant: str, error: str = "") -> str:
    banner = f"<div class='error' data-testid='login-error' role='alert'>{error}</div>" if error else ""
    if variant == "v2":
        # A refactor happened: ids churned, test hooks gone, labels reworded.
        return f"""
        <h1>Sign in</h1><p class='lede'>Operations console for the overnight batch.</p>
        {banner}
        <form method='post' action='/login?ui=v2'>
          <div>
            <label for='usr_1a2b'>User name</label>
            <input type='text' id='usr_1a2b' name='usr_1a2b' placeholder='Enter user name' autocomplete='off'>
          </div>
          <div>
            <label for='pw_9x77'>Passphrase</label>
            <input type='password' id='pw_9x77' name='pw_9x77' placeholder='Enter passphrase'>
          </div>
          <div class='row'><button type='submit'>Log in</button>
            <a href='/login'>use the stable UI</a></div>
        </form>"""
    return """
        <h1>Sign in</h1><p class='lede'>Operations console for the overnight batch.</p>
        {banner}
        <form method='post' action='/login'>
          <div>
            <label for='username'>Username</label>
            <input type='text' id='username' name='username' data-testid='username'
                   placeholder='demo' autocomplete='off'>
          </div>
          <div>
            <label for='password'>Password</label>
            <input type='password' id='password' name='password' data-testid='password'
                   placeholder='secret123'>
          </div>
          <div class='row'><button type='submit' id='login' data-testid='login'>Log in</button>
            <a href='/login?ui=v2'>preview the refactored UI</a></div>
        </form>""".replace("{banner}", banner)


def dashboard_page(user: str) -> str:
    rows = "".join(
        f"<tr><td>{job}</td><td>{status}</td><td>{took}</td></tr>"
        for job, status, took in (
            ("nightly-ingest", "completed", "4m 02s"),
            ("index-rebuild", "completed", "1m 47s"),
            ("report-mailer", "queued", "-"),
        )
    )
    return f"""
        <h1>Welcome, {user}</h1>
        <p class='lede' data-testid='welcome'>You are signed in. Three jobs ran in the last window.</p>
        <table><thead><tr><th>Job</th><th>Status</th><th>Duration</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p class='meta'><a href='/logout' data-testid='logout'>Sign out</a></p>"""


@dataclass
class _Session:
    user: str


class _Handler(BaseHTTPRequestHandler):
    sessions: dict[str, _Session] = {}
    server_version = "ForkableDemo/1.0"

    # -- helpers -------------------------------------------------------
    def log_message(self, *args) -> None:  # keep test output clean
        if os.environ.get("FORKABLE_APP_VERBOSE"):
            super().log_message(*args)

    def _variant(self, query: dict[str, list]) -> str:
        return (query.get("ui", [os.environ.get("FORKABLE_UI_VARIANT", "v1")])[0] or "v1").lower()

    def _session(self) -> _Session | None:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sid":
                return self.sessions.get(value)
        return None

    def _send(self, status: int, body: bytes, headers: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, headers: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()

    # -- routes --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"
        variant = self._variant(query)

        if route == "/health":
            payload = json.dumps({"status": "ok", "variant": variant}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if route == "/":
            body = (
                "<h1>Forkable Ops</h1><p class='lede'>An offline target for the "
                "ForkableAIAgent demo.</p><p><a href='/login' data-testid='go-login'>"
                "Open the sign-in page</a></p>"
                "<p class='meta'>Accounts: demo / secret123</p>"
            )
            self._send(200, _page("Forkable Ops", body))
            return

        if route == "/login":
            error = {"auth": "Sign in to continue.", "bad": "Invalid username or password."}.get(
                (query.get("error", [""])[0]), ""
            )
            self._send(200, _page("Sign in - Forkable Ops", login_form(variant, error)))
            return

        if route == "/dashboard":
            session = self._session()
            if session is None:
                self._redirect("/login?error=auth")
                return
            self._send(200, _page("Dashboard - Forkable Ops", dashboard_page(session.user)))
            return

        if route == "/logout":
            self._redirect("/", (("Set-Cookie", "sid=; Max-Age=0; Path=/"),))
            return

        self._send(404, _page("Not found", "<h1>404</h1><p class='lede'>No such page.</p>"))

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        variant = self._variant(query)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

        if parsed.path.rstrip("/") != "/login":
            self._send(404, _page("Not found", "<h1>404</h1>"))
            return

        if variant == "v2":
            user = form.get("usr_1a2b", "")
            password = form.get("pw_9x77", "")
        else:
            user = form.get("username", "")
            password = form.get("password", "")

        if USERS.get(user.strip()) == password:
            sid = secrets.token_urlsafe(16)
            _Handler.sessions[sid] = _Session(user=user.strip())
            self._redirect("/dashboard", (("Set-Cookie", f"sid={sid}; Path=/; HttpOnly"),))
            return

        suffix = "&ui=v2" if variant == "v2" else ""
        self._redirect(f"/login?error=bad{suffix}")


class DemoApp:
    """Threaded demo server usable as a context manager or a daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8799) -> None:
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> DemoApp:
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None

    def serve_forever(self) -> None:
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = self._httpd.server_address[1]
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._httpd.server_close()

    def __enter__(self) -> DemoApp:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
