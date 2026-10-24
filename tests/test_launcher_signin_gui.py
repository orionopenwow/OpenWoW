"""The launcher's sign-in (realm patch 0042): Continue with Google and the Hero Key the launcher keeps, driven
headless against a stand-in realm that checks the Hero ID signature for real. No Discord sign-in anywhere.
Skips without Tk or a display (run it under xvfb-run).

    xvfb-run -a python3.12 -m unittest tests.test_launcher_signin_gui -v
"""
import base64
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "launcher"))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    import PIL.ImageTk  # noqa: F401
    HAVE_TK = True
except Exception:
    HAVE_TK = False

import herokey_v2  # noqa: E402


def new_key():
    return "ovk1.KEYID12345." + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


class FakeRealm:
    """/api/hero/challenge, /api/launcher/hero (verifies the signature), /api/launcher/herokey, /me, /signout."""

    def __init__(self):
        self.key = new_key()
        self.hero = herokey_v2.HeroKeyV2.from_string(self.key).hero_id
        self.challenges = set()
        self.tokens = {}
        self.calls = []
        self.has_key = False
        realm = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def _creds(self):
                tok = secrets.token_hex(16)
                realm.tokens[tok] = True
                return {"user": "HERO1", "pass": "gamepass", "display_name": "Kaelix", "token": tok}

            def do_GET(self):
                realm.calls.append(("GET", self.path))
                if self.path == "/api/hero/challenge":
                    c = secrets.token_urlsafe(16)
                    realm.challenges.add(c)
                    return self._send(200, {"challenge": c, "expires": int(time.time()) + 300})
                if self.path == "/api/launcher/me":
                    tok = (self.headers.get("Authorization") or "")[7:]
                    if realm.tokens.get(tok):
                        return self._send(200, {"user": "HERO1", "pass": "gamepass", "display_name": "Kaelix"})
                    return self._send(401, {"message": "Signed out"})
                self._send(404, {})

            def do_POST(self):
                realm.calls.append(("POST", self.path))
                b = self._body()
                if self.path == "/api/launcher/hero":
                    c = b.get("challenge", "")
                    ok = c in realm.challenges and b.get("hero") == realm.hero and herokey_v2.verify_challenge(
                        realm.hero, "openvanilla-hero-v1\nchallenge:" + c, b.get("sig", ""))
                    realm.challenges.discard(c)
                    if not ok or b.get("key_id") != realm.key[5:15]:
                        return self._send(401, {"message": "That Hero Key didn't work."})
                    return self._send(200, self._creds())
                if self.path == "/api/launcher/token":
                    return self._send(200, self._creds())
                if self.path == "/api/launcher/herokey":
                    tok = (self.headers.get("Authorization") or "")[7:]
                    if not realm.tokens.get(tok):
                        return self._send(401, {"message": "Signed out"})
                    if realm.has_key and not b.get("replace"):
                        return self._send(200, {"has_key": True, "key_id": realm.key[5:15]})
                    realm.has_key = True
                    return self._send(200, {"key": realm.key})
                if self.path == "/api/launcher/signout":
                    return self._send(204, {})
                self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@unittest.skipUnless(HAVE_TK, "needs tkinter, Pillow and a display (xvfb-run)")
