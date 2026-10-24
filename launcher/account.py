"""Account services for the Open Vanilla launcher.

    verify_login(user, password, host, port)   the 1.12.1 SRP6 handshake against the realm's
                                                login server, exactly as the game does it
    register(portal, user, password)            POST {portal}/api/register
    change_password(portal, user, old, new)     POST {portal}/api/change-password
    protect(text) / unprotect(blob)             Windows DPAPI, so a remembered password is only
                                                readable by this Windows user on this PC

Nothing here talks to the database directly; sign-up and password changes go through the realm's
web portal, which owns the account table.
"""
import base64
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import sys
import urllib.error
import urllib.request

N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
G = 7
USER_RE = re.compile(r"^[A-Za-z0-9]{3,16}$")


def check_username(user):
    if not USER_RE.match(user or ""):
        return "Account names are 3–16 letters or numbers (no spaces or symbols)."
    return None


def check_password(pw):
    if not pw or len(pw) < 4:
        return "Passwords need at least 4 characters."
    if len(pw) > 16:
        # The 1.12.1 login screen only takes 16 characters, so a longer one can never be typed in game.
        return "Passwords can be at most 16 characters (the game's login screen limit)."
    try:
        pw.encode("ascii")
    except UnicodeEncodeError:
        return "Passwords can only use plain keyboard characters (A–Z, 0–9, symbols)."
    return None


# ---------------------------------------------------------------- SRP6 login check

def _sha(*parts):
    h = hashlib.sha1()  # nosec B324 - SHA1 is mandated by the 1.12.1 SRP6 login protocol
    for p in parts:
        h.update(p)
    return h.digest()


def _le(n, size=32):
    return n.to_bytes(size, "little")


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("the login server closed the connection")
        buf += chunk
    return buf


LOGON_ERRORS = {
    0x03: "This account has been banned.",
    0x04: "Unknown account name or wrong password.",
    0x05: "Unknown account name or wrong password.",
    0x06: "This account is already logged in. Wait a minute and try again.",
    0x07: "No game time on this account.",
    0x08: "The login server is busy. Try again shortly.",
    0x09: "This client version is not accepted by the realm.",
    0x0C: "This account is temporarily suspended.",
}


def verify_login(username, password, host, port=3724, timeout=6.0):
    """Log in to the realm's login server (realmd) and check the password proof.

    Returns (ok, message). Only the login server is touched; no game session is opened, so it
    does not kick a character that is already in the world.
    """
    user = username.strip().upper().encode("ascii")
    pwd = password.upper().encode("ascii")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            body = (b"WoW\x00" + bytes([1, 12, 1]) + struct.pack("<H", 5875) +
                    b"68x\x00" + b"niW\x00" + b"SUne" + struct.pack("<I", 0) +
                    socket.inet_aton("127.0.0.1") + bytes([len(user)]) + user)
            sock.sendall(bytes([0x00, 0x03]) + struct.pack("<H", len(body)) + body)

            cmd, _unk, result = _recv_exact(sock, 3)
            if cmd != 0x00:
                return False, "The login server sent an unexpected reply."
            if result != 0:
                return False, LOGON_ERRORS.get(result, f"Login refused (code {result:#04x}).")
            B = int.from_bytes(_recv_exact(sock, 32), "little")
            g = int.from_bytes(_recv_exact(sock, _recv_exact(sock, 1)[0]), "little")
            n = int.from_bytes(_recv_exact(sock, _recv_exact(sock, 1)[0]), "little")
            salt = _recv_exact(sock, 32)
            _recv_exact(sock, 16)
            flags = _recv_exact(sock, 1)[0]
            if flags:
                return False, "This account needs an authenticator, which the launcher can't do yet. Log in in-game."
            if g != G or n != N:
                return False, "The login server uses unexpected parameters."

            a = int.from_bytes(os.urandom(32), "little") % N
            A = pow(G, a, N)
            Ab, Bb = _le(A), _le(B)
            x = int.from_bytes(_sha(salt, _sha(user + b":" + pwd)), "little")
            u = int.from_bytes(_sha(Ab, Bb), "little")
            S = pow((B - 3 * pow(G, x, N)) % N, a + u * x, N)
            Sb = _le(S)
            even, odd = _sha(Sb[0::2]), _sha(Sb[1::2])
            K = bytes(b for pair in zip(even, odd) for b in pair)
            hn, hg = _sha(_le(N)), _sha(_le(G, 1))
            M1 = _sha(bytes(x1 ^ x2 for x1, x2 in zip(hn, hg)), _sha(user), salt, Ab, Bb, K)

            sock.sendall(bytes([0x01]) + Ab + M1 + bytes(20) + bytes([0, 0]))
            cmd, result = _recv_exact(sock, 2)
            if cmd != 0x01:
                return False, "The login server sent an unexpected reply."
            if result != 0:
                return False, LOGON_ERRORS.get(result, "Unknown account name or wrong password.")
            M2 = _recv_exact(sock, 20)
            if M2 != _sha(Ab, M1, K):
                return False, "The login server's proof did not match. Try again."
            return True, "Signed in."
    except socket.timeout:
        return None, "The login server did not answer in time."
    except OSError as e:
        return None, f"Can't reach the login server ({host}:{port}). {e.strerror or e}"