class SignInGuiTests(unittest.TestCase):
    def setUp(self):
        import openvanilla_launcher as L
        import layout
        import account
        self.L, self.account = L, account
        self.tmp = tempfile.mkdtemp(prefix="owsignin-")
        self.realm = FakeRealm()
        saved = dict(LAYOUT=L.LAYOUT, SETTINGS_PATH=L.SETTINGS_PATH, LIVE_CACHE=L.LIVE_CACHE, ADDONS_DIR=L.ADDONS_DIR)
        saved_cls = {k: getattr(L.Launcher, k) for k in ("refresh_realms", "check_for_update", "load_directory")}
        saved_acct = {k: getattr(account, k) for k in ("protect", "unprotect", "LoopbackSignIn")}
        saved_open = L.safe_open
        self.opened = []

        def restore():
            for k, v in saved.items():
                setattr(L, k, v)
            for k, v in saved_cls.items():
                setattr(L.Launcher, k, v)
            for k, v in saved_acct.items():
                setattr(account, k, v)
            L.safe_open = saved_open
            if self.app is not None:
                try:
                    self.app.destroy()
                except Exception:
                    pass
            self.realm.close()
            __import__("shutil").rmtree(self.tmp, ignore_errors=True)

        self.addCleanup(restore)
        L.LAYOUT = layout.Layout(self.tmp, self.tmp, "portable").ensure()
        L.SETTINGS_PATH = L.LAYOUT.settings_file
        L.LIVE_CACHE = L.LAYOUT.live_cache
        L.ADDONS_DIR = L.LAYOUT.addons_enabled
        for k in saved_cls:
            setattr(L.Launcher, k, lambda s: None)
        # DPAPI stands in for Windows: reversible, so what's kept on disk can be read back
        account.protect = lambda t: ("P:" + base64.b64encode(t.encode()).decode()) if t else None
        account.unprotect = lambda b: base64.b64decode(b[2:]).decode() if b and b.startswith("P:") else None
        L.safe_open = lambda url: self.opened.append(url)
        self.app = None

    def start(self):
        self.app = self.L.Launcher()
        self.app.realms[self.app.realm_index]["portal"] = self.realm.url
        self.app.show_page("play", animate=False)
        return self.app

    def pump(self, seconds=3.0, until=None):
        end = time.monotonic() + seconds
        app = self.app

        def tick():
            if (until and until()) or time.monotonic() >= end:
                app.quit()
            else:
                app.after(20, tick)

        app.after(20, tick)
        app.mainloop()
        return until() if until else True

    def texts(self):
        app = self.app
        out = [app.cv.itemcget(i, "text") for i in app.cv.find_all() if app.cv.type(i) == "text"]

        def walk(w):
            try:
                if "text" in w.keys():
                    out.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)

        walk(app)
        return " | ".join(out)

    def test_no_discord_sign_in_anywhere(self):
        app = self.start()
        home = self.texts()
        self.assertNotIn("CONTINUE WITH DISCORD", home.upper())
        app.show_page("account", animate=False)
        page = self.texts()
        self.assertIn("SIGN IN TO OPEN VANILLA", page)
        self.assertIn("HAVE A HERO KEY?", page)
        self.assertNotIn("Discord", page)
        # the buttons are images; their labels live in the button cache keys
        labels = " ".join(str(k) for k in getattr(app, "_btn_cache", {}).keys()) if hasattr(app, "_btn_cache") else ""
        self.assertNotIn("DISCORD", labels.replace("JOIN THE DISCORD", ""))

    def test_continue_with_google_goes_straight_to_google(self):
        app = self.start()
        app.sign_in_google()
        flow = app._discord_flow
        self.assertTrue(flow and "via=google" in flow.url and flow.url.startswith(self.realm.url + "/auth/launcher?"), flow and flow.url)
        self.assertEqual(self.opened[-1], flow.url)
        app.cancel_discord()
        self.assertTrue(self.pump(3, until=lambda: app._discord_flow is None))

    def test_google_sign_in_keeps_the_accounts_first_hero_key(self):
        app = self.start()
        realm_i = app.realm_index
        self.realm.tokens["T0"] = True
        app._discord_flow = flow = object()
        app._discord_done(flow, True, {"user": "hero1", "pass": "gamepass", "display_name": "Kaelix", "token": "T0"}, realm_i)
        self.assertTrue(self.pump(4, until=lambda: app._saved_hero_key() == self.realm.key))
        self.assertTrue(app.settings["hero_key"].startswith("P:"), "kept on this PC, encrypted")
        self.assertNotIn(self.realm.key, json.dumps({k: v for k, v in app.settings.items() if k != "hero_key"}))
        app.show_page("account", animate=False)
        self.assertIn("YOUR HERO KEY", self.texts())
        self.assertIn("Saved in this launcher", self.texts())

    def test_an_account_with_a_key_elsewhere_asks_for_it(self):
        app = self.start()
        self.realm.has_key = True
        self.realm.tokens["T1"] = True
        app._discord_flow = flow = object()
        app._discord_done(flow, True, {"user": "hero1", "pass": "gamepass", "display_name": "Kaelix", "token": "T1"}, app.realm_index)
        self.assertTrue(self.pump(4, until=lambda: app.session.get("hero_elsewhere")))
        app.show_page("account", animate=False)
        self.assertIn("Your account has a Hero Key already", self.texts())
        self.assertFalse(app._keep_hero_key("not a key"))
        self.assertTrue(app._keep_hero_key("my key: " + self.realm.key))
        self.assertEqual(app._saved_hero_key(), self.realm.key)

    def test_hero_key_signs_in_with_no_browser_and_is_remembered(self):
        app = self.start()
        app.show_page("account", animate=False)
        app.sign_in_hero("pasted text\n" + self.realm.key + "\n")
        self.assertTrue(self.pump(5, until=lambda: app.session.get("via") == "hero"))
        self.assertEqual(app.session["user"], "HERO1")
        self.assertEqual(app.session["password"], "gamepass")
        self.assertEqual(self.opened, [], "no browser")
        self.assertIn(("POST", "/api/launcher/hero"), self.realm.calls)
        self.assertEqual(app._saved_hero_key(), self.realm.key)
        self.assertIn("Signed in with your Hero Key", self.texts())
        # signed out: the key stays, PLAY's sign-in uses it again with no browser
        app.sign_out()
        self.assertFalse(app.session.get("user"))
        app.sign_in_auto()
        self.assertTrue(self.pump(5, until=lambda: app.session.get("via") == "hero"))
        self.assertEqual(self.opened, [])
        # and the next launch: the saved token, checked in the background
        self.app.save_settings()

    def test_a_wrong_key_says_so(self):
        app = self.start()
        app.show_page("account", animate=False)
        app.sign_in_hero("hello")
        self.assertIn("doesn't look like a Hero Key", app._acct_msg[0])
        app.sign_in_hero(new_key())
        self.assertTrue(self.pump(5, until=lambda: not getattr(app, "_hero_busy", False) and app._acct_msg[1] == self.L.RED))
        self.assertIn("didn't work", app._acct_msg[0])
        self.assertFalse(app.session.get("user"))

    def test_a_signed_out_token_falls_back_to_the_kept_key(self):
        app = self.start()
        app._keep_hero_key(self.realm.key)
        app.session.update(user="HERO1", password="old", token="gone", via="web", realm=app.realm_index)
        app._launcher_me_done(401, {"message": "Signed out"})
        self.assertTrue(self.pump(5, until=lambda: app.session.get("via") == "hero"))
        self.assertEqual(app.session["password"], "gamepass")


if __name__ == "__main__":
    unittest.main()