# ---------------------------------------------------------------- portal API

def _post(url, payload, timeout=20):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "OpenVanilla-Launcher"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {"message": f"The portal answered HTTP {e.code}."}
    except ssl.SSLError as e:
        return 0, {"message": f"Secure connection to the portal failed ({e.reason or e})."}
    except urllib.error.URLError as e:
        return 0, {"message": f"Can't reach the portal ({getattr(e, 'reason', e)})."}
    except (OSError, ValueError) as e:
        return 0, {"message": f"Can't reach the portal ({e})."}


def register(portal, username, password):
    status, body = _post(portal.rstrip("/") + "/api/register", {"username": username, "password": password})
    ok = bool(body.get("success")) and status == 200
    return ok, body.get("message") or ("Account created." if ok else "Sign-up failed.")


def change_password(portal, username, old, new):
    status, body = _post(portal.rstrip("/") + "/api/change-password",
                         {"username": username, "old_password": old, "new_password": new})
    if status == 404:
        return False, "This realm's portal doesn't support password changes yet."
    ok = bool(body.get("success")) and status == 200
    return ok, body.get("message") or ("Password changed." if ok else "Password change failed.")


# ---------------------------------------------------------------- remembered password

def protect(text):
    """Encrypt for this Windows user (DPAPI). Returns base64, or None where DPAPI is unavailable."""
    if sys.platform != "win32" or not text:
        return None
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    raw = text.encode("utf-8")
    src = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "OpenVanilla", None, None, None, 0x1, ctypes.byref(out)):
        return None
    try:
        return base64.b64encode(ctypes.string_at(out.pbData, out.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(blob):
    if sys.platform != "win32" or not blob:
        return None
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    try:
        raw = base64.b64decode(blob)
    except ValueError:
        return None
    src = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):
        return None
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ---------------------------------------------------------------- Discord sign-in (via the realm)
#
# The loopback flow desktop apps use: the launcher listens on 127.0.0.1, opens the player's browser
# at {portal}/auth/launcher, the realm signs them in (Discord, instantly when they already are) and
# redirects the browser back to the launcher with a one-time code, which the launcher trades for
# the game account and a launcher token. The launcher never sees a Discord password or token.

import secrets as _secrets
import threading as _threading
from http.server import BaseHTTPRequestHandler as _Handler, ThreadingHTTPServer as _Server
from urllib.parse import parse_qs as _parse_qs, urlencode as _urlencode, urlsplit as _urlsplit

_DONE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Open Vanilla</title>
<style>body{{margin:0;height:100vh;display:grid;place-items:center;background:#0c0a14;color:#e8e0d0;
font:16px system-ui,Segoe UI,sans-serif}}.c{{text-align:center;max-width:420px;padding:32px;border:1px solid #6b5426;
border-radius:14px;background:#17121c}}h1{{color:{color};font-size:22px;margin:0 0 10px}}p{{color:#a89f90;margin:0}}</style>
</head><body><div class="c"><h1>{title}</h1><p>{body}</p></div>
<script>setTimeout(function(){{window.close()}},1500)</script></body></html>"""


class LoopbackSignIn:
    """One sign-in attempt: `url` opens in the browser, `wait()` returns the one-time code."""

    def __init__(self, portal, switch=False, via=None):
        self.state = _secrets.token_urlsafe(24).replace("-", "a").replace("_", "b")[:32]
        self.code = None
        self.error = None
        self._done = _threading.Event()
        outer = self

        class H(_Handler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                parts = _urlsplit(self.path)
                if parts.path not in ("/openvanilla-signin", "/openwow-signin"):   # the second: realms before the rename
                    self.send_response(404)
                    self.end_headers()
                    return
                q = _parse_qs(parts.query)
                ok = q.get("state", [""])[0] == outer.state and q.get("code", [""])[0]
                if ok:
                    outer.code = q["code"][0]
                    page = _DONE_PAGE.format(color="#e9c46a", title="You're signed in",
                                             body="Head back to the Open Vanilla launcher. You can close this tab.")
                else:
                    outer.error = "The sign-in reply didn't match this launcher. Try again."
                    page = _DONE_PAGE.format(color="#e06c5a", title="Sign-in didn't match",
                                             body="Press Sign in in the launcher again.")
                data = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                outer._done.set()

        self._server = _Server(("127.0.0.1", 0), H)
        self.port = self._server.server_address[1]
        q = {"port": self.port, "state": self.state}
        if switch:
            q["switch"] = "1"
        if via in ("google", "key"):
            q["via"] = via      # realm patch 0042: straight to Google, or to the Hero Key page
        self.url = portal.rstrip("/") + "/auth/launcher?" + _urlencode(q)
        _threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def wait(self, timeout=300):
        """The code, or None (timed out / cancelled / mismatch: see `error`)."""
        self._done.wait(timeout)
        self.close()
        if self.code is None and self.error is None:
            self.error = "Sign-in timed out. Press Sign in to try again."
        return self.code

    def cancel(self):
        self.error = "Sign-in cancelled."
        self._done.set()

    def close(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        except OSError:
            pass


def _request(url, method="GET", payload=None, token=None, timeout=15):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": "OpenVanilla-Launcher", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {"message": f"The realm answered HTTP {e.code}."}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, {"message": f"Can't reach the realm ({getattr(e, 'reason', e)})."}


def exchange_code(portal, code):
    """(ok, info): info has user, pass, display_name, token … or message."""
    status, body = _request(portal.rstrip("/") + "/api/launcher/token", "POST", {"code": code})
    return status == 200 and bool(body.get("token")), body


def launcher_me(portal, token):
    """(status, info): 200 = still signed in (fresh credentials), 401 = signed out, 0 = offline."""
    return _request(portal.rstrip("/") + "/api/launcher/me", token=token, timeout=8)


def launcher_signout(portal, token):
    _request(portal.rstrip("/") + "/api/launcher/signout", "POST", {}, token=token, timeout=6)


# -- Hero Keys in the launcher (realm patch 0042) ---------------------------------------------------
# The launcher keeps the account's Hero Key (ovk1.<id>.<secret>, encrypted with protect()) and signs in
# with it on its own: it signs the realm's challenge with the key's Hero ID (Ed25519, the same
# derivation as the realm's key page), so the key's secret never leaves this PC.

HERO_CHALLENGE = "openvanilla-hero-v1\nchallenge:"
HERO_ARMOR = ("-----BEGIN OPEN VANILLA HERO KEY-----", "-----END OPEN VANILLA HERO KEY-----")


def parse_hero_key(text):
    """The key line in pasted text or a key file (`ovk1.<10>.<43>`), else None."""
    import re as _re
    m = _re.search(r"ovk1\.[A-Za-z0-9]{10}\.[A-Za-z0-9_-]{43}", text or "")
    return m.group(0) if m else None


def hero_key_file(key):
    """The text of a key file, the realm's own format."""
    return ("Open Vanilla Hero Key\n\nYour account's own sign-in. Keep it private: anyone with it can play as you.\n"
            f"{HERO_ARMOR[0]}\n{key}\n{HERO_ARMOR[1]}\n")


def hero_sign_in(portal, key):
    """(ok, info): info is /api/launcher/token's (user, pass, display_name, token) or has `message`."""
    key = parse_hero_key(key)
    if not key:
        return False, {"message": "That doesn't look like a Hero Key. It starts with ovk1. Paste the whole line, or load the key file."}
    try:
        from herokey_v2 import HeroKeyV2
    except ImportError:
        from .herokey_v2 import HeroKeyV2
    hk = HeroKeyV2.from_string(key)
    status, ch = _request(portal.rstrip("/") + "/api/hero/challenge", timeout=10)
    if status != 200 or not ch.get("challenge"):
        return False, {"message": ch.get("message") or "The realm didn't answer. Try again in a moment."}
    sig = hk.sign_message((HERO_CHALLENGE + ch["challenge"]).encode("utf-8"))
    status, body = _request(portal.rstrip("/") + "/api/launcher/hero", "POST",
                            {"key_id": hk.key_id, "hero": hk.hero_id, "challenge": ch["challenge"], "sig": sig})
    if status == 404:
        return False, {"message": "This realm can't take a Hero Key in the launcher yet. Use Continue with Google."}
    return status == 200 and bool(body.get("token")), body


def launcher_herokey(portal, token, replace=False):
    """(status, body): {"key": ...} a key made for this launcher, {"has_key": true} the account has one."""
    return _request(portal.rstrip("/") + "/api/launcher/herokey", "POST", {"replace": bool(replace)}, token=token, timeout=10)

