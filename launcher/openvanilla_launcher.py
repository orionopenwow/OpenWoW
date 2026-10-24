"""Open Vanilla Launcher — the player-facing launcher that ships in the client repack.

Layout (matches the Open Vanilla UI kit mockup):
    left rail     the realms, as medallions (+ to add one), Settings and Help at the bottom
    top bar       OPENVANILLA wordmark, tabs (Game Client, Web Play, Patch Notes, Community, Addons),
                  realm status, account chip, window buttons
    centre        the animated vortex; on Game Client, news / status / community / account cards
    bottom bar    realm picker, the energy bar between two dragon heads, PLAY

Everything shown is live: realm status comes from the realm's portal (/api/status) or a TCP
probe, mods are the folders in benilla-config/AddOns, patch notes come from the portal with the
bundled file as fallback, the energy bar only fills for a real update download, and sign-in is a
real SRP6 login against the realm's login server (see account.py).

Layout of a repack folder (see packaging/build_repack.py):
    Game/Open Vanilla Game.exe  the engine (a benilla player build)
    OpenVanilla.exe             this program, frozen
    benilla-config/AddOns/      addons the engine loads
    launcher/defaults.json      realms, community links, update manifest URL
    launcher/patch_notes.json   bundled patch notes
    launcher/version.json       this build's version
"""
import hashlib
import json
import math
import os
import queue
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

import account
import launcher_art as art
import wow_import  # finds and checks the player's own 1.12.1 install (archives, WoW.exe build)
import ed25519     # checks that an update manifest was signed by Open Vanilla's release key
import layout      # the install/user-data folders and moving old installs over (launcher/layout.py)
import updater     # background update staging and the restart-to-update hand-off
import live_content  # the signed downloads/live.json: news, banner, feature flags, links
import fetch as fetch_mod  # resumable downloads (updates, SPP Classics)
import home_logic  # HOME's decisions without Tk: play modes, Solo's next step, the update pill, the client button
import game_clients  # the client catalog (defaults, live content, clients.txt) behind Workshop > CLIENTS and HOME's dropdown
try:  # Play Solo with SPP Classics (launcher/spp.py)
    import spp
except ImportError:
    spp = None
try:  # HOST > Dedicated server (launcher/server_host.py)
    import server_host
except ImportError:
    server_host = None
try:  # "Share what I'm listening to" (Settings > Privacy, off by default)
    import nowplaying
except ImportError:
    nowplaying = None
try:  # Workshop > ADDONS and openvanilla://workshop/install/<id> links (launcher/workshop.py)
    import workshop
except ImportError:
    workshop = None
try:  # Settings > AI: "Activate your AI (optional)" (launcher/ai_setup.py)
    import ai_setup
except ImportError:
    ai_setup = None
try:  # PLAY SOLO: play_local.py sits in the Open Vanilla folder (a dev checkout) or is frozen in with the launcher
    sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import play_local as solo
except ImportError:
    solo = None
from pathlib import Path

# ---------------------------------------------------------------- paths

FROZEN = getattr(sys, "frozen", False)
# Play Solo runs SPP Classics or the Solo pack: Windows programs. Tests that drive Solo with fakes set this.
SOLO_ON_THIS_OS = sys.platform == "win32"
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
ASSETS = os.path.join(RES_DIR, "assets", "launcher")
# Folder layout 2 (launcher/layout.py, docs/LAUNCHER.md): OpenVanilla.exe + app\ + Game\ + Server\ in the
# install folder; AddOns, Realms, Screenshots, Logs, Backups, Settings and Cache in the user-data folder
# (the install folder for the zip, %LOCALAPPDATA%\OpenVanilla for the installer, _local\launcher-data from source).
SOURCE_ROOT = None if FROZEN else os.path.dirname(APP_DIR)
LAYOUT = layout.detect(APP_DIR if FROZEN else SOURCE_ROOT, source=not FROZEN)
INSTALL_DIR = LAYOUT.install
# shipped launcher data (defaults.json, version.json, patch_notes.json, links.txt): app\data in layout 2,
# <game>\launcher in older repacks, the source folder itself when run from source
DATA_DIR = next((d for d in (os.path.join(RES_DIR, "data"), os.path.join(APP_DIR, "launcher")) if os.path.isdir(d)), APP_DIR)
SHIPPED_ADDONS = os.path.join(RES_DIR, "addons")   # the Classic+ addons frozen in (seeded into AddOns\Enabled)
ENGINE_NAMES = (layout.ENGINE_EXE,) + layout.NEXT_ENGINE_NAMES + layout.LEGACY_ENGINE_NAMES + ("OpenWoW", "benilla")
CONFIG_DIR = LAYOUT.engine_config        # the engine's state folder, beside its binary (Game\benilla-config)
ADDONS_DIR = LAYOUT.addons_enabled       # shared by every client; PLAY copies them into the client's own folder
ADDONS_OFF_DIR = LAYOUT.addons_disabled
SETTINGS_PATH = LAYOUT.settings_file
STATE_DIR = LAYOUT.settings_dir          # small launcher state files (nowplaying.json, …)
LIVE_CACHE = LAYOUT.live_cache

art.FONT_DIRS.insert(0, os.path.join(ASSETS, "fonts"))
art.KIT_DIRS.insert(0, os.path.join(ASSETS, "kit"))


def read_version():
    """This build's version: app\\data\\version.json (written from VERSION by build_repack), or the
    checkout's VERSION file when run from source."""
    if SOURCE_ROOT:
        try:
            with open(os.path.join(SOURCE_ROOT, "VERSION"), encoding="utf-8") as f:
                v = f.read().strip()
            if v:
                return v
        except OSError:
            pass
    return read_json(os.path.join(DATA_DIR, "version.json"), {}).get("version", "0.0.0")


def startup(argv=None):
    """Once per launch, before the window: move an older install into layout 2, seed the bundled addons,
    tell the Solo/Host modules where Realms\\ is, and drop staged updates that are already applied."""
    lay = LAYOUT
    log_lines = []
    try:
        legacy = [lay.install] + ([APP_DIR] if SOURCE_ROOT else [])
        log_lines += layout.migrate(lay, legacy, frozen=FROZEN)
        layout.ensure_launcher_name(lay, FROZEN, log=log_lines.append)
        layout.seed_shipped_addons(SHIPPED_ADDONS, lay, read_version())
    except OSError as e:
        log_lines.append(f"layout: {e}")
    lay.export_env()
    try:
        updater.cleanup(lay, read_version())
    except OSError:
        pass
    if log_lines:
        try:
            with open(os.path.join(lay.logs, "launcher.log"), "a", encoding="utf-8") as f:
                for line in log_lines:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
        except OSError:
            pass
    return log_lines

# ---------------------------------------------------------------- palette & geometry

BG = "#08060c"
RAIL_BG = "#0b0910"
PANEL = "#0f0c14"        # the opaque content panel; widgets placed on it use the same colour
PANEL_RGBA = (15, 12, 20, 255)
FIELD = "#1a1520"
LINE = "#3a2f22"
GOLD = "#f3d179"
GOLD_DIM = "#c99a3f"
TAN = "#cdb98f"
TEXT = "#ece6da"
MUTED = "#b8ae9c"
GREEN = "#5ee08a"
RED = "#f07a6e"
AMBER = "#f6c453"
CYAN = "#5fd0ff"

WIN_W, WIN_H = 1240, 700
RAIL = 74
TOP = 66
BOT = 92
LEFT_W = 304   # the home page's card column
ART_X, ART_Y = RAIL, TOP
ART_W, ART_H = WIN_W - RAIL, WIN_H - TOP - BOT
FPS_MS = 33

DISPLAY_FAMILY = "Georgia"  # replaced by Cinzel once the bundled font is registered


def font(size, weight="normal", display=False):
    if display:
        return (DISPLAY_FAMILY, size, weight)
    return ("Segoe UI", size + 1 if size < 11 else size, weight)  # +1pt on small body text for legibility


def fit_text(text, fnt, width):
    """text cut with … to fit `width` pixels in font tuple `fnt` (measured, so it follows the font bump)."""
    f = tkfont.Font(font=fnt)
    while f.measure(text) > width and len(text) > 4:
        text = text.rstrip("…")[:-1].rstrip() + "…"
    return text


def register_fonts():
    """Make the bundled Cinzel usable by Tk (Windows: private AddFontResourceEx)."""
    global DISPLAY_FAMILY
    fdir = os.path.join(ASSETS, "fonts")
    if sys.platform == "win32" and os.path.isdir(fdir):
        try:
            import ctypes
            for f in os.listdir(fdir):
                if f.lower().endswith(".ttf"):
                    ctypes.windll.gdi32.AddFontResourceExW(os.path.join(fdir, f), 0x10, 0)
        except Exception:
            pass


# ---------------------------------------------------------------- data helpers

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_links_txt(search_dirs):
    """Find and parse links.txt (Notepad-friendly KEY = VALUE config)."""
    for d in search_dirs:
        cand = os.path.join(d, "links.txt")
        if os.path.isfile(cand):
            out = {}
            try:
                with open(cand, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(("#", ";")):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            out[k.strip().upper()] = v.strip()
                return out
            except OSError:
                pass
    return {}


FILE_LINK_EXTS = (".zip", ".7z", ".rar", ".exe", ".msi", ".tar.gz")


# Community directory entry "kind" -> its row icon.
KIND_ICONS = {"server": "server", "game": "play", "client": "play", "repack": "download",
              "addon": "mods", "mod": "mods", "tool": "code", "web": "web", "source": "github"}


def is_file_link(url):
    """A direct file download (the launcher fetches it) rather than a page (opened in the browser)."""
    return urllib.parse.urlsplit(url or "").path.lower().endswith(FILE_LINK_EXTS)


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 OpenVanilla-Launcher")


def download_mirrors(url):
    """The URL plus, for Internet Archive links, the item's direct storage servers (archive.org's
    /download/ redirector sometimes answers 5xx for big files while the servers themselves are fine)."""
    out = [url]
    m = re.match(r"https?://(?:www\.)?archive\.org/download/([^/]+)/(.+)$", url or "")
    if not m:
        return out, None
    item, path = m.groups()
    try:
        meta = http_json(f"https://archive.org/metadata/{item}", timeout=15)
    except Exception:
        return out, None
    seen = set()
    hosts = [(meta.get(k), meta.get("dir")) for k in ("d1", "d2", "server")]
    for alt in meta.get("alternate_locations", {}).get("workable", []) or []:
        hosts.append((alt.get("server"), alt.get("dir")))
    for host, d in hosts:
        if host and d and host not in seen:
            seen.add(host)
            out.insert(len(out) - 1, f"https://{host}{d}/{path}")
    md5 = next((f.get("md5") for f in meta.get("files", []) if f.get("name") == urllib.parse.unquote(path)), None)
    return out, md5


LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
HOST_RE = re.compile(r"(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?|\[?[0-9A-Fa-f:.]+\]?")


def valid_host(h):
    """A DNS name or an IP address, nothing else (it ends up in realmlist.wtf and in TCP connects)."""
    return isinstance(h, str) and bool(HOST_RE.fullmatch(h))


def safe_url(url):
    """url if it's https (or http to this PC), else None. Blocks file://, UNC paths and other schemes,
    which Windows would hand to a program."""
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return None
    if p.scheme == "https" and p.hostname and valid_host(p.hostname):
        return p.geturl()
    if p.scheme == "http" and (p.hostname or "") in LOCAL_HOSTS:
        return p.geturl()
    return None


def safe_open(url):
    u = safe_url(url)
    if u:
        webbrowser.open(u)
    return bool(u)


URL_KEYS = ("url", "homepage", "portal", "zip_url", "html_url")


def clean_directory(data):
    """Keep only well-formed entries from the community directory (it comes from the network)."""
    out = {}
    for kind in ("servers", "mods", "repacks"):
        items = []
        for it in (data.get(kind) or [])[:200] if isinstance(data.get(kind), list) else []:
            if not isinstance(it, dict):
                continue
            it = {k: v for k, v in it.items() if isinstance(k, str) and (not isinstance(v, str) or len(v) <= 4000)}
            for k in URL_KEYS:
                if k in it and not safe_url(it[k]):
                    it.pop(k)
            if isinstance(it.get("images"), list):
                it["images"] = [u for u in it["images"] if safe_url(u)][:12]
            if kind == "servers":
                try:
                    port = int(it.get("port", 3724))
                except (TypeError, ValueError):
                    continue
                if not valid_host(it.get("host")) or not 1 <= port <= 65535:
                    continue
                it["port"] = port
            if isinstance(it.get("name"), str) and it["name"].strip():
                items.append(it)
        out[kind] = items
    return out


class Cancelled(Exception):
    """The player pressed cancel; the partial file is kept so the next start resumes."""


def check_cancel(job):
    if job.get("cancel"):
        raise Cancelled()


CLIENT_LINK_MODES = ("TEMP", "PACKED")


def resolve_client_links(links):
    """CLIENT_DOWNLOADS = TEMP | PACKED picks CLIENT_112_URL / CLIENT_335_URL from the
    matching *_TEMP or *_PACKED line, so the stock-client downloads can be parked and packed
    back in by changing one word in links.txt. A plain CLIENT_112_URL line still wins when no
    switch is set (older links.txt files keep working)."""
    mode = (links.get("CLIENT_DOWNLOADS") or "").strip().upper()
    if mode not in CLIENT_LINK_MODES:
        return links
    for ver in ("112", "335"):
        url = links.get(f"CLIENT_{ver}_URL_{mode}")
        if url:
            links[f"CLIENT_{ver}_URL"] = url
    return links


def apply_links_overrides(defaults, overrides):
    """Apply overrides from links.txt to the defaults dict."""
    if not overrides:
        return defaults
    overrides = resolve_client_links(dict(overrides))
    # Client download links
    clients = defaults.setdefault("clients", [])
    for c in clients:
        cid = c.get("id")
        if cid in ("openvanilla", "engine") and "OPENVANILLA_CLIENT_URL" in overrides:
            c["download_url"] = overrides["OPENVANILLA_CLIENT_URL"]
        elif cid == "vanilla" and "CLIENT_112_URL" in overrides:
            c["download_url"] = overrides["CLIENT_112_URL"]
        elif cid == "wotlk" and "CLIENT_335_URL" in overrides:
            c["download_url"] = overrides["CLIENT_335_URL"]

    if overrides.get("DISCORD_LOGIN_URL"):
        defaults["discord_login_url"] = overrides["DISCORD_LOGIN_URL"]

    # Manifest update
    if "UPDATE_MANIFEST_URL" in overrides:
        defaults["update_manifest"] = overrides["UPDATE_MANIFEST_URL"]

    # Community
    comm = defaults.setdefault("community", {})
    if "PORTAL_URL" in overrides:
        comm["portal"] = overrides["PORTAL_URL"]
    if "DISCORD_INVITE" in overrides:
        comm["discord"] = overrides["DISCORD_INVITE"]
    if "DONATE_CARD_URL" in overrides:
        comm["donate_card"] = overrides["DONATE_CARD_URL"]
    if "GITHUB_REPO" in overrides:
        comm["github"] = overrides["GITHUB_REPO"]
    if "BUG_REPORTS" in overrides:
        comm["bug_reports"] = overrides["BUG_REPORTS"]

    # Realms
    if "REALM_HOST" in overrides or "REALM_NAME" in overrides:
        realms = defaults.setdefault("realms", [])
        if realms:
            r0 = realms[0]
            if "REALM_NAME" in overrides:
                r0["name"] = overrides["REALM_NAME"]
            if "REALM_HOST" in overrides:
                r0["host"] = overrides["REALM_HOST"]
            if "REALM_PORT" in overrides:
                try:
                    r0["port"] = int(overrides["REALM_PORT"])
                except ValueError:
                    pass
            # The realm's portal is where /api/register and the browser game live: the game
            # backend, which differs from PORTAL_URL when the website is on static hosting.
            if overrides.get("BACKEND_URL") or overrides.get("PORTAL_URL"):
                r0["portal"] = overrides.get("BACKEND_URL") or overrides["PORTAL_URL"]
    return defaults


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def version_tuple(v):
    out = []
    for part in str(v).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def http_json(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "OpenVanilla-Launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def realm_health(portal, timeout=5):
    """(status, detail) from a browser realm's public /healthz (wenilla-realm: soap = the world server,
    mariadb = its database), or None when the site has no such page. The official realm publishes no
    game ports and has no /api/status, so without this the launcher called it offline while it was up."""
    try:
        d = http_json(portal.rstrip("/") + "/healthz", timeout=timeout)
    except urllib.error.HTTPError as e:
        return ("offline", f"The realm's website answered {e.code}") if e.code >= 500 else None
    except Exception:
        return None
    if not isinstance(d, dict) or not any(k in d for k in ("soap", "mariadb")):
        return None
    if d.get("soap") is False:
        return "partial", "Website up · world server down"
    if d.get("mariadb") is False:
        return "partial", "Website up · database down"
    return "online", "Plays through the realm's website"


# The public half of the key CI signs downloads/version.json with (packaging/release_manifest.py).
# An update is only offered when version.json.sig verifies against it, so a tampered mirror or a
# hijacked page can't point launchers at another file. Rotating the key means shipping a launcher
# with the new one first.
MANIFEST_PUBKEY = "845b8fd97c36702fcac4e60ef279f0cfdf69628f54e2463d0efc2006e6c9f448"


def http_bytes(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "OpenVanilla-Launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def signed_manifest(url, timeout=6):
    """The update manifest at url, or None unless url + ".sig" is a valid signature of its bytes."""
    body = http_bytes(url, timeout)
    try:
        sig = bytes.fromhex(http_bytes(url + ".sig", timeout).decode("ascii").strip())
    except (ValueError, OSError):
        return None
    if not ed25519.verify(bytes.fromhex(MANIFEST_PUBKEY), body, sig):
        return None
    return json.loads(body.decode("utf-8"))


def tcp_ping(host, port, timeout=2.5):
    """Milliseconds to open a TCP connection, or None."""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return int((time.perf_counter() - t0) * 1000)
    except (OSError, ValueError):
        return None


def exe_command(exe):
    """How to start a client program: itself on Windows; a Windows .exe through Wine on macOS and Linux
    (WINE in the environment picks another runner, e.g. a Proton or CrossOver wine)."""
    if sys.platform != "win32" and str(exe).lower().endswith(".exe"):
        wine = os.environ.get("WINE") or shutil.which("wine") or shutil.which("wine64")
        if not wine:
            raise OSError("WoW.exe is a Windows program: install Wine (for example sudo apt install wine) "
                          "to run it here, or play in the browser.")
        return [wine, str(exe)]
    return [exe]


def find_engine():
    """Game\\Open Vanilla Game.exe, else an engine left by an older install or a dev build beside the launcher."""
    return layout.find_engine(LAYOUT, extra_dirs=(INSTALL_DIR, APP_DIR))


def wow_data_dir(folder):
    """Accept the WoW folder or its Data folder; return the Data folder (as a str) if it holds dbc.MPQ."""
    if not folder:
        return None
    try:
        p = wow_import.data_dir(folder)
    except OSError:
        return None
    return str(p) if p else None


def wow_problems(folder):
    """Why this WoW folder won't run Open Vanilla (missing or damaged archives, wrong build); [] when it's good."""
    data = wow_data_dir(folder)
    if not data:
        return ["No Data folder with game archives found there."]
    try:
        return wow_import.problems(Path(data))
    except OSError as e:
        return [f"Couldn't read the Data folder ({e})."]


def read_toc(folder):
    """Title/notes/version from an addon's .toc, with |c colour codes stripped."""
    name = os.path.basename(folder)
    info = {"name": name, "title": name, "notes": "", "version": "", "author": ""}
    toc = None
    try:
        for f in os.listdir(folder):
            if f.lower() == name.lower() + ".toc":
                toc = os.path.join(folder, f)
                break
        if not toc:
            tocs = [f for f in os.listdir(folder) if f.lower().endswith(".toc")]
            toc = os.path.join(folder, tocs[0]) if tocs else None
    except OSError:
        return None
    if not toc:
        return None
    try:
        with open(toc, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith("##"):
                    continue
                key, _, val = line[2:].partition(":")
                key, val = key.strip().lower(), val.strip()
                if key in ("title", "notes", "version", "author"):
                    info[key] = val
    except OSError:
        pass
    info["title"] = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", info["title"]).strip() or name
    info["notes"] = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", info["notes"]).strip()
    return info


def list_addons(addons_dir=None):
    addons_dir = addons_dir or ADDONS_DIR
    off = ADDONS_OFF_DIR if os.path.abspath(addons_dir) == os.path.abspath(ADDONS_DIR) else addons_dir + ".disabled"
    rows = []
    for root, enabled in ((addons_dir, True), (off, False)):
        try:
            entries = sorted(os.listdir(root), key=str.lower)
        except OSError:
            continue
        for e in entries:
            p = os.path.join(root, e)
            if os.path.isdir(p):
                info = read_toc(p)
                if info:
                    info.update(enabled=enabled, path=p)
                    rows.append(info)
    return rows


BUILD_NAMES = {5875: "1.12.1", 6005: "1.12.2", 8606: "2.4.3", 12340: "3.3.5a"}


# ---------------------------------------------------------------- web play

def find_browsers():
    """Chromium-family browsers that can open a chromeless --app window, best first."""
    found = []
    if sys.platform == "win32":
        pf = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        cands = [("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe"),
                 ("Google Chrome", r"Google\Chrome\Application\chrome.exe"),
                 ("Brave", r"BraveSoftware\Brave-Browser\Application\brave.exe")]
        for name, rel in cands:
            for base in pf:
                if base and os.path.isfile(os.path.join(base, rel)):
                    found.append((name, os.path.join(base, rel)))
                    break
    elif sys.platform == "darwin":
        # the app bundles, in /Applications or the user's own Applications folder
        for name, app in (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"),
                          ("Brave", "Brave Browser"), ("Chromium", "Chromium")):
            for base in ("/Applications", os.path.expanduser("~/Applications")):
                exe = os.path.join(base, app + ".app", "Contents", "MacOS", app)
                if os.path.isfile(exe):
                    found.append((name, exe))
                    break
    else:
        seen = set()
        for name, exe in (("Google Chrome", "google-chrome-stable"), ("Google Chrome", "google-chrome"),
                          ("Chromium", "chromium"), ("Chromium", "chromium-browser"),
                          ("Microsoft Edge", "microsoft-edge-stable"), ("Microsoft Edge", "microsoft-edge"),
                          ("Brave", "brave-browser"), ("Brave", "brave")):
            p = shutil.which(exe)
            if p and name not in seen:
                seen.add(name)
                found.append((name, p))
    return found


def linux_webgpu_flags(platform=None):
    """Chrome on Linux turns WebGPU on by default only for some GPUs (newer Intel; NVIDIA on Wayland). The
    launcher's own play window asks for it through Vulkan everywhere else; it uses its own profile, so the
    player's normal browser keeps its settings."""
    if (platform or sys.platform).startswith("linux"):
        return ["--enable-unsafe-webgpu", "--enable-features=Vulkan,VulkanFromANGLE", "--use-angle=vulkan"]
    return []


def launch_web(url, fullscreen=True):
    """Open the Open Vanilla site in its own chromeless window (fullscreen by default).

    A dedicated browser profile keeps the window separate from the player's normal browsing,
    so the flags apply even when the browser is already open. Returns (ok, message).
    """
    browsers = find_browsers()
    if browsers:
        name, exe = browsers[0]
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
        old = os.path.join(base, "OpenWoW", "WebPlay")   # the browser profile from before the rename keeps its sign-ins
        profile = old if os.path.isdir(old) else os.path.join(base, "OpenVanilla", "WebPlay")
        os.makedirs(profile, exist_ok=True)
        args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required", "--disable-features=Translate"]
        args += linux_webgpu_flags()
        args.append("--start-fullscreen" if fullscreen else "--window-size=1600,900")
        try:
            subprocess.Popen(args, close_fds=True)
            return True, f"Opening Open Vanilla in {name}" + (" (F11 leaves fullscreen)" if fullscreen else "")
        except OSError as e:
            return False, f"Could not start {name}: {e}"
    safe_open(url)
    return True, "Opened in your default browser (install Edge or Chrome for the fullscreen window)."


# ---------------------------------------------------------------- the window

# ---------------------------------------------------------------- P2P: community realms, hosting, torrents
# The package launcher/p2p/ is optional. Each of its modules is imported the first time a page needs it,
# so the launcher starts cleanly without it (or without libtorrent) and the page says what is missing.

P2P_DIRECTORY_URL = "https://play.openvanilla.app/api/directory"
P2P_PORTAL = "https://play.openvanilla.app"
REALM_TYPES = (("pve", "PvE"), ("pvp", "PvP"), ("rp", "RP"), ("rppvp", "RP-PvP"))
REALM_TYPE_ICONS = {"pve": "shield", "pvp": "swords", "rp": "scroll", "rppvp": "swords"}
REALM_TEMPLATES = (("classicplus", "Vanilla Remastered"), ("vanilla", "Vanilla"))
CONNECTIONS = (("relay", "Through Open Vanilla (recommended: your address stays hidden)"),
               ("direct", "Direct from my home connection"),
               ("lan", "My local network only"))
def legacy_link(a):
    """Links made before the rename use the old scheme; read them as openvanilla:// links."""
    return "openvanilla://" + a[10:] if a[:10].lower() == "openwow://" else a


def register_link_handler():
    """Point openvanilla:// links at this launcher (per user, no admin). The installer does the same; a
    launcher updated in place from an older install only had the old scheme registered."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        exe = sys.executable
        base = r"Software\Classes\openvanilla"
        for sub, name, val in ((base, "", "URL:Open Vanilla"), (base, "URL Protocol", ""),
                               (base + r"\DefaultIcon", "", f'"{exe}",0'),
                               (base + r"\shell\open\command", "", f'"{exe}" "%1"')):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
    except OSError:
        pass


INVITE_RE = re.compile(r"^(?:openvanilla://join/|https://play\.(?:openvanilla|openwow)\.app/join/)([a-z2-7]{16})/?(?:\?(.*))?$")  # old links still work
_P2P_MODS, _P2P_ERRS = {}, {}


def p2p_module(name):
    """launcher/p2p/<name>.py, imported on first use; None (and the reason in p2p_error) when it can't load."""
    if name not in _P2P_MODS:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(1, here)
        try:
            import importlib
            _P2P_MODS[name] = importlib.import_module("p2p." + name)
        except Exception as e:  # ImportError, or an optional dependency that is broken on this PC
            _P2P_MODS[name] = None
            _P2P_ERRS[name] = f"{type(e).__name__}: {e}"
    return _P2P_MODS[name]


def p2p_error(name):
    return _P2P_ERRS.get(name, "")


def parse_invite(text):
    """openvanilla://join/<host_id>?i=<code>&n=<name> or https://play.openvanilla.app/join/<host_id>?i=<code>
    -> dict(host_id, code, name, link), else None."""
    text = (text or "").strip()
    base, sep, query = text.partition("?")
    m = INVITE_RE.match(base.lower() + sep + query)
    if not m:
        return None
    q = urllib.parse.parse_qs(m.group(2) or "")
    code = (q.get("i") or [""])[0]
    if code and not re.fullmatch(r"[A-Za-z2-7]{10}", code):
        return None
    code = code.upper()
    name = "".join(ch for ch in (q.get("n") or [""])[0] if ch.isprintable())[:40]
    return dict(kind="relay", host_id=m.group(1), code=code, name=name, link=text.strip())


DIRECT_RE = re.compile(r"^openvanilla://join/(direct|lan)/([A-Za-z0-9.\-]{1,253}|\[[0-9a-fA-F:]+\]):(\d{1,5})/?(?:\?(.*))?$")
OFFLINE_TEXT = "Open Vanilla is offline: you can still host and join friends directly."


def parse_link(text):
    """Any invite link: the relay form (parse_invite), or openvanilla://join/direct|lan/<host>:<port>?g=…&n=…&k=…
    (no Open Vanilla services involved) -> dict(kind, host_id, host, port, code, guest, name, fp, link), else None."""
    inv = parse_invite(text)
    if inv:
        q = urllib.parse.parse_qs(text.partition("?")[2])
        inv.update(host=None, port=None, guest=((q.get("g") or [""])[0] or "").upper() or None,
                   fp=(q.get("k") or [None])[0])
        return inv
    m = DIRECT_RE.match((text or "").strip())
    if not m or not 0 < int(m.group(3)) < 65536:
        return None
    q = urllib.parse.parse_qs(m.group(4) or "")
    name = "".join(ch for ch in (q.get("n") or [""])[0] if ch.isprintable())[:40]
    return dict(kind=m.group(1), host_id=None, host=m.group(2), port=int(m.group(3)), code="",
                guest=((q.get("g") or [""])[0] or "").upper() or None, fp=(q.get("k") or [None])[0], name=name,
                link=text.strip())


def is_offline_error(text):
    """Errors that only mean Open Vanilla's central services (directory, sign-in, relay) can't be reached."""
    t = (text or "").lower()
    return any(k in t for k in ("can't be reached", "cannot be reached", "unreachable", "urlopen error",
                                "timed out", "name or service not known", "getaddrinfo", "connection refused",
                                "network is unreachable", "needs the openvanilla directory"))


def is_host_key_error(text):
    t = (text or "").lower()
    return "host key" in t or "pretending to be" in t or "didn't prove it is the host" in t or "host signature" in t


def rf(r, key, default=None):
    """A field of a directory Realm (the p2p dataclass) or a plain dict."""
    v = r.get(key, default) if isinstance(r, dict) else getattr(r, key, default)
    return default if v is None else v


def realm_key(r):
    return rf(r, "host_id") or f"{rf(r, 'host', '')}:{rf(r, 'port', 3724)}"


def realm_group(r):
    """0 official, 1 verified community, 2 unverified (listed below, greyed)."""
    return 0 if rf(r, "official", False) else (1 if rf(r, "verified", False) else 2)


def realm_has_room(r):
    cap = rf(r, "max_players")
    return not cap or int(rf(r, "population", 0) or 0) < int(cap)


def filter_realms(realms, rtype="all", template="all", has_room=False, only=None):
    """Directory order for the Realms list: official, then verified, then the rest; busiest first."""
    out = [r for r in realms
           if (rtype == "all" or rf(r, "type", "") == rtype)
           and (template == "all" or rf(r, "template", "") == template)
           and (not has_room or realm_has_room(r))
           and (only is None or realm_key(r) in only)]
    return sorted(out, key=lambda r: (realm_group(r), -int(rf(r, "population", 0) or 0), str(rf(r, "name", "")).lower()))


def first(d, *keys, default=None):
    """The first of `keys` present in dict d (status dicts from p2p.host / p2p.torrent)."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def fmt_rate(kbps):
    try:
        kbps = float(kbps)
    except (TypeError, ValueError):
        return "—"
    return f"{kbps / 1024:.1f} MB/s" if kbps >= 1024 else f"{kbps:.0f} KB/s"


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        register_fonts()
        self._pick_display_font()
        self.defaults = read_json(os.path.join(DATA_DIR, "defaults.json"), {})
        # links: the shipped app\data\links.txt, then the signed live content, then the player's own links.txt
        self.links = read_links_txt([DATA_DIR]) if os.path.abspath(DATA_DIR) != os.path.abspath(INSTALL_DIR) else {}
        self.live = live_content.LiveContent(LIVE_CACHE, self.links.get("LIVE_CONTENT_URL")
                                             or read_links_txt([INSTALL_DIR]).get("LIVE_CONTENT_URL"), MANIFEST_PUBKEY)
        self.live.load_cached()
        self.links.update(self.live.doc.get("links", {}))
        self.links.update(read_links_txt([INSTALL_DIR]))
        self.defaults = apply_links_overrides(self.defaults, self.links)
        if self.live.doc.get("realms"):   # live realm defaults replace the shipped ones (custom realms stay)
            self.defaults["realms"] = list(self.live.doc["realms"]) + [r for r in self.defaults.get("realms", [])
                                                                        if r.get("host") in LOCAL_HOSTS]
        self.version = read_version()
        self.settings = read_json(SETTINGS_PATH, {})
        self.update_ready = None    # updater info when a newer release is staged ("Update ready")
        self.realms = list(self.defaults.get("realms", [])) + list(self.settings.get("custom_realms", []))
        if not self.realms:
            self.realms = [{"name": "Local server", "host": "127.0.0.1", "port": 3724, "portal": "http://127.0.0.1:18090"}]
        self.realm_index = min(int(self.settings.get("realm_index", 0)), len(self.realms) - 1)
        # the realm picked last time, by its address: the list can gain realms (Duels) and shift
        saved_host = self.settings.get("realm_host")
        if saved_host:
            by_host = next((i for i, r in enumerate(self.realms) if r.get("host") == saved_host), None)
            if by_host is not None:
                self.realm_index = by_host
        elif self.realm_index == 1 and len(self.realms) > 2 and self.realms[1].get("host") == "duels.openvanilla.app":
            # saved before Duels joined the list: index 1 was the local server
            self.realm_index = next((i for i, r in enumerate(self.realms) if r.get("host") in LOCAL_HOSTS), 0)
        # First run: look for a 1.12.1 install in the usual places, so most players never see the folder picker.
        if not wow_data_dir(self.settings.get("wow_folder", "")):
            found = wow_import.autodetect()
            if found:
                self.settings["wow_folder"] = str(found.parent)
                write_json(SETTINGS_PATH, self.settings)
        self._wow_issues = wow_problems(self.settings["wow_folder"]) if self.settings.get("wow_folder") else []
        # --realm HOST ("Play Solo.bat" host/lan/public): this session plays on HOST through this PC's own web backend. Not saved.
        if "--realm" in sys.argv[1:-1]:
            host = sys.argv[sys.argv.index("--realm") + 1]
            hit = next((i for i, r in enumerate(self.realms) if r.get("host") == host), None)
            if hit is None:
                self.realms.append({"name": f"Local test ({host})", "host": host, "port": 3724,
                                    "portal": "http://127.0.0.1:18090", "build": 5875})
                hit = len(self.realms) - 1
            self.realm_index = hit
        self.realm_state = {}       # index -> dict(status, ping, detail)
        self.clients = self._load_clients()
        ids = [c["id"] for c in self.clients]
        self.client_index = ids.index(self.settings["client"]) if self.settings.get("client") in ids else 0
        self.directory = dict(self.defaults.get("directory", {}))   # community servers / mods / repacks
        self.dir_state = {}         # "host:port" -> ping result for directory servers
        self.job = None             # the running download (update, mod, repack, repo) or Play Solo
        self.solo_session = None    # PLAY SOLO running (play_local.SoloSession, the older solo pack)
        self.solo_run = None        # PLAY > Solo running (spp.SoloPlay)
        self.dedicated = None       # HOST > Dedicated server (server_host.Dedicated), made on first use
        self.busy_tracker = solo.BusyTracker() if solo else None
        self.busy_hushed = None     # the busy state the player already saw a notice for
        # Realms / Host / Downloads (launcher/p2p, optional)
        self.p2p = dict(realms=None, error="", loading=False, pings={}, invite_text="", joining=False, join_session=None,
                        filters=dict({"type": "all", "template": "all", "show": "all", "room": False},
                                     **self.settings.get("p2p_filters", {})))
        self._p2p_paint_after = None
        self._p2p_dialog = None
        self.p2p_host = None        # p2p.host.HostSession while this PC hosts a realm
        self.portal_bridge = None   # p2p.bridge.PortalBridge: the desktop game on a browser realm (no game ports)
        self.p2p_host_state = None  # "Starting…", progress text, …
        self.p2p_host_status = {}
        self._host_polling = False
        self.p2p_torrents = None    # p2p.torrent.Torrents, made on first use
        self._dl_gen = 0
        self.p2p_node = None        # p2p.node.NodeService (Become a node), made on first use; off by default
        self._node_gen = 0
        self._node_board = dict(data=None, error="", loading=False)
        self._tray = None
        self.gh = dict(query="", results=None, error="", busy=False)
        self.tab_state = {"servers": "realms", "mods": "repacks", "host": "realm"}
        self.ws_query = ""  # the Workshop's one search box, shared by every sub-tab
        self.wsx = dict(index=None, error="", busy=False)  # Workshop > ADDONS: the site's addon catalogue
        self.patch_notes = read_json(os.path.join(DATA_DIR, "patch_notes.json"), {})
        self.update_info = None     # manifest dict when a newer build exists
        self.download = None        # dict(progress, done, path, error)
        self.page = "play"
        self.images = {}
        self.page_widgets = []
        self.hit = {}               # canvas item -> callbacks, for image buttons
        self._t0 = time.perf_counter()
        self._tick_n = 0
        self._slide = None
        self._notice = None         # (text, color, until)
        self.busy = None            # text while an account request runs
        self.session = {}           # user, password, realm, verified
        self._bg_files = sorted(
            os.path.join(ASSETS, "bg", f) for f in os.listdir(os.path.join(ASSETS, "bg"))
        ) if os.path.isdir(os.path.join(ASSETS, "bg")) else []
        self._bg_q = queue.Queue(maxsize=2)
        self._bg_i = 0

        self.title("Open Vanilla Launcher")
        self.configure(bg=BG)
        self._place_window()
        self.resizable(False, False)
        try:
            self.iconphoto(True, ImageTk.PhotoImage(art.kit_image("emblem", height=64)))
        except (tk.TclError, Exception):
            pass
        if sys.platform == "win32":
            # A real .ico (16-256 px, the same emblem as the release exe) for the taskbar and Alt+Tab.
            # Run from source (Play Open Vanilla.bat), the window would otherwise show Python's icon.
            try:
                ico = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "OpenVanilla", "openvanilla.ico")
                if not os.path.isfile(ico):
                    os.makedirs(os.path.dirname(ico), exist_ok=True)
                    art.emblem(256).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
                self.iconbitmap(default=ico)
                self._ico_path = ico
            except Exception:
                pass
        self._style_ttk()
        self._load_cursors()

        self.cv = tk.Canvas(self, width=WIN_W, height=WIN_H, bg=BG, highlightthickness=0, bd=0,
                            cursor=self.CUR_ARROW)
        self.cv.place(x=0, y=0)
        self.cv.bind("<Button-1>", self._canvas_click, add="+")
        self.configure(cursor=self.CUR_ARROW)
        self._build_static()
        self._apply_chrome()
        self._restore_session()
        self.show_page("play", animate=False)
        self._bg_worker_start()
        self.after(FPS_MS, self._tick)
        self.after(80, self._bg_step)
        self.refresh_realms()
        self.check_for_update()
        self.load_directory()
        register_link_handler()   # openvanilla:// links open this launcher, also for installs that predate the name
        # openvanilla://join/… (or https://play.openvanilla.app/join/…) on the command line: the OS hands invite links here.
        sys.argv[1:] = [legacy_link(a) for a in sys.argv[1:]]
        invite = next((a for a in sys.argv[1:] if parse_link(a)), None)
        if invite:
            self.tab_state["servers"] = "realms"
            self.after(700, lambda: (self.show_page("servers", animate=False), self.open_invite(invite)))
        # openvanilla://workshop/install/<id>[,<id>…]: the site's Install buttons.
        ws_link = next((a for a in sys.argv[1:] if workshop and workshop.parse_link(a)), None)
        if ws_link:
            self.tab_state["mods"] = "workshop"
            self.after(700, lambda: (self.show_page("mods", animate=False), self.workshop_install(workshop.parse_link(ws_link))))
        if self.settings.get("p2p_torrent", {}).get("seeding"):
            self.after(3000, self.torrents)  # the player opted in to seeding earlier: carry on
        if self.settings.get("p2p_node", {}).get("enabled"):
            self.after(4000, self._node_resume)  # the volunteer ran a node last time (and agreed to today's text)
        self._nowplaying_start()
        if ai_setup:   # counts the launch; once, from the second launch, offers the optional AI card
            ai_setup.on_start(self, LAYOUT.data)

    # ----- Now playing ("Share what I'm listening to", off by default; launcher/nowplaying.py)

    def _nowplaying_roots(self):
        engines = [CONFIG_DIR]
        wows = [self.settings.get("wow_folder", "")]
        for c in getattr(self, "clients", []):
            try:
                exe = self.client_exe(c)
            except Exception:  # noqa: BLE001
                exe = None
            if exe and exe != "web":
                d = os.path.dirname(exe)
                (engines if c.get("type") == "engine" else wows).append(
                    os.path.join(d, "benilla-config") if c.get("type") == "engine" else d)
        return [e for e in dict.fromkeys(engines) if e], [w for w in dict.fromkeys(wows) if w]

    def _nowplaying_save(self):
        try:  # from the worker thread: no dialogs
            write_json(SETTINGS_PATH, self.settings)
        except OSError:
            pass

    def _nowplaying_start(self):
        if not nowplaying:
            return
        self.nowplaying = nowplaying.NowPlaying(os.path.join(STATE_DIR, "nowplaying.json"), self._nowplaying_roots,
                                                lambda: self.settings, self._nowplaying_save)
        self.nowplaying.start()

    def _spotify_client_id(self):
        return (self.settings.get("spotify_client_id") or self.defaults.get("spotify_client_id") or "").strip()

    def _link_spotify(self):
        cid = self._spotify_client_id()
        if not nowplaying or not cid:
            self.notice("Spotify linking needs the launcher's Spotify app id (spotify_client_id in defaults.json).", AMBER, 6)
            return
        self.notice("Sign in to Spotify in your browser…", GOLD, 6)

        def work():
            try:
                sp = nowplaying.link_spotify(cid, safe_open)
            except Exception as e:  # noqa: BLE001
                msg = f"Spotify: {e}"[:110]
                self.after(0, lambda: self.notice(msg, RED, 6))
                return
            self.settings["spotify"] = sp
            self._nowplaying_save()
            self.after(0, lambda: (self.notice("Spotify linked.", GREEN), self.show_page("settings", animate=False)))
        threading.Thread(target=work, daemon=True).start()

    def _unlink_spotify(self):
        self.settings.pop("spotify", None)
        self.save_settings()
        self.notice("Spotify unlinked from this launcher.", GREEN)
        self.show_page("settings", animate=False)

    # ================================================================ setup

    def _load_cursors(self):
        """The gauntlet cursor (Windows .cur); plain Tk cursors elsewhere."""
        self.CUR_ARROW, self.CUR_HAND = "arrow", "hand2"
        if sys.platform != "win32":
            return
        cdir = os.path.join(ASSETS, "cursors")
        try:
            a, h = os.path.join(cdir, "hand.cur"), os.path.join(cdir, "link.cur")
            if os.path.isfile(a) and os.path.isfile(h):
                arrow = ("@" + a.replace("\\", "/"),)  # a Tcl list, so paths with spaces survive
                hand = ("@" + h.replace("\\", "/"),)
                probe = tk.Frame(self, cursor=arrow)
                probe.configure(cursor=hand)
                probe.destroy()
                self.CUR_ARROW, self.CUR_HAND = arrow, hand
        except tk.TclError:
            pass

    def _pick_display_font(self):
        global DISPLAY_FAMILY
        fams = {f.lower(): f for f in tkfont.families(self)}
        for cand in ("Cinzel", "Cinzel SemiBold", "Georgia", "DejaVu Serif"):
            if cand.lower() in fams:
                DISPLAY_FAMILY = fams[cand.lower()]
                return

    def _place_window(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = max(0, (sw - WIN_W) // 2), max(0, (sh - WIN_H) // 2 - 20)
        self.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

    def _style_ttk(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Dark.Vertical.TScrollbar", background="#6b5426", troughcolor="#120e16", bordercolor="#3a2f22",
                     arrowcolor=GOLD, lightcolor="#8a6c32", darkcolor="#4a3a1c", gripcount=0, arrowsize=11, width=11)
        st.map("Dark.Vertical.TScrollbar", background=[("active", "#a07c38")], arrowcolor=[("active", "#ffe68a")])

    def _safe_itemconfig(self, item, **kw):
        try:
            self.cv.itemconfig(item, **kw)
        except tk.TclError:
            pass

    def img(self, key, pil):
        self.images[key] = ImageTk.PhotoImage(pil)
        return self.images[key]

    # ---------- window chrome

    def _apply_chrome(self):
        self.custom_chrome = not self.settings.get("native_titlebar", False)
        if not self.custom_chrome:
            self._dark_titlebar()
            return
        self.overrideredirect(True)
        if sys.platform == "win32":
            self.after(10, self._win_taskbar_fix)
        self.bind("<Map>", self._on_map)

    def _win_taskbar_fix(self):
        """An overrideredirect window has no taskbar button; give it one back (WS_EX_APPWINDOW)."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self._win_set_icon(hwnd)
            v = ctypes.c_int(2)  # Windows 11 rounded corners
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v), ctypes.sizeof(v))
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception:
            pass

    def _win_set_icon(self, hwnd):
        """Tk doesn't give a borderless (overrideredirect) window its icon, so Windows falls back to
        the program's own icon: pythonw's when run from source. Hand the emblem to the window and its
        class directly, for the taskbar button, Alt+Tab and the window list."""
        ico = getattr(self, "_ico_path", None)
        if not ico or not hwnd:
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            u.LoadImageW.restype = ctypes.c_void_p
            u.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x0080
            big = u.LoadImageW(None, ico, IMAGE_ICON, u.GetSystemMetrics(11) or 32, u.GetSystemMetrics(12) or 32, LR_LOADFROMFILE)
            small = u.LoadImageW(None, ico, IMAGE_ICON, u.GetSystemMetrics(49) or 16, u.GetSystemMetrics(50) or 16, LR_LOADFROMFILE)
            if big:
                u.SendMessageW(hwnd, WM_SETICON, 1, big)
            if small:
                u.SendMessageW(hwnd, WM_SETICON, 0, small)
            if hasattr(u, "SetClassLongPtrW"):
                u.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                if big:
                    u.SetClassLongPtrW(hwnd, -14, big)    # GCLP_HICON
                if small:
                    u.SetClassLongPtrW(hwnd, -34, small)  # GCLP_HICONSM
            self._win_icons = (big, small)  # keep the handles alive with the window
        except Exception:
            pass

    def _on_map(self, _e=None):
        if self.custom_chrome and not self.overrideredirect() and self.state() == "normal":
            self.overrideredirect(True)
            if sys.platform == "win32":
                self.after(10, self._win_taskbar_fix)

    def minimize(self):
        if self.custom_chrome:
            self.overrideredirect(False)
        self.iconify()

    def _dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            for attr, val in ((20, 1), (19, 1), (35, 0x000B090B), (36, 0x0079D1F3)):
                v = ctypes.c_int(val)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass

    def _drag_start(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        if self.custom_chrome and getattr(self, "_drag", None):
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    # ---------- generic canvas button (image that swaps on hover)

    def ibutton(self, x, y, normal, hover, command, tags=(), anchor="nw", pressed=None, key=None):
        key = key or f"ib_{len(self.images)}"
        n, h = self.img(key + "_n", normal), self.img(key + "_h", hover)
        p = self.img(key + "_p", pressed) if pressed is not None else h
        item = self.cv.create_image(x, y, image=n, anchor=anchor, tags=tags)

        def enter(_):
            self.cv.itemconfig(item, image=h)
            self.cv.config(cursor=self.CUR_HAND)

        def leave(_):
            self.cv.itemconfig(item, image=n)
            self.cv.config(cursor=self.CUR_ARROW)

        def press(_):
            # Act on press: release events are not reliable on an overrideredirect window on Windows.
            self.cv.itemconfig(item, image=p)
            self.after(90, lambda: self._safe_itemconfig(item, image=h))
            self.after(10, command)

        self.cv.tag_bind(item, "<Enter>", enter)
        self.cv.tag_bind(item, "<Leave>", leave)
        self.cv.tag_bind(item, "<Button-1>", press)
        return item

    # Label colour per button style; gold buttons take dark lettering cut into the metal.
    BTN_FG = {"gold": "#3b2106", "discord": "#ffffff", "violet": "#ece6da", "danger": "#ffe9e4"}

    def _button_images(self, w, h, label, style, size, icon):
        key = f"btn_{style}_{w}x{h}_{size}_{icon}_{label}"
        if key + "_n" not in self.images:
            fg = self.BTN_FG.get(style, "#f0dca8")
            ic = None
            if icon:
                ic = art.discord_logo(16) if icon == "discord" else (
                    art.github_logo(16) if icon == "github" else art.icon(icon, 16, fg if style != "ghost" else GOLD))
            px = round(size * 1.45) + 1
            for state, hover in (("n", False), ("h", True)):
                self.img(f"{key}_{state}", art.button_face(art.pill(w, h, style, hover), label, px, fg,
                                                           engraved=(style == "gold"), icon_img=ic))
        return self.images[key + "_n"], self.images[key + "_h"]

    def pill_button(self, x, y, w, h, label, command, style="ghost", tags=("page",), size=9, anchor="nw", icon=None):
        """A rounded button: kit pill art with an embossed label (and icon), as one clickable image."""
        if anchor == "center":
            x, y = x - w // 2, y - h // 2
        elif anchor == "ne":
            x = x - w
        n, hv = self._button_images(w, h, label, style, size, icon)
        item = self.cv.create_image(x, y, image=n, anchor="nw", tags=tags)

        def enter(_):
            self.cv.itemconfig(item, image=hv)
            self.cv.config(cursor=self.CUR_HAND)

        def leave(_):
            self.cv.itemconfig(item, image=n)
            self.cv.config(cursor=self.CUR_ARROW)

        self.cv.tag_bind(item, "<Enter>", enter)
        self.cv.tag_bind(item, "<Leave>", leave)
        self.cv.tag_bind(item, "<Button-1>", lambda e: self.after(10, command))
        return item

    def link_text(self, x, y, text, command, size=9, color=GOLD_DIM, anchor="w", tags=("page",), display=False):
        item = self.cv.create_text(x, y, anchor=anchor, text=text, fill=color,
                                   font=font(size, "bold", display), tags=tags)
        self.cv.tag_bind(item, "<Button-1>", lambda e: command())
        self.cv.tag_bind(item, "<Enter>", lambda e: (self.cv.itemconfig(item, fill=GOLD), self.cv.config(cursor=self.CUR_HAND)))
        self.cv.tag_bind(item, "<Leave>", lambda e: (self.cv.itemconfig(item, fill=color), self.cv.config(cursor=self.CUR_ARROW)))
        return item

    def shadow_text(self, x, y, text, size=10, fill=TEXT, anchor="w", tags=("page",), weight="bold", display=True, width=None):
        kw = dict(anchor=anchor, font=font(size, weight, display), tags=tags)
        if width:
            kw["width"] = width
        s = self.cv.create_text(x + 1, y + 2, text=text, fill="#000000", **kw)
        t = self.cv.create_text(x, y, text=text, fill=fill, **kw)
        return t, s

    # ================================================================ static chrome

    def _build_static(self):
        cv = self.cv
        # background art + particles
        self.bg_item = cv.create_image(ART_X, ART_Y, anchor="nw")
        first = self._bg_files[0] if self._bg_files else os.path.join(ASSETS, "bg_static.jpg")
        if os.path.isfile(first):
            cv.itemconfig(self.bg_item, image=self.img("bg", self._cover(Image.open(first))))
        self._init_particles()

        # top bar
        cv.create_image(0, 0, anchor="nw", image=self.img("topbar", self._topbar_bg()), tags="drag")
        cv.tag_bind("drag", "<ButtonPress-1>", self._drag_start)
        cv.tag_bind("drag", "<B1-Motion>", self._drag_move)
        self._build_tabs()
        self._build_topright()

        # left rail
        cv.create_image(0, 0, anchor="nw", image=self.img("rail", self._rail_bg()), tags="drag")
        self.emblem_frames = [ImageTk.PhotoImage(f) for f in art.emblem_frames(64, 48)]
        self.emblem_item = cv.create_image(RAIL // 2, TOP // 2 + 1, image=self.emblem_frames[0], tags="drag")
        self._build_rail()

        # bottom bar
        self._build_bottom()

        # the site's hero logo, hanging over the top bar's edge like a crest
        logo_path = os.path.join(ASSETS, "logo_hero.png")
        if os.path.isfile(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((round(logo.width * 104 / logo.height), 104), Image.Resampling.LANCZOS)
            cv.create_image(RAIL + 4, -4, anchor="nw", image=self.img("logo", logo), tags=("drag", "logo"))
        else:
            cv.create_image(RAIL + 14, TOP // 2 + 1, anchor="w", image=self.img("logo", art.wordmark("OPEN VANILLA", 25)),
                            tags=("drag", "logo"))

        # frame border over everything
        cv.create_rectangle(0, 0, WIN_W - 1, WIN_H - 1, outline="#5a4626", width=1, tags="border")

    def _cover(self, im):
        """Scale a background frame to cover the art area, centred."""
        im = im.convert("RGB")
        s = max(ART_W / im.width, ART_H / im.height)
        im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.Resampling.BILINEAR)
        x0 = (im.width - ART_W) // 2
        y0 = int((im.height - ART_H) * 0.42)
        return im.crop((x0, y0, x0 + ART_W, y0 + ART_H))

    def _topbar_bg(self):
        from PIL import ImageDraw
        im = art._gradient(WIN_W, TOP, (22, 19, 24, 255), (10, 8, 12, 255))
        d = ImageDraw.Draw(im)
        d.line([(0, TOP - 2), (WIN_W, TOP - 2)], fill=(0, 0, 0, 255), width=1)
        d.line([(0, TOP - 1), (WIN_W, TOP - 1)], fill=(150, 116, 52, 255), width=1)
        return im

    def _rail_bg(self):
        from PIL import ImageDraw
        im = art._gradient(RAIL, WIN_H, (16, 13, 18, 255), (9, 7, 11, 255))
        d = ImageDraw.Draw(im)
        d.line([(RAIL - 2, 0), (RAIL - 2, WIN_H)], fill=(0, 0, 0, 255))
        d.line([(RAIL - 1, 0), (RAIL - 1, WIN_H)], fill=(110, 86, 42, 255))
        d.line([(10, TOP - 1), (RAIL - 2, TOP - 1)], fill=(110, 86, 42, 255))
        return im

    # ---------- tabs

    # Host your own realm directly from the launcher or the browser console.
    TABS = [("play", "HOME", "play"), ("mods", "WORKSHOP", "mods"),
            ("servers", "REALMS", "realms"), ("host", "HOST", "server"), ("notes", "NEWS", "news")]

    def visible_tabs(self):
        """The top tabs; live.json can switch the Workshop off (flags.workshop)."""
        hidden = set()
        if not self.live.flag("workshop"):
            hidden.add("mods")
        return [t for t in self.TABS if t[0] not in hidden]

    def _build_tabs(self):
        self.tab_items = {}
        x = RAIL + 200
        y = TOP // 2 + 1
        for key, label, ico in self.visible_tabs():
            imgs = {s: self.img(f"tab_{key}_{s}", art.tab(label, ico, active=(s == "a"), hover=(s == "h")))
                    for s in ("n", "h", "a")}
            item = self.cv.create_image(x, y, image=imgs["n"], anchor="w")
            self.tab_items[key] = (item, imgs)
            self.cv.tag_bind(item, "<Enter>", lambda e, k=key: self._tab_hover(k, True))
            self.cv.tag_bind(item, "<Leave>", lambda e, k=key: self._tab_hover(k, False))
            self.cv.tag_bind(item, "<Button-1>", lambda e, k=key: self.show_page(k))
            x += imgs["n"].width() + 6
        self.tab_line = self.cv.create_rectangle(0, TOP - 4, 0, TOP - 2, fill=GOLD, outline="")
        self._tab_line_pos = None

    def _tab_hover(self, key, on):
        item, imgs = self.tab_items[key]
        self.cv.config(cursor=self.CUR_HAND if on else "")
        if key != self.page:
            self.cv.itemconfig(item, image=imgs["h"] if on else imgs["n"])

    def _set_tabs(self, page):
        target = None
        for key, (item, imgs) in self.tab_items.items():
            self.cv.itemconfig(item, image=imgs["a"] if key == page else imgs["n"])
            if key == page:
                x0, y0, x1, y1 = self.cv.bbox(item)
                target = (x0 + 10, x1 - 10)
        if target is None:
            self.cv.itemconfig(self.tab_line, state="hidden")
        else:
            self.cv.itemconfig(self.tab_line, state="normal")
            self._tab_line_target = target
            if self._tab_line_pos is None:
                self._tab_line_pos = target

    # ---------- top right: status pill, account chip, window buttons

    def _build_topright(self):
        cv = self.cv
        right = WIN_W - 12
        if True:  # window buttons (drawn even with the native title bar hidden, they no-op there)
            self.win_btns = []
            close = art.kit_image("win_close", height=24)
            mini = art.kit_image("win_min", height=24)
            bright = lambda im: Image.eval(im, lambda v: min(255, int(v * 1.25)))
            self.ibutton(right, 8, close, bright(close), self.close_app, anchor="ne", key="wclose", tags=("chrome",))
            self.ibutton(right - 30, 8, mini, bright(mini), self.minimize, anchor="ne", key="wmin", tags=("chrome",))
        # account chip
        self.chip_x = WIN_W - 76
        self.chip_items = []
        self._paint_chip()
        # realm status pill
        self.pill_bg = cv.create_image(0, TOP // 2 + 1, anchor="e")
        self.pill_dot = cv.create_image(0, TOP // 2 + 1)
        self.pill_halo = cv.create_image(0, TOP // 2 + 1)
        self.pill_txt_sh = cv.create_text(0, TOP // 2 + 2, anchor="w", text="", fill="#000000", font=font(9, "bold"))
        self.pill_txt = cv.create_text(0, TOP // 2 + 1, anchor="w", text="", fill=MUTED, font=font(9, "bold"))
        self._paint_pill()

    def _paint_chip(self):
        cv = self.cv
        for it in self.chip_items:
            cv.delete(it)
        self.chip_items = []
        user = self.session.get("user")
        x_right = WIN_W - 76
        if user:
            name = self.session.get("display") or user.capitalize()
            sub = "Online" if self.session.get("verified") else ("Signed in" if self.session.get("password") else "Signed out")
            col = GREEN if self.session.get("verified") else AMBER
        elif getattr(self, "_discord_flow", None):
            name, sub, col = "Signing in…", "Finish in your browser", AMBER
        else:
            name, sub, col = "Sign in", "Google or Hero Key", MUTED
        fnt = tkfont.Font(font=font(10, "bold"))
        tw = max(fnt.measure(name), tkfont.Font(font=font(8)).measure(sub))
        w = 44 + tw + 18
        x0 = x_right - w
        bg = cv.create_image(x0, 10, anchor="nw", image=self.img("chip_bg", art.pill(w, 46, "ghost")))
        av = cv.create_image(x0 + 6, 33, anchor="w", image=self.img("chip_av", art.avatar(36, (self.session.get("display") or user)[:1] if user else "?")))
        dot = cv.create_image(x0 + 37, 45, image=self.img("chip_dot", art.dot(10, col)))
        s1 = cv.create_text(x0 + 49, 27, anchor="w", text=name, fill="#000000", font=font(10, "bold"))
        t1 = cv.create_text(x0 + 48, 26, anchor="w", text=name, fill=TEXT, font=font(10, "bold"))
        s2 = cv.create_text(x0 + 49, 43, anchor="w", text=sub, fill="#000000", font=font(8))
        t2 = cv.create_text(x0 + 48, 42, anchor="w", text=sub, fill=col, font=font(8))
        self.chip_items = [bg, av, dot, s1, t1, s2, t2]
        self.chip_left = x0
        for it in self.chip_items:
            cv.tag_bind(it, "<Button-1>", lambda e: self._chip_click())
            cv.tag_bind(it, "<Enter>", lambda e: cv.config(cursor=self.CUR_HAND))
            cv.tag_bind(it, "<Leave>", lambda e: cv.config(cursor=self.CUR_ARROW))
        if hasattr(self, "pill_txt"):
            self._paint_pill()

    def _chip_click(self):
        """Signed in → the account page. Not signed in → the saved Hero Key signs in at once, else the
        account page with Google and Hero Key."""
        if not (self.session.get("user") and self.session.get("password")) and not getattr(self, "_discord_flow", None):
            if self._saved_hero_key():
                self.sign_in_auto()
        self.show_page("account")

    def _paint_pill(self):
        st = self.realm_state.get(self.realm_index)
        status = st["status"] if st else "checking"
        label = {"online": "Online", "partial": "Partly up", "offline": "Offline", "checking": "Checking"}[status]
        if st and st.get("ping") is not None and status != "offline":
            label += f"  {st['ping']} ms"
        col = {"online": GREEN, "partial": AMBER, "offline": RED, "checking": MUTED}[status]
        fnt = tkfont.Font(font=font(9, "bold"))
        w = fnt.measure(label) + 38
        right = self.chip_left - 10
        self.cv.coords(self.pill_bg, right, TOP // 2 + 1)
        self.cv.itemconfig(self.pill_bg, image=self.img("pill_bg", art.pill(w, 28, "ghost")))
        self.cv.coords(self.pill_dot, right - w + 16, TOP // 2 + 1)
        self.cv.coords(self.pill_halo, right - w + 16, TOP // 2 + 1)
        self.cv.itemconfig(self.pill_dot, image=self.img("pill_dot", art.dot(10, col)))
        self._halo_frames = [self.img(f"halo_{i}", art.halo(30, col, int(40 + 90 * (0.5 + 0.5 * math.sin(i / 12 * 2 * math.pi)))))
                             for i in range(12)]
        self.cv.itemconfig(self.pill_halo, image=self._halo_frames[0])
        self.cv.coords(self.pill_txt, right - w + 27, TOP // 2 + 1)
        self.cv.coords(self.pill_txt_sh, right - w + 28, TOP // 2 + 2)
        self.cv.itemconfig(self.pill_txt, text=label, fill=col)
        self.cv.itemconfig(self.pill_txt_sh, text=label)
        self._pill_status = status

    # ---------- rail

    def _build_rail(self):
        for it in getattr(self, "rail_items", []):
            self.cv.delete(it)
        self.rail_items = []
        self.rail_y = {}
        y = TOP + 44
        for i, r in enumerate(self.realms):
            self._rail_medallion(f"realm{i}", y, None, r.get("name", "?"), lambda i=i: self.select_realm(i),
                                 tip=r.get("name", r.get("host")), realm=i)
            y += 60
        self._rail_medallion("addrealm", y, "plus", None, lambda: self.show_page("servers"), tip="Add or find a server")
        self._rail_medallion("support", WIN_H - 160, "heart", None, lambda: self.show_page("support"), tip="Support the realm")
        self._rail_medallion("settings", WIN_H - 104, "settings", None, lambda: self.show_page("settings"), tip="Settings")
        self._rail_medallion("help", WIN_H - 48, "help", None, lambda: self.show_page("help"), tip="Help")
        ind = self.cv.create_rectangle(0, 0, 4, 0, fill=CYAN, outline="")
        glow = self.cv.create_rectangle(4, 0, 6, 0, fill="#1f6f94", outline="")
        self.rail_items += [ind, glow]
        self.rail_ind = (ind, glow)
        self._rail_ind_y = None
        self._paint_rail()

    def _rail_medallion(self, key, y, icon_name, letter, command, tip="", realm=None):
        cx = RAIL // 2
        if realm is not None and realm == 0 and art.kit("emblem_small") is not None:
            base = art.kit_image("emblem_small", height=48)
            imgs = {"n": base, "h": Image.eval(base, lambda v: min(255, int(v * 1.2))), "a": Image.eval(base, lambda v: min(255, int(v * 1.25)))}
        else:
            imgs = {s: art.medallion(46, icon_name, letter, active=(s == "a"), hover=(s == "h")) for s in ("n", "h", "a")}
        imgs = {s: self.img(f"rail_{key}_{s}", im) for s, im in imgs.items()}
        item = self.cv.create_image(cx, y, image=imgs["n"])
        self.rail_items.append(item)
        self.rail_y[key] = (y, item, imgs, realm)

        def enter(_):
            self.cv.config(cursor=self.CUR_HAND)
            if not self._rail_active(key):
                self.cv.itemconfig(item, image=imgs["h"])
            self._show_tip(RAIL + 8, y, tip)

        def leave(_):
            self.cv.config(cursor=self.CUR_ARROW)
            self.cv.itemconfig(item, image=imgs["a"] if self._rail_active(key) else imgs["n"])
            self._hide_tip()

        self.cv.tag_bind(item, "<Enter>", enter)
        self.cv.tag_bind(item, "<Leave>", leave)
        self.cv.tag_bind(item, "<Button-1>", lambda e: command())

    def _rail_active(self, key):
        y, item, imgs, realm = self.rail_y[key]
        if realm is not None:
            return realm == self.realm_index
        return {"addrealm": "servers", "support": "support", "settings": "settings", "help": "help"}.get(key) == self.page

    def _paint_rail(self):
        target = None
        for key, (y, item, imgs, realm) in self.rail_y.items():
            on = self._rail_active(key)
            self.cv.itemconfig(item, image=imgs["a"] if on else imgs["n"])
            if realm is not None and on:
                target = y
        self._rail_ind_target = target
        if target is not None and self._rail_ind_y is None:
            self._rail_ind_y = target

    def _show_tip(self, x, y, text):
        self._hide_tip()
        if not text:
            return
        fnt = tkfont.Font(font=font(9, "bold"))
        w = fnt.measure(text) + 20
        bg = self.cv.create_image(x, y, anchor="w", image=self.img("tip_bg", art.pill(w, 26, "ghost", True)), tags="tip")
        self.cv.create_text(x + w // 2, y, text=text, fill=TEXT, font=fnt, tags="tip")

    def _hide_tip(self):
        self.cv.delete("tip")

    # ---------- bottom bar

    def _build_bottom(self):
        cv = self.cv
        y0 = WIN_H - BOT
        cy = y0 + BOT // 2 + 2
        cv.create_image(RAIL, y0, anchor="nw", image=self.img("botbar", self._bottom_bg()))

        # how PLAY plays: ONLINE | SOLO | BROWSER (one PLAY button; the switch replaces the old client
        # dropdown and the separate PLAY IN BROWSER / PLAY SOLO buttons). The client line under it opens
        # the client menu only when there is more than one desktop client.
        x = RAIL + 12
        cv.create_image(x, cy, anchor="w", image=self.img("bot_emblem", art.kit_image("emblem_small", height=58)))
        dd_x, dd_w = x + 64, 214
        self.dd_x, self.dd_top = dd_x, cy - 25
        self.mode_y = cy - 12
        self.dd_label = cv.create_text(dd_x + 2, cy + 17, anchor="w", text="", fill=TAN, font=font(8))
        self.dd_name = cv.create_text(dd_x + 2, cy + 30, anchor="w", text="", fill=MUTED, font=font(7))
        for it in (self.dd_label, self.dd_name):
            cv.tag_bind(it, "<Button-1>", lambda e: self._client_line_click())
            cv.tag_bind(it, "<Enter>", lambda e: cv.config(cursor=self.CUR_HAND))
            cv.tag_bind(it, "<Leave>", lambda e: cv.config(cursor=self.CUR_ARROW))
        self._paint_modes()

        # PLAY
        play_w = 236
        self.play_x = WIN_W - 14 - play_w
        self.play_imgs = {s: self.img(f"play_{s}", art.kit_play(play_w, s)) for s in ("normal", "hover", "pressed", "disabled")}
        ph = self.play_imgs["normal"].height()
        self.play_y = cy - ph // 2
        self.play_glow_frames = [self.img(f"pglow_{i}", art.kit_glow(play_w, ph, 0.35 + 0.65 * (0.5 + 0.5 * math.sin(i / 24 * 2 * math.pi))))
                                 for i in range(24)]
        self.play_glow = cv.create_image(self.play_x - 22, self.play_y - 22, anchor="nw", image=self.play_glow_frames[0])
        self.play_item = cv.create_image(self.play_x, self.play_y, anchor="nw", image=self.play_imgs["normal"])
        self.play_sub = cv.create_text(self.play_x + play_w // 2, WIN_H - 7, text="", fill=MUTED, font=font(7, "bold"))
        cv.tag_bind(self.play_item, "<Enter>", lambda e: self._play_hover(True))
        cv.tag_bind(self.play_item, "<Leave>", lambda e: self._play_hover(False))
        cv.tag_bind(self.play_item, "<Button-1>", lambda e: self._play_press())
        self._hover = False
        self._play_enabled = True

        # dragons and the energy bar between them
        dl = art.kit_image("dragon_left", height=78)
        dr = art.kit_image("dragon_right", height=78)
        left = dd_x + dd_w + 6
        right = self.play_x - 8
        self.dragon_l = cv.create_image(left, WIN_H - 2, anchor="sw", image=self.img("dragon_l", dl))
        self.dragon_r = cv.create_image(right, WIN_H - 2, anchor="se", image=self.img("dragon_r", dr))
        self.bar_x0 = left + dl.width - 24
        self.bar_x1 = right - dr.width + 24  # mirrors the left overlap: each gryphon's jaw holds a bar end
        self.bar_w = self.bar_x1 - self.bar_x0
        self.bar_h = 54
        self.bar_cy = cy + 6
        self.bar_item = cv.create_image(self.bar_x0, self.bar_cy, anchor="w")
        bx = self.bar_x0 + self.bar_w / 2
        self.bar_shadow = cv.create_text(bx + 1, self.bar_cy + 1, text="", fill="#000000", font=font(10, "bold", True))
        self.bar_text = cv.create_text(bx, self.bar_cy - 1, text="", fill="#ffffff", font=font(10, "bold", True))
        self.bar_side = cv.create_text(self.bar_x1 - 26, WIN_H - 7, anchor="e", text="", fill=TAN,
                                       font=font(9, "bold"))
        self.bar_detail = cv.create_text(bx, y0 + 15, text="", fill=MUTED, font=font(8))
        cv.tag_bind(self.bar_side, "<Button-1>", lambda e: self._update_click())
        for it in (self.bar_item, self.bar_text, self.bar_shadow, self.bar_detail):
            cv.tag_bind(it, "<Button-1>", lambda e: self._status_click())
            cv.tag_bind(it, "<Enter>", lambda e: cv.config(cursor=self.CUR_HAND))
            cv.tag_bind(it, "<Leave>", lambda e: cv.config(cursor=self.CUR_ARROW))
        self.bar_state = dict(style="blue", fraction=1.0, indeterminate=False)
        cv.tag_raise(self.dragon_l)
        cv.tag_raise(self.dragon_r)

        self._fill_client_label()
        self.update_status()

    def _bottom_bg(self):
        from PIL import ImageDraw
        w, h = WIN_W - RAIL, BOT
        im = art._gradient(w, h, (34, 28, 24, 255), (14, 11, 10, 255))
        d = ImageDraw.Draw(im)
        d.line([(0, 0), (w, 0)], fill=(0, 0, 0, 255), width=2)
        d.line([(0, 2), (w, 2)], fill=(168, 128, 58, 255), width=2)
        d.line([(0, 4), (w, 4)], fill=(60, 44, 20, 255), width=1)
        # faint stone grain
        rnd = random.Random(7)
        for _ in range(900):
            x, y = rnd.randrange(w), rnd.randrange(6, h)
            v = rnd.randrange(-14, 14)
            r, g, b, a = im.getpixel((x, y))
            im.putpixel((x, y), (max(0, r + v), max(0, g + v), max(0, b + v), 255))
        return im

    def _fill_realm_label(self):
        """Realm changes repaint the parts that show it (the rail, and the line under the mode switch)."""
        self._paint_rail()
        self._fill_client_label()

    # ---------- clients (the bottom-left picker)

    def client_catalog(self):
        """Every known client (Workshop > CLIENTS): defaults.json `clients` and `clients_parked`, the maintainer's
        live `clients`, and clients.txt in the user-data folder (launcher/game_clients.py merges them)."""
        builtin = self.defaults.get("clients") or [
            {"id": "openvanilla", "name": "Open Vanilla Classic+", "version": "1.12.1", "type": "engine",
             "exe": "OpenVanilla.exe", "build": 5875},
            {"id": "web", "name": "Open Vanilla in Browser", "version": "Web", "type": "web", "build": 5875}]
        return game_clients.catalog(builtin, self.defaults.get("clients_parked", []),
                                    self.live.doc.get("clients", []) if getattr(self, "live", None) else [],
                                    game_clients.read_clients_txt(LAYOUT.clients_txt))

    def _load_clients(self):
        """The HOME dropdown: the built-in clients plus the ones added in Workshop > CLIENTS."""
        clients = game_clients.my_clients(self.client_catalog(), self.settings.get("my_clients", []))
        for c in clients:  # the player's own links and install folders override the defaults
            c.update({k: v for k, v in self.settings.get("clients", {}).get(c["id"], {}).items() if v})
            # a 1.12.1 stock client uses the same install the importer found or the player locked in
            if c.get("type") == "exe" and int(c.get("build", 0) or 0) == wow_import.BUILD and not c.get("path"):
                if self.settings.get("wow_folder"):
                    c["path"] = self.settings["wow_folder"]
        return clients

    def reload_clients(self):
        """Rebuild the dropdown (live content arrived, a client was added or removed), keeping the selection."""
        cur = self.clients[self.client_index]["id"] if getattr(self, "clients", None) else self.settings.get("client")
        self.clients = self._load_clients()
        ids = [c["id"] for c in self.clients]
        self.client_index = ids.index(cur) if cur in ids else 0
        if hasattr(self, "dd_label"):
            self._fill_client_label()

    def client(self):
        return self.clients[self.client_index]

    def client_exe(self, c=None):
        """The program PLAY starts for this client, or None when it is not installed."""
        c = c or self.client()
        if c["type"] == "web":
            return "web"
        if c["type"] == "engine":
            p = c.get("path")
            if p and os.path.isfile(p):
                return p
            return find_engine()
        folder = c.get("path")
        if not folder or not os.path.isdir(folder):
            return None
        names = [c.get("exe", "Wow.exe"), "Wow.exe", "WoW.exe", "wow.exe"]
        for n in names:
            if os.path.isfile(os.path.join(folder, n)):
                return os.path.join(folder, n)
        return None

    def client_download(self, c=None):
        c = c or self.client()
        if c.get("download_url"):
            return c["download_url"]
        if c["type"] == "engine" and self.update_info and self.update_info.get("url"):
            return self.update_info["url"]
        return None

    def client_addons_dir(self, c=None):
        """Where the launcher manages addons: the shared AddOns\\Enabled folder for every client.
        (PLAY copies them into the client's own folder: see sync_client_addons.)"""
        return ADDONS_DIR

    def client_own_addons_dir(self, c=None):
        """The folder the game itself loads addons from."""
        c = c or self.client()
        if c["type"] == "engine":
            exe = self.client_exe(c)
            return os.path.join(os.path.dirname(exe), "benilla-config", "AddOns") if exe else None
        if c["type"] == "exe" and c.get("path"):
            return os.path.join(c["path"], "Interface", "AddOns")
        return None

    def sync_client_addons(self, c=None):
        """Mirror AddOns\\Enabled into the client before it starts (never touching the player's own addons)."""
        try:
            res = layout.sync_addons(ADDONS_DIR, self.client_own_addons_dir(c))
        except OSError as e:
            self.notice(f"Couldn't copy your addons into the game: {e}"[:110], AMBER, 6)
            return None
        if res["skipped"]:
            self.notice(f"Kept your own copy of {', '.join(res['skipped'][:3])} in the game's AddOns folder.", AMBER, 6)
        return res

    # ---------- play modes (the switch at the bottom left)

    def play_modes(self):
        """The modes this launcher offers: live.json flags, and only what this build can actually do."""
        # SPP Classics and the Solo pack are Windows programs; on macOS and Linux a solo realm is HOST >
        # Dedicated server > "This computer only" (Docker, launcher/docker_host.py)
        win = SOLO_ON_THIS_OS
        return home_logic.play_modes(self.live.flags, have_spp=bool(spp) and win, have_solo_pack=bool(solo) and win)

    def advanced(self):
        """Settings > Advanced: developer controls (client download links, GitHub search, Downloads tab)."""
        return bool(self.settings.get("advanced"))

    def play_mode(self):
        return home_logic.pick_mode(self.settings.get("play_mode", "online"), self.play_modes())

    def set_play_mode(self, mode):
        self._close_menu()
        self.settings["play_mode"] = mode
        self.save_settings()
        self._paint_modes()
        self._fill_client_label()
        self.update_status()
        if self.page == "play":
            self.show_page("play", animate=False)

    def _paint_modes(self):
        self.cv.delete("modes")
        modes = self.play_modes()
        cur = self.play_mode()
        gap = 4
        bw = (214 - gap * (len(modes) - 1)) // max(1, len(modes))
        for i, (key, label) in enumerate(modes):
            self.pill_button(self.dd_x + i * (bw + gap), self.mode_y - 13, bw, 26, label,
                             lambda k=key: self.set_play_mode(k), style="gold" if key == cur else "ghost",
                             tags=("modes",), size=8)

    def desktop_clients(self):
        return [c for c in self.clients if c.get("type") != "web"]

    def _client_line_click(self):
        mode = self.play_mode()
        if mode == "online":   # always: the menu also leads to Workshop > CLIENTS
            self._client_menu()
        elif mode == "solo":
            self.show_page("solo")
        elif mode == "browser":
            self.show_page("servers")
        else:
            self.show_page("settings")

    def _fill_client_label(self):
        c = self.client()
        mode = self.play_mode()
        realm = self.realms[self.realm_index] if self.realms else {}
        if mode == "browser":
            line1, line2 = "Plays in your web browser", fit_text(realm.get("name", ""), font(7), 210)
        elif mode == "solo":
            line1, line2 = "Your own world on this PC  ›", "SPP Classics · playerbots · offline"
        else:
            line1 = fit_text(c['name'], font(8), 196) + "  ▾"
            line2 = fit_text(realm.get("name", ""), font(7), 210)
        self.cv.itemconfig(self.dd_label, text=line1)
        self.cv.itemconfig(self.dd_name, text=line2)

    def select_client(self, i):
        self._close_menu()
        self.client_index = i
        self.settings["client"] = self.clients[i]["id"]
        self.save_settings()
        self._fill_client_label()
        self.update_status()
        if self.page in ("play", "mods", "settings"):
            self.show_page(self.page, animate=False)

    def _client_menu(self):
        if self.cv.find_withtag("menu"):
            self._close_menu()
            return
        cv = self.cv
        # embedded Tk widgets always draw above canvas items: tuck the page's widgets away while the menu is open
        self._menu_hidden = [it for it in cv.find_withtag("page") if cv.type(it) == "window" and cv.itemcget(it, "state") != "hidden"]
        for it in self._menu_hidden:
            cv.itemconfig(it, state="hidden")
        rows = len(self.clients)
        w, rh = 330, 54
        h = 54 + rows * rh + 34   # + "More clients in Workshop ›"
        x, y = self.dd_x - 4, self.dd_top - h - 8
        cv.create_image(x, y, anchor="nw", image=self.img("menu_bg", art.kit_panel(w, h, fill=(14, 11, 18, 246))), tags="menu")
        cv.create_text(x + 22, y + 26, anchor="w", text="CHOOSE YOUR GAME CLIENT", fill=GOLD,
                       font=font(9, "bold", True), tags="menu")
        for i, c in enumerate(self.clients):
            ry = y + 44 + i * rh
            sel = i == self.client_index
            base = "#2a2014" if sel else "#0f0c13"
            hl = cv.create_rectangle(x + 12, ry, x + w - 12, ry + rh - 6, fill=base,
                                     outline=GOLD_DIM if sel else "#0f0c13", tags="menu")
            ico = {"engine": "play", "web": "web"}.get(c["type"], "realms")
            exe = self.client_exe(c)
            if exe:
                sub, col = ("Streams in your browser" if c["type"] == "web" else "Installed"), GREEN
            elif self.client_download(c):
                sub, col = "Not installed · click PLAY's bar to get it", AMBER
            else:
                sub, col = (c.get("note") or ("Coming soon" if c.get("coming_soon") else "Not set up · Settings → Game clients")), MUTED
            items = [hl,
                     cv.create_image(x + 40, ry + (rh - 6) // 2, tags="menu",
                                     image=self.img(f"menu_ic_{i}", art.medallion(38, ico, active=sel))),
                     cv.create_text(x + 70, ry + 16, anchor="w", text=c["name"], fill=GOLD if sel else TEXT,
                                    font=font(10, "bold"), tags="menu"),
                     cv.create_text(x + w - 26, ry + 16, anchor="e", text=c.get("version", ""), fill=TAN,
                                    font=font(9, "bold"), tags="menu"),
                     cv.create_text(x + 70, ry + 34, anchor="w", text=sub, fill=col, font=font(8), tags="menu")]
            row_tag = f"menurow{i}"
            for it in items:
                cv.addtag_withtag(row_tag, it)
            cv.tag_bind(row_tag, "<Enter>", lambda e, hl=hl, base=base: (cv.itemconfig(hl, fill="#33281a" if base == "#2a2014" else "#1d1724"),
                                                                     cv.config(cursor=self.CUR_HAND)))
            cv.tag_bind(row_tag, "<Leave>", lambda e, hl=hl, base=base: (cv.itemconfig(hl, fill=base), cv.config(cursor=self.CUR_ARROW)))
            cv.tag_bind(row_tag, "<Button-1>", lambda e, i=i: self._menu_pick(i))
        my = y + 44 + rows * rh + 2
        more = cv.create_text(x + 22, my + 12, anchor="w", text="More clients in Workshop  ›", fill=GOLD,
                              font=font(9, "bold"), tags=("menu", "menumore"))
        cv.tag_bind("menumore", "<Enter>", lambda e: (cv.itemconfig(more, fill=TEXT), cv.config(cursor=self.CUR_HAND)))
        cv.tag_bind("menumore", "<Leave>", lambda e: (cv.itemconfig(more, fill=GOLD), cv.config(cursor=self.CUR_ARROW)))
        cv.tag_bind("menumore", "<Button-1>", lambda e: self._menu_more())
        cv.tag_raise("menu")
        cv.tag_raise("border")

    def _menu_more(self):
        """The client menu's last row: Workshop > CLIENTS."""
        self._menu_opened = True
        self.after(1, self.open_workshop_clients)

    def open_workshop_clients(self):
        self._close_menu()
        self.tab_state["mods"] = "clients"
        self.show_page("mods", animate=False)

    def _menu_pick(self, i):
        self._menu_opened = True
        self.after(1, lambda: self.select_client(i))

    def _canvas_click(self, _e):
        """Any click outside the open client menu closes it."""
        if getattr(self, "_menu_opened", False):
            self._menu_opened = False
            return
        if self.cv.find_withtag("menu"):
            self._close_menu()

    def _close_menu(self):
        self._menu_opened = False
        self.cv.delete("menu")
        for it in getattr(self, "_menu_hidden", []):
            self._safe_itemconfig(it, state="normal")
        self._menu_hidden = []
        self.cv.config(cursor=self.CUR_ARROW)

    # ================================================================ animation

    def _init_particles(self):
        self.motes = []
        self.mote_imgs = {(s, h): ImageTk.PhotoImage(art.mote(s, h)) for s in (6, 9, 13, 18) for h in ("gold", "violet", "white")}
        rnd = random.Random()
        for _ in range(42):
            m = self._new_mote(rnd, initial=True)
            m["item"] = self.cv.create_image(m["x"], m["y"], image=self.mote_imgs[(m["s"], m["h"])], tags="fx")
            self.motes.append(m)

    def _new_mote(self, rnd, initial=False):
        s = rnd.choice((6, 6, 9, 9, 13, 18))
        return dict(x=rnd.uniform(ART_X, WIN_W), y=rnd.uniform(ART_Y, WIN_H - BOT) if initial else WIN_H - BOT + 10,
                    vy=-rnd.uniform(0.25, 0.9) * (1.4 if s < 10 else 0.8), sway=rnd.uniform(0.2, 1.1),
                    ph=rnd.uniform(0, 6.28), s=s, h=rnd.choice(("gold", "gold", "violet", "white")))

    def _tick(self):
        """One animation frame (~30 fps): motes, emblem, PLAY glow, energy bar, slides, indicators."""
        self._tick_n += 1
        n = self._tick_n
        t = time.perf_counter() - self._t0
        anim = self.settings.get("effects", True) and self.state() != "iconic"
        cv = self.cv
        if anim:
            rnd = random
            for m in self.motes:
                m["y"] += m["vy"]
                x = m["x"] + math.sin(t * m["sway"] + m["ph"]) * 0.6
                m["x"] = x
                if m["y"] < ART_Y - 10:
                    m.update(self._new_mote(rnd))
                    cv.itemconfig(m["item"], image=self.mote_imgs[(m["s"], m["h"])])
                cv.coords(m["item"], m["x"], m["y"])
            if n % 2 == 0:
                cv.itemconfig(self.emblem_item, image=self.emblem_frames[(n // 2) % len(self.emblem_frames)])
            if self._play_enabled:
                cv.itemconfig(self.play_glow, image=self.play_glow_frames[(n // 2) % len(self.play_glow_frames)], state="normal")
            if self._pill_status in ("online", "checking"):
                cv.itemconfig(self.pill_halo, image=self._halo_frames[(n // 3) % 12], state="normal")
        cv.itemconfig(self.fx_state_tag(), state="normal" if anim else "hidden")
        if not self._play_enabled:
            cv.itemconfig(self.play_glow, state="hidden")
        if self._pill_status not in ("online", "checking"):
            cv.itemconfig(self.pill_halo, state="hidden")

        # energy bar: animate while working or (gently) while idle
        if n % 2 == 0 and (anim or self.bar_state.get("dirty")):
            self._render_bar(t)

        # page slide-in
        if self._slide:
            step = self._slide
            k = min(1.0, (time.perf_counter() - step["t0"]) / 0.28)
            e = 1 - (1 - k) ** 3
            target = step["dy"] * (1 - e)
            cv.move("page", 0, target - step["cur"])
            step["cur"] = target
            if k >= 1:
                self._slide = None

        # tab underline and rail indicator glide
        if getattr(self, "_tab_line_target", None) and self._tab_line_pos:
            a, b = self._tab_line_pos
            ta, tb = self._tab_line_target
            a += (ta - a) * 0.25
            b += (tb - b) * 0.25
            self._tab_line_pos = (a, b)
            cv.coords(self.tab_line, a, TOP - 4, b, TOP - 2)
        if self._rail_ind_target is not None:
            y = self._rail_ind_y + (self._rail_ind_target - self._rail_ind_y) * 0.25
            self._rail_ind_y = y
            cv.coords(self.rail_ind[0], 0, y - 22, 4, y + 22)
            cv.coords(self.rail_ind[1], 4, y - 16, 6, y + 16)
            cv.itemconfig(self.rail_ind[0], state="normal")
            cv.itemconfig(self.rail_ind[1], state="normal")
        else:
            cv.itemconfig(self.rail_ind[0], state="hidden")
            cv.itemconfig(self.rail_ind[1], state="hidden")

        if n % 6 == 0 and ((self.download and not self.download.get("done")) or (self.job and not self.job.get("done"))):
            self.update_status()
        if self._notice and time.time() > self._notice[2]:
            self._notice = None
            self.update_status()
        self.after(FPS_MS, self._tick)

    def fx_state_tag(self):
        return "fx"

    def _render_bar(self, t):
        b = self.bar_state
        ind = (t * 0.55) % 1.0 if b.get("indeterminate") else None
        phase = (t * (0.22 if b.get("busy") else 0.06)) % 1.0
        im = art.kit_bar(self.bar_w, self.bar_h, b.get("fraction", 1.0), b.get("style", "blue"), phase=phase, indeterminate=ind)
        self.cv.itemconfig(self.bar_item, image=self.img("bar", im))
        b["dirty"] = False

    # ---------- background frames: decoded on a worker thread, swapped on the UI thread

    def _bg_worker_start(self):
        if len(self._bg_files) < 2:
            return

        def work():
            i = 0
            while True:
                if not self.settings.get("animated_background", True):
                    time.sleep(0.5)
                    continue
                i = (i + 1) % len(self._bg_files)
                try:
                    im = self._cover(Image.open(self._bg_files[i]))
                except OSError:
                    continue
                self._bg_q.put(im)  # blocks while the UI is two frames behind

        threading.Thread(target=work, daemon=True).start()

    def _bg_step(self):
        try:
            im = self._bg_q.get_nowait()
            if self.state() != "iconic":
                self.cv.itemconfig(self.bg_item, image=self.img("bg", im))
        except queue.Empty:
            pass
        self.after(80, self._bg_step)

    # ================================================================ pages

    def clear_page(self):
        self.cv.delete("page")
        for w in self.page_widgets:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.page_widgets = []
        self.cv.unbind_all("<MouseWheel>")

    def show_page(self, page, animate=True):
        self.page = page
        self._set_tabs(page)
        self.clear_page()
        getattr(self, f"page_{page}")()
        self._paint_rail()
        if hasattr(self, "play_item"):
            self._paint_update_button()
        self.cv.tag_raise("logo")
        self.cv.tag_raise("border")
        if animate and self.settings.get("effects", True):
            self.cv.move("page", 0, 22)
            self._slide = dict(dy=22, cur=22, t0=time.perf_counter())

    def big_panel(self, title, icon_name=None, subtitle=""):
        """The framed content area used by every page except Game Client. Returns (x, y, w, h) inside."""
        x, y = ART_X + 22, ART_Y + 18
        w, h = ART_W - 44, ART_H - 36
        self.cv.create_image(x, y, anchor="nw", image=self.img("bigpanel", art.kit_panel(w, h, fill=PANEL_RGBA, flat=True)),
                             tags="page")
        tx = x + 30
        if icon_name:
            self.cv.create_image(tx, y + 34, image=self.img(f"bp_ic_{icon_name}", art.icon(icon_name, 24, GOLD)), tags="page")
            tx += 22
        self.cv.create_image(tx, y + 34, anchor="w", image=self.img(f"bp_title_{title}", art.emboss_text(title, 19, "#f3d179")),
                             tags="page")
        if subtitle:
            self.cv.create_text(x + w - 64, y + 36, anchor="e", text=subtitle, fill=MUTED, font=font(9), tags="page")
        # close: back to Home
        xb = art.kit_image("win_close", height=28)
        self.ibutton(x + w - 22, y + 34, xb, Image.eval(xb, lambda v: min(255, int(v * 1.25))), lambda: self.show_page("play"),
                     anchor="e", tags=("page",), key="panel_close")
        self.cv.create_line(x + 26, y + 58, x + w - 26, y + 58, fill="#4a3b22", tags="page")
        return x + 28, y + 72, w - 56, h - 92

    def card(self, x, y, w, h, title, key):
        n = self.img(f"card_{key}_n", art.kit_panel(w, h))
        hv = self.img(f"card_{key}_h", art.kit_panel(w, h, hover=True))
        item = self.cv.create_image(x, y, anchor="nw", image=n, tags="page")
        self.cv.tag_bind(item, "<Enter>", lambda e: self.cv.itemconfig(item, image=hv))
        self.cv.tag_bind(item, "<Leave>", lambda e: self.cv.itemconfig(item, image=n))
        return item

    def frame_on(self, x, y, w, h, bg=PANEL):
        f = tk.Frame(self, bg=bg, highlightthickness=0, bd=0)
        self.cv.create_window(x, y, anchor="nw", window=f, width=w, height=h, tags="page")
        self.page_widgets.append(f)
        return f

    def wbutton(self, parent, text, command, primary=False, danger=False, style=None, icon=None, size=9):
        """A kit pill button for use inside frames, sized to its label (same art as pill_button)."""
        style = style or ("gold" if primary else ("danger" if danger else "ghost"))
        label = text.upper()
        px = round(size * 1.45) + 1
        w = art.button_label(label, px, "#ffffff").width + (22 if icon else 0) + 30
        n, hv = self._button_images(w, 32, label, style, size, icon)
        b = tk.Label(parent, image=n, bg=parent["bg"], bd=0, cursor=self.CUR_HAND)
        b.bind("<Enter>", lambda e: b.config(image=hv))
        b.bind("<Leave>", lambda e: b.config(image=n))
        b.bind("<Button-1>", lambda e: self.after(10, command))
        return b

    def entry(self, parent, show=None, width=28):
        e = tk.Entry(parent, width=width, bg=FIELD, fg=TEXT, insertbackground=GOLD, relief="flat", font=font(11),
                     highlightthickness=1, highlightbackground="#4a3b22", highlightcolor=GOLD_DIM, show=show or "")
        return e

    def check(self, parent, text, var, command=None):
        return tk.Checkbutton(parent, text=text, variable=var, command=command, bg=parent["bg"], fg=TEXT,
                              activebackground=parent["bg"], activeforeground=GOLD, selectcolor=FIELD,
                              highlightthickness=0, font=font(9), anchor="w", bd=0)

    def segmented(self, x, y, options, current, on_pick, w=170):
        """A row of pill tabs inside a page (MY REALMS | COMMUNITY …)."""
        for i, (key, label) in enumerate(options):
            self.pill_button(x + i * (w + 8), y, w, 32, label, lambda k=key: on_pick(k),
                             style="gold" if key == current else "ghost", size=8)

    def chip(self, parent, text, bg="#2a2014", fg=TAN):
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=font(7, "bold"), padx=6, pady=1,
                        highlightthickness=1, highlightbackground="#6b5426")

    def list_row(self, inner, bg="#17121c", border="#3a2f22"):
        row = tk.Frame(inner, bg=bg, highlightthickness=1, highlightbackground=border)
        row.pack(fill="x", pady=3, padx=2)
        return row

    def empty_state(self, inner, title, body):
        box = tk.Frame(inner, bg=PANEL)
        box.pack(fill="x", pady=40)
        tk.Label(box, text=title, bg=PANEL, fg=GOLD, font=font(12, "bold", True)).pack()
        tk.Label(box, text=body, bg=PANEL, fg=MUTED, font=font(9), wraplength=620, justify="center").pack(pady=(6, 0))

    def _set_tab(self, page, key):
        self.tab_state[page] = key
        self.show_page(page, animate=False)

    # ----- Game Client (home)

    def page_play(self):
        """Home: news, realm status, quick actions and account down the LEFT side, so the art stays clear."""
        cw = LEFT_W
        x = ART_X + 18
        y = ART_Y + 42
        gap = 9
        frame0 = self._bg_files[0] if self._bg_files else os.path.join(ASSETS, "bg_static.jpg")
        frame1 = self._bg_files[len(self._bg_files) // 2] if self._bg_files else frame0

        def clickable(item, command):
            self.cv.tag_bind(item, "<Button-1>", lambda e: command())

        # latest news
        h = 94
        c = self.card(x, y, cw, h, "notes", "notes")
        clickable(c, lambda: self.show_page("notes"))
        th = self.cv.create_image(x + 13, y + 13, anchor="nw", image=self.img("th_notes", art.thumb(frame0, 74, 68, (0.47, 0.45))), tags="page")
        clickable(th, lambda: self.show_page("notes"))
        notes = self.patch_notes or {}
        ver = notes.get("version") or self.version
        live_news = self.live.doc.get("news") or []
        if live_news:   # live content (downloads/live.json) first; the patch notes are one click away
            self.shadow_text(x + 100, y + 22, "LATEST NEWS", 9, GOLD)
            bullets = [n.get("title") or n.get("text", "") for n in live_news]
        else:
            self.shadow_text(x + 100, y + 22, f"LATEST NEWS  ·  {ver}", 9, GOLD)
            bullets = notes.get("highlights") or [n for sec in notes.get("sections", []) for n in sec.get("items", [])][:3]
        fnt8 = tkfont.Font(font=font(8))
        yy = y + 42
        for line in (bullets or ["Patch notes arrive with the next update."])[:3]:
            while fnt8.measure("•  " + line) > cw - 114 and len(line) > 4:
                line = line[:-2].rstrip() + "…" if not line.endswith("…") else line[:-3].rstrip() + "…"
            t = self.cv.create_text(x + 100, yy, anchor="w", text="•  " + line, fill=TEXT, font=fnt8, tags="page")
            clickable(t, lambda: self.show_page("notes"))
            yy += 16
        y += h + gap

        # selected server
        h = 90
        self.card(x, y, cw, h, "status", "status")
        self.cv.create_image(x + 13, y + 11, anchor="nw", image=self.img("th_status", art.thumb(frame1, 74, 68, (0.78, 0.30))), tags="page")
        self.shadow_text(x + 100, y + 20, "SERVER", 9, GOLD)
        self.status_items = {
            "name": self.cv.create_text(x + 100, y + 40, anchor="w", text="", fill=TEXT, font=font(9, "bold"), tags="page"),
            "state": self.cv.create_text(x + 100, y + 57, anchor="w", text="", fill=MUTED, font=font(8, "bold"), tags="page"),
            "detail": self.cv.create_text(x + 100, y + 73, anchor="w", text="", fill=MUTED, font=font(7), tags="page"),
        }
        self.link_text(x + cw - 16, y + 20, "Change ›", lambda: self.show_page("servers"), 8, anchor="e")
        self._paint_realm_status()
        y += h + gap

        # account
        h = 92 if self.session.get("user") else 136
        self.card(x, y, cw, h, "acct", "acct")
        self.shadow_text(x + 16, y + 20, "ACCOUNT", 9, GOLD)
        user = self.session.get("user")
        self.cv.create_image(x + 16, y + 56, anchor="w", image=self.img("acct_av", art.avatar(40, (self.session.get("display") or user)[:1] if user else "?")), tags="page")
        if user:
            self.cv.create_text(x + 66, y + 48, anchor="w", text=self.session.get("display") or user.capitalize(),
                                fill=TEXT, font=font(10, "bold"), tags="page")
            on = bool(self.session.get("password"))
            self.cv.create_text(x + 66, y + 66, anchor="w", text="Auto-login on PLAY" if on else "Signed out",
                                fill=GREEN if on else AMBER, font=font(8), tags="page")
            self.pill_button(x + cw - 14, y + 8, 96, 26, "MANAGE", lambda: self.show_page("account"), anchor="ne", size=8)
        else:
            self.cv.create_text(x + 66, y + 48, anchor="w", text="Not signed in", fill=TEXT, font=font(10, "bold"), tags="page")
            waiting = bool(getattr(self, "_discord_flow", None))
            self.cv.create_text(x + 66, y + 66, anchor="w", tags="page", font=font(8),
                                text="Finish signing in in your browser…" if waiting else "Google or your Hero Key",
                                fill=AMBER if waiting else MUTED)
            self.pill_button(x + cw - 14, y + 8, 96, 26, "SIGN IN", self._chip_click, style="gold", anchor="ne", size=8)
            self.pill_button(x + 16, y + 92, cw - 32, 30, "CONTINUE WITH GOOGLE", lambda: self.sign_in_google(),
                             style="gold", size=8)

        y += h + gap

        # the selected client: get it, set it up or change its folder (CANCEL DOWNLOAD while one runs)
        self._home_client_button(x, y, cw)

        # community buttons, bottom right, stacked with room for UPDATE READY above PLAY (no overlaps)
        pw = 196
        bx = WIN_W - 34 - pw
        by = ART_Y + ART_H - 46 - 44
        label, link = self.live.button("discord", "JOIN THE DISCORD", self.community_links().get("discord"))
        self.pill_button(bx, by, pw, 32, label, lambda l=link: self.open_live_link(l), style="discord", size=8, icon="discord")
        label, link = self.live.button("support", "SUPPORT THE REALM")
        self.pill_button(bx, by - 40, pw, 32, label, (lambda l=link: self.open_live_link(l)) if link else
                         (lambda: self.show_page("support")), style="ghost", size=8, icon="heart")

    def open_live_link(self, link):
        """A link from live content or a button: openvanilla://page/<page> opens a launcher page; https opens the browser."""
        link = live_content.safe_link(link)
        m = re.match(r"^openvanilla://page/([a-z]+)$", link or "")
        if m and m.group(1) in ("play", "notes", "mods", "host", "servers", "solo", "settings", "help", "support", "account"):
            self.show_page(m.group(1))
        elif link.startswith("openvanilla://"):
            if parse_link(link):
                self.tab_state["servers"] = "realms"
                self.show_page("servers", animate=False)
                self.open_invite(link)
            elif workshop and workshop.parse_link(link):
                self.tab_state["mods"] = "workshop"
                self.show_page("mods", animate=False)
                self.workshop_install(workshop.parse_link(link))
        elif link:
            safe_open(link)

    def _home_client_button(self, x, y, w):
        c = self.client()
        btn = home_logic.client_button(
            c["type"], bool(self.client_exe(c)), bool(self.client_download(c)),
            busy=bool(self.busy_download()), build=c.get("build", 5875))
        self._client_btn_label = btn[0] if btn else ""
        if not btn:
            return
        label, style, action = btn
        command = {"install": lambda: self.show_page("install"), "cancel": self.cancel_download,
                   "web": lambda: self.play_web()}.get(action, self.get_client)
        icon = {"cancel": "close", "web": "web"}.get(action, "download")
        self._client_btn_label = label
        self.pill_button(x, y, w, 32, label, command, style=style, size=8, icon=icon, tags=("page", "clientbtn"))

    def _paint_realm_status(self):
        if self.page != "play" or not getattr(self, "status_items", None):
            return
        realm = self.realms[self.realm_index]
        st = self.realm_state.get(self.realm_index)
        try:
            self.cv.itemconfig(self.status_items["name"], text=fit_text(realm.get("name", realm.get("host")), font(9, "bold"), LEFT_W - 118))
        except tk.TclError:
            return
        if not st:
            self.cv.itemconfig(self.status_items["state"], text="CHECKING…", fill=AMBER)
            self.cv.itemconfig(self.status_items["detail"], text=f"{realm.get('host')}:{realm.get('port', 3724)}")
            return
        color = {"online": GREEN, "partial": AMBER}.get(st["status"], RED)
        label = {"online": "ONLINE", "partial": "PARTLY UP", "offline": "OFFLINE"}[st["status"]]
        ping = f"  ({st['ping']} ms)" if st.get("ping") is not None else ""
        self.cv.itemconfig(self.status_items["state"], text=f"{label}{ping}", fill=color)
        self.cv.itemconfig(self.status_items["detail"], text=fit_text(st.get("detail", ""), font(7), LEFT_W - 118))

    # ----- Web play

    def web_url(self):
        r = self.realms[self.realm_index]
        url = r.get("portal") or self.defaults.get("community", {}).get("portal")
        return url.rstrip("/") + "/" if url else None

    def play_web(self, fullscreen=None):
        url = self.web_url()
        if not url:
            messagebox.showerror("Web play", "This realm has no website set. Pick another realm or add its portal URL on the Realms page.",
                                 parent=self)
            return
        if fullscreen is None:
            fullscreen = self.settings.get("web_fullscreen", True)
        if not safe_url(url):
            messagebox.showerror("Web play", "This realm's website isn't https, so it can't be opened.", parent=self)
            return
        ok, msg = launch_web(url, fullscreen)
        self.notice(msg, GREEN if ok else RED)
        if ok and self.settings.get("close_on_play"):
            self.after(1500, self.destroy)

    # ----- Patch notes

    def page_notes(self):
        n = self.patch_notes or {}
        x, y, w, h = self.big_panel(f"NEWS  ·  PATCH NOTES {n.get('version', '')}".strip(), "news", n.get("date", ""))
        tw = w - 330
        f = self.frame_on(x, y, tw, h, bg=PANEL)
        txt = tk.Text(f, bg=PANEL, fg=TEXT, relief="flat", wrap="word", font=font(10), padx=6, pady=4,
                      highlightthickness=0, bd=0, cursor=self.CUR_ARROW)
        sb = ttk.Scrollbar(f, orient="vertical", command=txt.yview, style="Dark.Vertical.TScrollbar")
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.tag_config("h2", foreground=GOLD, font=font(12, "bold", True), spacing1=12, spacing3=6)
        txt.tag_config("li", lmargin1=8, lmargin2=26, spacing3=3)
        txt.tag_config("hl", foreground=GOLD_DIM, font=font(10, "bold"))
        txt.tag_config("date", foreground=MUTED, font=font(8))
        for item in self.live.doc.get("news") or []:   # live news (downloads/live.json) above the patch notes
            txt.insert("end", (item.get("title") or "News") + "\n", "h2")
            if item.get("date"):
                txt.insert("end", item["date"] + "\n", "date")
            if item.get("text"):
                txt.insert("end", item["text"] + "\n", "li")
            if item.get("link", "").startswith("https://"):
                txt.insert("end", item["link"] + "\n", ("li", "hl"))
        if n.get("highlights"):
            txt.insert("end", "Highlights\n", "h2")
            for item in n["highlights"]:
                txt.insert("end", f"✦  {item}\n", ("li", "hl"))
        for sec in n.get("sections", []):
            txt.insert("end", sec.get("title", "") + "\n", "h2")
            for item in sec.get("items", []):
                txt.insert("end", f"•  {item}\n", "li")
        if not n:
            txt.insert("end", "No patch notes are bundled with this build. They arrive with the next update.")
        txt.config(state="disabled")
        self.cv.bind_all("<MouseWheel>", lambda e: txt.yview_scroll(int(-e.delta / 120), "units"))

        # community column
        cx, cwid = x + tw + 22, w - tw - 22
        self.shadow_text(cx, y + 8, "COMMUNITY", 10, GOLD)
        links = self.community_links()
        entries = (("portal", "Open Vanilla Portal", "link"), ("forums", "Forums", "chat"), ("mods", "Mod workshop", "mods"),
                   ("discord", "Discord", "chat"), ("github", "GitHub", "code"), ("bug_reports", "Report a bug", "bug"))
        yy = y + 30
        for key, title, ico in entries:
            url = links.get(key)
            self.card(cx, yy, cwid, 46, title, f"nl_{key}")
            self.cv.create_image(cx + 26, yy + 23, tags="page", image=self.img(f"nl_ic_{key}_{bool(url)}", art.icon(ico, 20, GOLD if url else "#5b5468")))
            self.cv.create_text(cx + 48, yy + 23, anchor="w", text=title, fill=TEXT if url else "#6f6758", font=font(9, "bold"), tags="page")
            if url:
                self.link_text(cx + cwid - 16, yy + 23, "Open ›", lambda u=url: safe_open(u), 8, anchor="e")
            else:
                self.cv.create_text(cx + cwid - 16, yy + 23, anchor="e", text="soon", fill="#6f6758", font=font(8), tags="page")
            yy += 52
        self.pill_button(cx, yy + 6, cwid, 34, "COPY INVITE", self.copy_invite, size=9)

    # ----- Community

    def community_links(self):
        links = dict(self.defaults.get("community", {}))
        portal = self.realms[self.realm_index].get("portal")
        if portal and not links.get("portal"):
            links["portal"] = portal.rstrip("/") + "/"
        if links.get("portal"):
            links.setdefault("forums", links["portal"].rstrip("/") + "/#tab-forum")
            links.setdefault("mods", links["portal"].rstrip("/") + "/#tab-mods")
        return {k: v for k, v in links.items() if v}

    def copy_invite(self):
        r = self.realms[self.realm_index]
        text = f"Join me on {r.get('name')}! Realm: {r.get('host')}"
        if r.get("portal"):
            text += f"  ·  Sign up / play in browser: {r['portal']}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.notice("Invite copied to clipboard")

    # ----- Addons

    def _scroll_list(self, x, y, w, h):
        f = self.frame_on(x, y, w, h, bg=PANEL)
        canvas = tk.Canvas(f, bg=PANEL, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview, style="Dark.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window(0, 0, anchor="nw", window=inner, width=w - 18)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.cv.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        return inner

    def page_mods(self):
        tab = self.tab_state.get("mods", "repacks")
        x, y, w, h = self.big_panel("WORKSHOP", "mods", "Addons install into AddOns\\Enabled, for every game client")
        segs = (("workshop", "ADDONS"), ("repacks", "PROJECTS"), ("clients", "CLIENTS"), ("installed", "INSTALLED"))
        if self.advanced():   # GitHub search is a developer control
            segs += (("search", "GITHUB"),)
        elif tab == "search":
            tab = "repacks"
        seg_w = {3: 150, 4: 118, 5: 106}.get(len(segs), 96)
        self.segmented(x, y - 4, segs, tab, lambda k: self._set_tab("mods", k), w=seg_w)
        sw = (seg_w + 8) * len(segs)
        self._workshop_search_bar(x + sw + 6, y - 4, w - sw - 6, tab)
        y, h = y + 38, h - 38
        if tab == "clients":
            self._mods_clients(x, y, w, h)
        elif tab == "search":
            self._mods_search(x, y, w, h)
        elif tab == "workshop":
            self._mods_workshop(x, y, w, h)
        elif tab == "repacks":
            self._mods_community(x, y, w, h, "repacks")
        else:
            self._mods_installed(x, y, w, h)

    def _workshop_search_bar(self, x, y, w, tab):
        """One search box for the whole Workshop: it filters Projects and Installed as you type,
        and Enter (or the button) searches GitHub for anything not listed here."""
        bar = self.frame_on(x, y, w, 34, bg=PANEL)
        e = self.entry(bar, width=24)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        e.insert(0, self.ws_query)
        hint = "Search projects, addons and GitHub…" if self.advanced() else "Search projects and addons…"
        if not self.ws_query:
            e.insert(0, hint)
            e.config(fg=MUTED)

            def clear_hint(_ev):
                if e.get() == hint:
                    e.delete(0, "end")
                    e.config(fg=TEXT)
            e.bind("<FocusIn>", clear_hint)
        self._ws_entry = e

        def typed(_ev):
            text = e.get()
            if text == hint:
                return
            if text != self.ws_query:
                self.ws_query = text
                # Re-filter after a short pause, keeping the caret where it was.
                if getattr(self, "_ws_after", None):
                    self.after_cancel(self._ws_after)
                self._ws_after = self.after(220, self._ws_refresh)

        e.bind("<KeyRelease>", typed)
        if self.advanced():
            e.bind("<Return>", lambda ev: self._ws_github(e.get()))
            self.wbutton(bar, "Search GitHub", lambda: self._ws_github(e.get()), primary=tab == "search",
                         size=8).pack(side="left", padx=(8, 0))
        if getattr(self, "_ws_keep_focus", False):
            self._ws_keep_focus = False
            e.focus_set()
            e.icursor("end")

    def _ws_refresh(self):
        self._ws_after = None
        if self.page != "mods":
            return
        if self.tab_state.get("mods") == "search":
            return  # GitHub results change only on Enter, not on every key
        self._ws_keep_focus = True
        self.show_page("mods", animate=False)

    def _ws_github(self, text):
        text = (text or "").strip()
        if not text or text.startswith("Search projects"):
            return
        self.ws_query = text
        self.github_search(text)

    def _ws_match(self, *fields):
        """True when every word of the Workshop search appears in one of `fields`."""
        q = self.ws_query.strip().lower()
        if not q:
            return True
        hay = " ".join(str(f or "") for f in fields).lower()
        return all(word in hay for word in q.split())

    def _ws_no_match(self, inner):
        q = self.ws_query.strip()
        box = tk.Frame(inner, bg=PANEL)
        box.pack(fill="x", pady=40)
        tk.Label(box, text=f"Nothing here matches “{q}”", bg=PANEL, fg=GOLD, font=font(12, "bold", True)).pack()
        if self.advanced():
            tk.Label(box, text="Press Enter to search GitHub for it instead.", bg=PANEL, fg=MUTED, font=font(9)).pack(pady=(6, 8))
            self.wbutton(box, "Search GitHub", lambda: self._ws_github(q), primary=True).pack()
        else:
            tk.Label(box, text="Try fewer words, or look in the ADDONS tab.", bg=PANEL, fg=MUTED, font=font(9)).pack(pady=(6, 8))

    def _mods_installed(self, x, y, w, h):
        target = self.client_addons_dir()
        if not target:
            inner = self._scroll_list(x, y, w, h)
            self.empty_state(inner, "The browser client manages its own addons",
                             "Pick a desktop client in the Game Client box (bottom left) to install and manage addons here.")
            return
        all_rows = list_addons(target)
        rows = [a for a in all_rows if self._ws_match(a["title"], a["name"], a["notes"])]
        n_on = sum(1 for a in all_rows if a["enabled"])
        self.cv.create_text(x, y + 12, anchor="w", fill=MUTED, font=font(9), tags="page",
                            text=f"{n_on} enabled · {len(all_rows) - n_on} off  ·  turning one off moves it aside; nothing is deleted")
        self.pill_button(x + w, y - 4, 180, 32, "INSTALL FROM .ZIP", self.install_addon_zip, style="gold", anchor="ne", size=8, icon="download")
        self.pill_button(x + w - 188, y - 4, 150, 32, "OPEN FOLDER", lambda: self.open_path(target), anchor="ne", size=8, icon="folder")
        inner = self._scroll_list(x, y + 36, w, h - 36)
        if not rows and all_rows:
            self._ws_no_match(inner)
        elif not rows:
            self.empty_state(inner, "No addons yet", "Grab some from the ADDONS tab, or install a .zip you already have.")
        for a in rows:
            row = self.list_row(inner)
            tk.Label(row, text="●", bg="#17121c", fg=GREEN if a["enabled"] else "#5b5468", font=font(11)).pack(side="left", padx=(12, 8), pady=9)
            txt = tk.Frame(row, bg="#17121c")
            txt.pack(side="left", fill="x", expand=True, pady=6)
            head = a["title"] + (f"   v{a['version']}" if a["version"] else "")
            tk.Label(txt, text=head, bg="#17121c", fg=TEXT if a["enabled"] else MUTED, font=font(10, "bold"), anchor="w").pack(fill="x")
            tk.Label(txt, text=a["notes"] or a["name"], bg="#17121c", fg=MUTED, font=font(8), anchor="w",
                     wraplength=w - 220, justify="left").pack(fill="x")
            self.wbutton(row, "Disable" if a["enabled"] else "Enable", lambda a=a: self.toggle_addon(a),
                         primary=not a["enabled"]).pack(side="right", padx=12)

    # ----- Workshop > CLIENTS (launcher/game_clients.py: defaults, the maintainer's live list, clients.txt)

    def _mods_clients(self, x, y, w, h):
        self.reload_clients()   # clients.txt may have changed since the last look
        entries = self.client_catalog()
        mine = {c["id"] for c in self.clients}
        rows = [e for e in entries if self._ws_match(e.get("name"), e.get("version"), e.get("description"), e.get("type"))]
        self.cv.create_text(x, y + 12, anchor="w", fill=MUTED, font=font(9), tags="page",
                            text="Game clients: add one to put it in the HOME client menu (bottom left)")
        self.pill_button(x + w, y - 4, 190, 32, "OPEN CLIENTS.TXT", self.open_clients_txt, anchor="ne", size=8, icon="folder")
        inner = self._scroll_list(x, y + 36, w, h - 36 - 30)
        if not rows and entries:
            self._ws_no_match(inner)
        source_label = {"builtin": "built in", "parked": "Open Vanilla", "live": "from Open Vanilla", "local": "clients.txt"}
        for e in rows:
            row = self.list_row(inner)
            ico = {"engine": "play", "web": "web"}.get(e.get("type"), "realms")
            tk.Label(row, image=self._tk_icon(ico), bg="#17121c").pack(side="left", padx=(12, 10), pady=10)
            box = tk.Frame(row, bg="#17121c")
            box.pack(side="left", fill="x", expand=True, pady=6)
            head = tk.Frame(box, bg="#17121c")
            head.pack(fill="x")
            tk.Label(head, text=e.get("name", "?"), bg="#17121c", fg=TEXT, font=font(10, "bold")).pack(side="left")
            if e.get("version"):
                tk.Label(head, text=e["version"], bg="#17121c", fg=MUTED, font=font(8)).pack(side="left", padx=6)
            soon = e.get("status") == "coming_soon"
            status = "COMING SOON" if soon else ("IN MY CLIENTS" if e["id"] in mine else "AVAILABLE")
            self.chip(head, status, fg=AMBER if soon else (GREEN if e["id"] in mine else TAN)).pack(side="left", padx=2)
            self.chip(head, source_label.get(e.get("source"), "")).pack(side="left", padx=2)
            tk.Label(box, text=e.get("description") or {"exe": "Your own game install (.exe)", "engine": "The Open Vanilla engine",
                                                         "web": "Plays in your web browser"}.get(e.get("type"), ""),
                     bg="#17121c", fg=TEXT, font=font(8), anchor="w", wraplength=w - 420, justify="left").pack(fill="x")
            if e["id"] in mine:
                if e.get("removable", True):
                    self.wbutton(row, "Remove", lambda e=e: self.workshop_remove_client(e)).pack(side="right", padx=(4, 12))
                else:
                    tk.Label(row, text="Always in the menu", bg="#17121c", fg=MUTED, font=font(8)).pack(side="right", padx=(4, 12))
            else:
                self.wbutton(row, "Add to my clients", lambda e=e: self.workshop_add_client(e),
                             primary=not soon).pack(side="right", padx=(4, 12))
            if e.get("url") and not soon and e.get("type") != "web":
                self.wbutton(row, "Download" if is_file_link(e["url"]) else "Get",
                             lambda e=e: self.workshop_get_client(e)).pack(side="right", padx=(0, 4))
            if e.get("page"):
                self.wbutton(row, "Page", lambda u=e["page"]: safe_open(u)).pack(side="right", padx=(0, 4))
        self.link_text(x, y + h - 12, "Your own clients: clients.txt in the Open Vanilla data folder ›",
                       self.open_clients_txt, 9)

    def workshop_add_client(self, e, select=False):
        game_clients.add(self.settings, e["id"])
        self.save_settings()
        self.reload_clients()
        if select:
            ids = [c["id"] for c in self.clients]
            if e["id"] in ids:
                self.client_index = ids.index(e["id"])
                self.settings["client"] = e["id"]
                self.save_settings()
                self._fill_client_label()
        else:
            self.notice(f"{e.get('name')} is in your client menu (HOME, bottom left).", GREEN, 4)
        self.update_status()
        if self.page == "mods":
            self.show_page("mods", animate=False)

    def workshop_remove_client(self, e):
        if not game_clients.remove(self.settings, e):
            return
        self.save_settings()
        self.reload_clients()
        self.settings["client"] = self.client()["id"]
        self.save_settings()
        self.update_status()
        if self.page == "mods":
            self.show_page("mods", animate=False)

    def workshop_get_client(self, e):
        """Download / Get: add the client, pick it, then the usual client download flow (get_client)."""
        self.workshop_add_client(e, select=True)
        self.get_client()

    def open_clients_txt(self):
        """clients.txt in the user-data folder (created with a commented example the first time)."""
        path = LAYOUT.clients_txt
        if not os.path.isfile(path):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:   # \r\n on Windows, for Notepad
                    f.write(game_clients.CLIENTS_TXT_EXAMPLE)
            except OSError as err:
                self.notice(f"Can't create {path}: {err}"[:110], RED, 6)
                return
        self.open_path(path)

    def _mods_community(self, x, y, w, h, kind):
        listed = self.directory.get(kind, [])
        items = [it for it in listed if self._ws_match(it.get("name"), it.get("description"), it.get("author"),
                                                      it.get("kind"), it.get("client"), " ".join(it.get("tags", [])))]
        live = self.directory.get("_live")
        self.cv.create_text(x + w, y - 26, anchor="e", fill=MUTED, font=font(8), tags="page",
                            text="Live list from the Open Vanilla directory" if live else "Offline copy (the directory couldn't be reached)")
        inner = self._scroll_list(x, y, w, h - 34)
        if not items and listed:
            self._ws_no_match(inner)
        elif not items:
            if kind == "mods":
                self.empty_state(inner, "No community mods listed yet", "Share yours through the directory, or search GitHub for addons.")
            else:
                self.empty_state(inner, "No projects listed yet", "Community games, tools and repacks published to the directory show up here.")
        for it in items:
            row = self.list_row(inner)
            ico = KIND_ICONS.get(it.get("kind"), "play" if kind == "repacks" else "mods")
            tk.Label(row, image=self._tk_icon(ico), bg="#17121c").pack(side="left", padx=(12, 10), pady=10)
            box = tk.Frame(row, bg="#17121c")
            box.pack(side="left", fill="x", expand=True, pady=6)
            head = tk.Frame(box, bg="#17121c")
            head.pack(fill="x")
            tk.Label(head, text=it.get("name", "?"), bg="#17121c", fg=TEXT, font=font(10, "bold")).pack(side="left")
            if it.get("version"):
                tk.Label(head, text=f"v{it['version']}", bg="#17121c", fg=MUTED, font=font(8)).pack(side="left", padx=6)
            for tag in [it.get("client"), it.get("kind")] + list(it.get("tags", []))[:3]:
                if tag:
                    self.chip(head, str(tag)).pack(side="left", padx=2)
            meta = "  ·  ".join(v for v in (f"by {it['author']}" if it.get("author") else "", fmt_size(it.get("size", 0))) if v)
            tk.Label(box, text=it.get("description", ""), bg="#17121c", fg=TEXT, font=font(8), anchor="w",
                     wraplength=w - 300, justify="left").pack(fill="x")
            if meta:
                tk.Label(box, text=meta, bg="#17121c", fg=MUTED, font=font(8), anchor="w").pack(fill="x")
            url = it.get("url")
            if url and kind == "mods":
                self.wbutton(row, "Install", lambda u=url, n=it.get("name", "mod"): self.install_from_url(u, n), primary=True).pack(side="right", padx=12)
            elif url:
                label = "GitHub" if "github.com/" in url and not is_file_link(url) else "Download"
                self.wbutton(row, label, lambda u=url, n=it.get("name", "repack"): self.fetch_or_open(u, n), primary=True).pack(side="right", padx=12)
            if it.get("homepage"):
                self.wbutton(row, "Page", lambda u=it["homepage"]: safe_open(u)).pack(side="right", padx=(0, 4))
        submit = self.defaults.get("directory_submit_url") or self.community_links().get("portal")
        if submit:
            noun = "mod" if kind == "mods" else "project"
            self.link_text(x, y + h - 12, f"Made a {noun}? Share it with the network ›", lambda: safe_open(submit), 9)
        self.link_text(x + w, y + h - 12, "Reload list", self.load_directory, 9, anchor="e")

    # ----- Workshop > ADDONS (the site's catalogue; launcher/workshop.py does the fetching and checking)

    def _workshop(self):
        site = self.defaults.get("workshop_site") or workshop.SITE
        return workshop.Workshop(site=site)

    def workshop_load(self):
        if not workshop or self.wsx.get("busy"):
            return
        self.wsx.update(busy=True, error="")

        def work():
            w = self._workshop()
            try:
                idx, err = w.load_index(), ""
            except Exception as e:  # noqa: BLE001
                idx, err = None, f"Can't reach the Workshop ({getattr(e, 'reason', e)})."
            self.after(0, self._workshop_loaded, idx, err)

        threading.Thread(target=work, daemon=True).start()

    def _workshop_loaded(self, idx, err):
        self.wsx.update(index=idx or self.wsx.get("index"), error=err, busy=False)
        if self.page == "mods" and self.tab_state.get("mods") == "workshop":
            self.show_page("mods", animate=False)

    def _mods_workshop(self, x, y, w, h):
        inner = self._scroll_list(x, y, w, h - 34)
        if not workshop:
            self.empty_state(inner, "The Workshop is not part of this launcher", "Update the launcher to browse the Workshop here.")
            return
        idx = self.wsx.get("index")
        if idx is None:
            if not self.wsx.get("busy") and not self.wsx.get("error"):
                self.workshop_load()
            self.empty_state(inner, "Loading the Workshop…" if not self.wsx.get("error") else "The Workshop didn't answer",
                             self.wsx.get("error") or "The addon catalogue from openvanilla.app.")
            if self.wsx.get("error"):
                self.wbutton(inner, "Try again", lambda: (self.wsx.update(error=""), self.workshop_load()), primary=True).pack()
            return
        ws = self._workshop()
        ws.index = idx
        rows = ws.cards(self.ws_query)
        if not rows:
            self._ws_no_match(inner)
        labels = {"works": ("Works", GREEN), "partly": ("Partly", AMBER), "needs-fixes": ("Needs fixes", RED), "unknown": ("Not checked", MUTED)}
        for c in rows[:200]:
            row = self.list_row(inner)
            box = tk.Frame(row, bg="#17121c")
            box.pack(side="left", fill="x", expand=True, padx=(14, 0), pady=6)
            head = tk.Frame(box, bg="#17121c")
            head.pack(fill="x")
            tk.Label(head, text=c.get("name", "?"), bg="#17121c", fg=TEXT, font=font(10, "bold")).pack(side="left")
            if c.get("ours"):
                self.chip(head, "Ours").pack(side="left", padx=4)
            lab, col = labels.get(c.get("compat"), labels["unknown"])
            self.chip(head, lab, fg=col).pack(side="left", padx=2)
            st = c.get("stats") or {}
            if st.get("votes"):
                tk.Label(head, text=f"★ {st.get('rating', 0):.1f} ({st['votes']})", bg="#17121c", fg=GOLD, font=font(8, "bold")).pack(side="left", padx=6)
            tk.Label(box, text=c.get("summary", ""), bg="#17121c", fg=TEXT, font=font(8), anchor="w",
                     wraplength=w - 300, justify="left").pack(fill="x")
            tk.Label(box, text=f"by {c.get('author', '?')}  ·  {c.get('license', '')}", bg="#17121c", fg=MUTED, font=font(7), anchor="w").pack(fill="x")
            page = ws.site + "workshop/addon.html?id=" + urllib.parse.quote(c["id"])
            if c.get("install"):
                self.wbutton(row, "Install", lambda i=c["id"]: self.workshop_install([i]), primary=True).pack(side="right", padx=12)
                self.wbutton(row, "Page", lambda u=page: safe_open(u)).pack(side="right")
            else:  # not ours to host: the site's page links to the author
                self.wbutton(row, "Get from author", lambda u=page: safe_open(u)).pack(side="right", padx=12)
        self.link_text(x, y + h - 12, "Ratings, reviews and collections are on openvanilla.app/workshop ›",
                       lambda: safe_open(self._workshop().site + "workshop.html"), 9)
        self.link_text(x + w, y + h - 12, "Reload list", lambda: (self.wsx.update(index=None), self.workshop_load()), 9, anchor="e")

    def workshop_install(self, ids):
        """Install Workshop addons by id (the ADDONS list, or an openvanilla://workshop/install link)."""
        target = self.client_addons_dir()
        if not workshop or not ids:
            return
        if not target:
            self.notice("Addons install into a desktop client. Pick one in the Game Client box.", AMBER, 5)
            return
        if self.wsx.get("installing"):
            self.notice("A Workshop install is still running.", AMBER)
            return
        self.wsx["installing"] = True
        self.notice(f"Installing {len(ids)} addon{'s' if len(ids) > 1 else ''} from the Workshop…", GOLD, 4)

        def work():
            try:
                res = self._workshop().install(ids, target, install_zip)
            except Exception as e:  # noqa: BLE001
                res = [{"id": i, "name": i, "ok": False, "error": str(e)} for i in ids]
            self.after(0, self._workshop_installed, res)

        threading.Thread(target=work, daemon=True).start()

    def _workshop_installed(self, res):
        self.wsx["installing"] = False
        self.wsx["last"] = res
        ok = any(r["ok"] for r in res)
        self.notice(workshop.summary(res), GREEN if ok and all(r["ok"] or r.get("link") for r in res) else AMBER, 6)
        for r in res:
            if not r["ok"] and r.get("link"):
                safe_open(r["link"])  # a link-out in a collection: the author's page, never a download
        if self.page == "mods":
            self.show_page("mods", animate=False)

    def _tk_icon(self, name, size=22, color=GOLD_DIM):
        key = f"tkicon_{name}_{size}_{color}"
        if key not in self.images:
            self.images[key] = ImageTk.PhotoImage(art.github_logo(size, color) if name == "github" else art.icon(name, size, color))
        return self.images[key]

    def toggle_addon(self, a):
        src = a["path"]
        dst_root = ADDONS_OFF_DIR if a["enabled"] else ADDONS_DIR
        os.makedirs(dst_root, exist_ok=True)
        dst = os.path.join(dst_root, os.path.basename(src))
        if os.path.exists(dst):
            messagebox.showerror("Addons", f"{os.path.basename(src)} already exists in {dst_root}.", parent=self)
            return
        try:
            shutil.move(src, dst)
        except OSError as e:
            messagebox.showerror("Addons", f"Could not move the addon (is the game running?)\n\n{e}", parent=self)
        self.show_page("mods", animate=False)

    def install_addon_zip(self):
        path = filedialog.askopenfilename(parent=self, title="Choose an addon .zip", filetypes=[("Zip archives", "*.zip")])
        if not path:
            return
        try:
            target = self.client_addons_dir()
            if not target:
                raise ValueError("Pick a desktop client in the Game Client box first.")
            installed = install_zip(path, target)
        except (OSError, zipfile.BadZipFile, ValueError) as e:
            messagebox.showerror("Install addon", str(e), parent=self)
            return
        self.notice("Installed: " + ", ".join(installed), GREEN)
        self.show_page("mods", animate=False)

    # ----- GitHub

    GH_PRESETS = (("Repacks", "wow repack"), ("Vanilla addons", "wow addon 1.12"), ("3.3.5a addons", "wow addon 3.3.5"),
                  ("vmangos", "vmangos"), ("AzerothCore", "azerothcore"), ("TrinityCore", "trinitycore 3.3.5"),
                  ("Open Vanilla", "openvanilla"))

    def _mods_search(self, x, y, w, h):
        """Workshop → Search: GitHub repositories (repacks, addons, server cores, tools)."""
        # The query comes from the Workshop's search box above; shortcuts fill it too.
        presets = self.frame_on(x, y - 4, w, 34, bg=PANEL)
        for label, q in self.GH_PRESETS:
            self.wbutton(presets, label, lambda q=q: self._ws_github(q), size=7).pack(side="left", padx=(0, 6))
        inner = self._scroll_list(x, y + 38, w, h - 38)
        if self.gh.get("busy"):
            self.empty_state(inner, "Searching GitHub…", f"“{self.gh['query']}”")
            return
        if self.gh.get("error"):
            self.empty_state(inner, "GitHub didn't answer", self.gh["error"])
            return
        results = self.gh.get("results")
        if results is None:
            self.empty_state(inner, "Find addons, server cores and tools",
                             "Type in the search box and press Enter, or pick a shortcut above. Addons install straight into the selected client; "
                             "anything else downloads as a .zip.")
            return
        if not results:
            self.empty_state(inner, "Nothing found", "Try fewer or different words.")
        for r in results:
            row = self.list_row(inner)
            box = tk.Frame(row, bg="#17121c")
            box.pack(side="left", fill="x", expand=True, padx=(14, 0), pady=7)
            head = tk.Frame(box, bg="#17121c")
            head.pack(fill="x")
            tk.Label(head, text=r["full_name"], bg="#17121c", fg=TEXT, font=font(10, "bold")).pack(side="left")
            tk.Label(head, text=f"★ {fmt_count(r.get('stargazers_count', 0))}", bg="#17121c", fg=GOLD, font=font(8, "bold")).pack(side="left", padx=8)
            if r.get("language"):
                self.chip(head, r["language"]).pack(side="left", padx=2)
            if r.get("archived"):
                self.chip(head, "archived", bg="#3a1a1a", fg=RED).pack(side="left", padx=2)
            tk.Label(box, text=(r.get("description") or "No description.")[:220], bg="#17121c", fg=TEXT, font=font(8),
                     anchor="w", wraplength=w - 330, justify="left").pack(fill="x")
            tk.Label(box, text=f"Updated {str(r.get('pushed_at', ''))[:10]}", bg="#17121c", fg=MUTED, font=font(7), anchor="w").pack(fill="x")
            zip_url = f"https://codeload.github.com/{r['full_name']}/zip/refs/heads/{r.get('default_branch', 'main')}"
            self.wbutton(row, "Install addon", lambda u=zip_url, n=r["name"]: self.install_from_url(u, n), primary=True).pack(side="right", padx=12)
            self.wbutton(row, "Download", lambda u=zip_url, n=r["name"]: self.start_job(u, n)).pack(side="right")
            self.wbutton(row, "Open", lambda u=r["html_url"]: safe_open(u)).pack(side="right", padx=8)

    def github_search(self, query):
        query = (query or "").strip()
        if not query:
            return
        self.gh = dict(query=query, results=None, error="", busy=True)
        self.tab_state["mods"] = "search"
        self.show_page("mods", animate=False)

        def work():
            url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
                {"q": query, "sort": "stars", "order": "desc", "per_page": 30})
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "OpenVanilla-Launcher", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = json.loads(r.read().decode("utf-8"))
                res, err = data.get("items", []), ""
            except urllib.error.HTTPError as e:
                res, err = None, ("GitHub's search limit was reached. Wait a minute and try again." if e.code in (403, 429)
                                  else f"GitHub answered HTTP {e.code}.")
            except Exception as e:
                res, err = None, f"Can't reach GitHub ({getattr(e, 'reason', e)})."
            self.after(0, self._github_done, query, res, err)

        threading.Thread(target=work, daemon=True).start()

    def _github_done(self, query, res, err):
        if self.gh.get("query") != query:
            return
        self.gh.update(results=res, error=err, busy=False)
        if self.page == "mods" and self.tab_state.get("mods") == "search":
            self.show_page("mods", animate=False)

    # ----- Host

    def classic_target(self):
        """Where a fresh 1.12.1 install goes (changeable on the setup page)."""
        return self.settings.get("classic_target") or os.path.join(os.path.expanduser("~"), "Games", "WoW-1.12.1")

    def _pick_classic_target(self):
        start = os.path.dirname(self.classic_target())
        parent = filedialog.askdirectory(parent=self, initialdir=start if os.path.isdir(start) else os.path.expanduser("~"),
                                         title="Choose where to put Vanilla Client v1.3 (a new game folder is made inside)")
        if parent:
            self.settings["classic_target"] = os.path.join(os.path.normpath(parent), "WoW-1.12.1")
            self.save_settings()
            self.show_page("install", animate=False)

    def _classic_part(self, c):
        url = self.client_download(c) or ""
        name = os.path.basename(urllib.parse.urlsplit(url).path)
        part = os.path.join(os.path.dirname(self.classic_target()), name + ".part") if name else ""
        return part if part and os.path.isfile(part) else None

    def _discard_part(self, part):
        if messagebox.askyesno("Discard download?", "Delete the partly downloaded game? The next install starts from zero.", parent=self):
            try:
                os.remove(part)
            except OSError as e:
                self.notice(f"Couldn't delete it: {e}"[:110], RED, 5)
            self.show_page("install", animate=False)

    def page_install(self):
        """Set up the 1.12.1 game: install a fresh copy into a new folder, or use one already on this PC."""
        c = next((k for k in self.clients if k.get("type") == "exe"), self.client())
        x, y, w, h = self.big_panel("SET UP VANILLA CLIENT V1.3", "download", "Open Vanilla needs the classic Vanilla game (build 5875)")
        cw, ch = (w - 20) // 2, 250
        url = self.client_download(c)
        # get the game: the client's own page opens in the browser (no download inside the launcher)
        self.card(x, y, cw, ch, "new", "inst_new")
        self.shadow_text(x + 22, y + 26, "GET THE GAME", 11, GOLD)
        self.cv.create_text(x + 22, y + 50, anchor="nw", fill=TEXT, font=font(9), width=cw - 44, tags="page",
                            text="Don't have it yet? This opens Vanilla Client v1.3's page on the Internet Archive "
                                 "in your browser. Download it there, unzip it anywhere (for example C:\\Games\\Vanilla), "
                                 "then come back and pick its Data folder.")
        if not url:
            self.cv.create_text(x + 22, y + ch - 42, anchor="w", text="No download page is set (links.txt: CLIENT_112_URL_TEMP).",
                                fill=AMBER, font=font(9), tags="page")
        else:
            self.pill_button(x + 22, y + ch - 60, cw - 44, 38, "OPEN THE DOWNLOAD PAGE", lambda: self.open_client_page(c),
                             style="gold", size=10, icon="download")
        # existing folder
        x2 = x + cw + 20
        self.card(x2, y, cw, ch, "have", "inst_have")
        self.shadow_text(x2 + 22, y + 26, "I ALREADY HAVE IT", 11, GOLD)
        self.cv.create_text(x2 + 22, y + 50, anchor="nw", fill=TEXT, font=font(9), width=cw - 44, tags="page",
                            text="Pick your game's Data folder on this PC (or the folder with WoW.exe in it). "
                                 "The launcher checks it's the right version and remembers it. Your game files are never changed.")
        cur = self.settings.get("wow_folder")
        if cur and os.path.isdir(cur):
            self.cv.create_text(x2 + 22, y + 128, anchor="nw", text="CURRENT FOLDER", fill=MUTED, font=font(8, "bold"), tags="page")
            self.cv.create_text(x2 + 22, y + 148, anchor="nw", text=cur, fill=TEXT, font=font(9), width=cw - 44, tags="page")
        self.pill_button(x2 + 22, y + ch - 60, cw - 44, 38, "SELECT EXISTING FOLDER", lambda: self.choose_install(c),
                         style="ghost", size=10, icon="folder")
        self.cv.create_text(x + w // 2, y + ch + 30, anchor="n", fill=MUTED, font=font(8), width=w - 40, justify="center", tags="page",
                            text="The game comes from the Internet Archive. Open Vanilla doesn't host Blizzard's game files.")

    # ----- HOST > Dedicated server (launcher/server_host.py: SPP's services, the website and Studio, from here)

    def _dedicated(self):
        """server_host.Dedicated for the SPP install this tab runs, made on first use (None: no install yet)."""
        if not server_host:
            return None
        d = getattr(self, "dedicated", None)
        if d is not None and (d.servers.procs or d.web is not None):
            return d   # keep the one that is running
        cfg = server_host.load_config(self.settings, LAYOUT)
        paths = server_host.resolve_paths(cfg, LAYOUT)
        if paths is None:
            self.dedicated = None
            return None
        if d is None or d.p.server != paths.server or d.cfg != cfg:
            d = self.dedicated = server_host.Dedicated(paths, cfg, LAYOUT, frozen=FROZEN, exe=sys.executable,
                                                       source_root=SOURCE_ROOT)
        return d

    def _host_dedicated(self, x, y, w, h):
        if not server_host:
            self.empty_state(self._scroll_list(x, y, w, h), "The dedicated server isn't in this launcher build",
                             "launcher/server_host.py is missing or couldn't load. Host for friends still works.")
            return
        d = self._dedicated()
        bg = PANEL
        f = self.frame_on(x, y, w, h, bg=bg)
        tk.Label(f, text="DEDICATED SERVER  ·  ADVANCED", bg=bg, fg=GOLD, font=font(11, "bold", True)).pack(anchor="w")
        tk.Label(f, text="An always-on SPP Classics realm (database, login and world servers) with its website and Server "
                         "Studio, run from this launcher: nothing else to download. For a few friends, Host for friends is "
                         "simpler.", bg=bg, fg=MUTED, font=font(8), wraplength=w - 20, justify="left").pack(anchor="w", pady=(2, 8))
        if d is None:
            tk.Label(f, text="It runs on SPP Classics. Set SPP up once with Play Solo (the launcher downloads it), or point "
                             "this launcher at an SPP Classics folder you already have.", bg=bg, fg=TEXT, font=font(9),
                     wraplength=w - 20, justify="left").pack(anchor="w")
            row = tk.Frame(f, bg=bg)
            row.pack(anchor="w", pady=10)
            self.wbutton(row, "Set up SPP with Play Solo", self._dedicated_via_solo, primary=True).pack(side="left")
            self.wbutton(row, "Use my SPP folder…", self._locate_spp_server, icon="folder").pack(side="left", padx=6)
            return
        tk.Label(f, text=f"SPP install: {d.p.server}", bg=bg, fg=MUTED, font=font(8), anchor="w").pack(fill="x")
        status = tk.Frame(f, bg=bg)
        status.pack(fill="x", pady=(6, 4))
        self._ded_dots = {}
        for key, port, label, note in server_host.PORTS:
            r = tk.Frame(status, bg=bg)
            r.pack(fill="x")
            dot = tk.Label(r, text="○", bg=bg, fg=MUTED, font=font(10))
            dot.pack(side="left")
            tk.Label(r, text=f"{label}  ·  TCP {port}", bg=bg, fg=TEXT, font=font(9, "bold")).pack(side="left", padx=6)
            tk.Label(r, text=note, bg=bg, fg=MUTED, font=font(8)).pack(side="left", padx=6)
            self._ded_dots[key] = dot
        btns = tk.Frame(f, bg=bg)
        btns.pack(anchor="w", pady=6)
        busy = getattr(self, "_ded_busy", None)
        if busy:
            tk.Label(btns, text=busy, bg=bg, fg=AMBER, font=font(9, "bold")).pack(side="left")
        else:
            if d.servers.procs:
                self.wbutton(btns, "Stop servers", lambda: self._ded_run(d.stop_all, "Stopping the servers…",
                                                                         "Servers stopped."), danger=True).pack(side="left")
            else:
                self.wbutton(btns, "Start servers", lambda: self._ded_run(d.start_all, "Starting the servers…",
                                                                          "Your realm is up."), primary=True,
                             icon="play").pack(side="left")
            if d.web is not None:
                self.wbutton(btns, "Stop website", lambda: self._ded_run(d.stop_web, "", "Website stopped.")).pack(side="left", padx=6)
            else:
                self.wbutton(btns, "Start website", lambda: self._ded_run(d.start_web, "Starting the website…",
                                                                          "Website starting on this PC.")).pack(side="left", padx=6)
        web = f"http://127.0.0.1:{server_host.WEB_PORT}/"
        self.wbutton(btns, "Server Studio", lambda: safe_open(web + "studio/")).pack(side="left", padx=(0, 6))
        self.wbutton(btns, "Add this PC to my realms", lambda: self.add_realm(
            {"name": "My server (this PC)", "host": "127.0.0.1", "port": 3724, "portal": web.rstrip("/"), "build": 5875},
            select=True)).pack(side="left", padx=(0, 6))
        self.wbutton(btns, "Copy my address", lambda: self._copy(local_ip(), "Local address copied")).pack(side="left")
        line = tk.Frame(f, bg=bg)
        line.pack(fill="x", pady=(6, 2))
        tk.Label(line, text="Address players use", bg=bg, fg=MUTED, font=font(8)).pack(side="left")
        addr = self.entry(line, width=24)
        addr.insert(0, d.cfg.get("realm_address") or "127.0.0.1")
        addr.pack(side="left", padx=8, ipady=2)
        self.wbutton(line, "Save", lambda: self._ded_address(addr.get())).pack(side="left")
        tk.Label(line, text="127.0.0.1 = this PC only. Players on the internet need your public address and TCP 3724 "
                            "and 8085 forwarded to this PC.", bg=bg, fg=MUTED, font=font(8)).pack(side="left", padx=8)
        gm = tk.Frame(f, bg=bg)
        gm.pack(fill="x", pady=(6, 2))
        tk.Label(gm, text="GM console", bg=bg, fg=MUTED, font=font(8)).pack(side="left")
        cmd = self.entry(gm, width=40)
        cmd.pack(side="left", padx=8, ipady=2, fill="x", expand=True)
        send = lambda: self._ded_gm(cmd)  # noqa: E731
        cmd.bind("<Return>", lambda e: send())
        self.wbutton(gm, "Send", send).pack(side="left")
        log = tk.Text(f, height=8, bg="#0d0a11", fg=MUTED, font=("Consolas", 9), relief="flat", highlightthickness=1,
                      highlightbackground="#3a2f22", wrap="none")
        log.pack(fill="both", expand=True, pady=(6, 0))
        log.insert("end", "World server log appears here once it runs.")
        log.config(state="disabled")
        self._ded_log = log
        self._ded_poll()

    def _ded_run(self, fn, busy_text, ok_text):
        self._ded_busy = busy_text or None

        def then(err):
            self._ded_busy = None
            if self.page == "host":
                self.show_page("host", animate=False)

        self._host_thread(fn, ok_text, "The dedicated server reported a problem", then)
        if self.page == "host":
            self.show_page("host", animate=False)

    def _ded_address(self, text):
        text = text.strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}", text):
            self.notice("That isn't an address (use an IP like 203.0.113.7 or a name like realm.example.org).", RED, 6)
            return
        cfg = server_host.load_config(self.settings, LAYOUT)
        cfg["realm_address"] = text
        try:
            server_host.save_config(LAYOUT, cfg)
        except OSError as e:
            self.notice(f"Couldn't save: {e}"[:110], RED, 6)
            return
        self.notice("Saved. It applies the next time the servers start.", GREEN, 5)
        self.show_page("host", animate=False)

    def _ded_gm(self, entry):
        d = getattr(self, "dedicated", None)
        command = entry.get().strip()
        if not d or not command:
            return
        try:
            reply = d.gm(command)
        except Exception as e:  # SppError, SOAP errors: show them as they are
            self.notice(f"GM: {e}"[:110], RED, 8)
            return
        entry.delete(0, "end")
        self.notice(f"GM: {reply}"[:110], GREEN, 5)

    def _ded_poll(self, gen=None):
        """Ports and the world log every 3 seconds while this tab is on screen (one loop per page view)."""
        if gen is None:
            self._ded_gen = getattr(self, "_ded_gen", 0) + 1
            gen = self._ded_gen
        elif gen != self._ded_gen or self.page != "host" or self.tab_state.get("host") != "server":
            return
        d = getattr(self, "dedicated", None)
        if d is None:
            return

        def work():
            try:
                st, tail = d.status(), d.log_tail("mangosd", 30)
            except Exception:
                st, tail = {}, []
            try:
                self.after(0, show, st, tail)
            except RuntimeError:
                pass

        def show(st, tail):
            if gen != self._ded_gen or self.page != "host":
                return
            try:
                for key, dot in self._ded_dots.items():
                    dot.config(text="●" if st.get(key) else "○", fg=GREEN if st.get(key) else MUTED)
                if tail:
                    self._ded_log.config(state="normal")
                    self._ded_log.delete("1.0", "end")
                    self._ded_log.insert("end", "\n".join(tail))
                    self._ded_log.see("end")
                    self._ded_log.config(state="disabled")
            except tk.TclError:
                return
            self.after(3000, self._ded_poll, gen)

        threading.Thread(target=work, daemon=True).start()

    def _dedicated_via_solo(self):
        if "solo" in [k for k, _ in self.play_modes()]:
            self.set_play_mode("solo")
        self.show_page("solo")

    def _locate_spp_server(self):
        path = filedialog.askdirectory(parent=self, title="Choose your SPP Classics folder (SPP_Classics_V2 or its SPP_Server)")
        if not path:
            return
        server = next((c for c in (path, os.path.join(path, spp.SERVER_FOLDER)) if spp.is_spp_server(c)), None)
        if not server:
            messagebox.showerror("That isn't SPP Classics", "There's no Launcher.bat and Server folder there. Pick the "
                                 "SPP_Classics_V2 folder (or the SPP_Server folder inside it).", parent=self)
            return
        cfg = server_host.load_config(self.settings, LAYOUT)
        cfg["spp_root"] = server
        try:
            server_host.save_config(LAYOUT, cfg)
        except OSError as e:
            self.notice(f"Couldn't save: {e}"[:110], RED, 6)
            return
        self.settings["spp_root"] = server
        self.save_settings()
        self.dedicated = None
        self.show_page("host", animate=False)

    def _copy(self, text, msg):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.notice(msg)

    # ----- Realms

    def page_servers(self):
        tab = self.tab_state.get("servers", "realms")
        x, y, w, h = self.big_panel("REALMS", "realms", "" if tab == "realms" else
                                    "Pick where PLAY connects · ping is a TCP connect to the login port")
        self.segmented(x, y - 4, (("realms", "REALM BROWSER"), ("mine", "MY SERVERS"), ("community", "COMMUNITY LIST")), tab,
                       lambda k: self._set_tab("servers", k), w=180)
        if tab == "realms":
            self._servers_realms(x, y + 38, w, h - 38)
        elif tab == "community":
            self._servers_community(x, y + 38, w, h - 38)
        else:
            self._servers_mine(x, y + 38, w, h - 38)

    def _servers_mine(self, x, y, w, h):
        self.pill_button(x + w, y - 42, 150, 32, "REFRESH", self.refresh_realms, anchor="ne", size=8, icon="refresh")
        inner = self._scroll_list(x, y, w, h - 104)
        for i, r in enumerate(self.realms):
            st = self.realm_state.get(i, {})
            sel = i == self.realm_index
            bg = "#211a12" if sel else "#17121c"
            row = self.list_row(inner, bg, GOLD_DIM if sel else "#3a2f22")
            color = {"online": GREEN, "partial": AMBER, "offline": RED}.get(st.get("status"), MUTED)
            tk.Label(row, text="●", bg=bg, fg=color, font=font(12)).pack(side="left", padx=(12, 8), pady=10)
            box = tk.Frame(row, bg=bg)
            box.pack(side="left", fill="x", expand=True)
            head = tk.Frame(box, bg=bg)
            head.pack(fill="x")
            tk.Label(head, text=r.get("name", r.get("host")), bg=bg, fg=GOLD if sel else TEXT, font=font(10, "bold")).pack(side="left")
            self.chip(head, BUILD_NAMES.get(int(r.get("build", 5875)), str(r.get("build")))).pack(side="left", padx=8)
            ping = f"{st['ping']} ms" if st.get("ping") is not None else "—"
            tk.Label(box, text=f"{r.get('host')}:{r.get('port', 3724)}    ping {ping}    {st.get('detail', '')}",
                     bg=bg, fg=MUTED, font=font(8), anchor="w").pack(fill="x")
            if r in self.settings.get("custom_realms", []):
                self.wbutton(row, "Remove", lambda r=r: self.remove_realm(r), danger=True).pack(side="right", padx=(0, 12))
            if r.get("portal"):
                self.wbutton(row, "Website", lambda u=r["portal"]: safe_open(u)).pack(side="right", padx=(0, 8))
            if sel:
                tk.Label(row, text="SELECTED", bg=bg, fg=GOLD, font=font(8, "bold")).pack(side="right", padx=12)
            else:
                self.wbutton(row, "Select", lambda i=i: self.select_realm(i), primary=True).pack(side="right", padx=12)

        add = self.frame_on(x, y + h - 96, w, 92, bg=PANEL)
        tk.Label(add, text="ADD A SERVER", bg=PANEL, fg=GOLD, font=font(10, "bold", True)).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 6))
        fields = []
        for col, (label, width) in enumerate((("Name", 18), ("Host or IP", 20), ("Port", 6), ("Website URL (optional)", 26))):
            tk.Label(add, text=label, bg=PANEL, fg=MUTED, font=font(8)).grid(row=1, column=col, sticky="w", padx=(0, 8))
            e = self.entry(add, width=width)
            e.grid(row=2, column=col, sticky="w", padx=(0, 8), ipady=3)
            fields.append(e)
        fields[2].insert(0, "3724")
        tk.Label(add, text="Client", bg=PANEL, fg=MUTED, font=font(8)).grid(row=1, column=4, sticky="w", padx=(0, 8))
        bvar = tk.StringVar(value="1.12.1")
        opt = tk.OptionMenu(add, bvar, *sorted(set(BUILD_NAMES.values()) - {"1.12.2"}))
        opt.config(bg=FIELD, fg=TEXT, activebackground="#33291d", activeforeground=GOLD, highlightthickness=0, bd=0,
                   relief="flat", font=font(9), cursor=self.CUR_HAND)
        opt["menu"].config(bg="#1a1510", fg=TEXT, activebackground="#4a3a22", activeforeground=GOLD)
        opt.grid(row=2, column=4, sticky="w", padx=(0, 8))

        def do_add():
            name, host, port, portal = (e.get().strip() for e in fields)
            port = port or "3724"
            if not host or not port.isdigit():
                messagebox.showerror("Servers", "Enter a host and a numeric port.", parent=self)
                return
            build = {v: k for k, v in BUILD_NAMES.items()}.get(bvar.get(), 5875)
            self.add_realm({"name": name or host, "host": host, "port": int(port), "portal": portal or None, "build": build})

        self.wbutton(add, "Add server", do_add, primary=True).grid(row=2, column=5, sticky="w", padx=6)

    def add_realm(self, r, select=False):
        r = {k: v for k, v in r.items() if v not in (None, "")}
        if not valid_host(r.get("host")):
            self.notice("That isn't a valid server address.", RED, 5)
            return
        if r.get("portal") and not safe_url(r["portal"]):
            r.pop("portal")  # only https websites (or this PC)
        for i, existing in enumerate(self.realms):
            if existing.get("host") == r.get("host") and int(existing.get("port", 3724)) == int(r.get("port", 3724)):
                if select:
                    self.select_realm(i)
                else:
                    self.notice(f"{existing.get('name')} is already in your list")
                return
        self.settings.setdefault("custom_realms", []).append(r)
        self.realms.append(r)
        self.save_settings()
        self._build_rail()
        self.refresh_realms()
        self.notice(f"Added {r.get('name')}", GREEN)
        if select:
            self.select_realm(len(self.realms) - 1)
        else:
            self.show_page(self.page, animate=False)

    def _servers_community(self, x, y, w, h):
        self.ping_directory()
        servers = self.directory.get("servers", [])
        live = self.directory.get("_live")
        sub = "Live list from the Open Vanilla directory" if live else "Offline copy (the directory couldn't be reached)"
        self.cv.create_text(x + w, y - 26, anchor="e", text=sub, fill=MUTED, font=font(8), tags="page")
        inner = self._scroll_list(x, y, w, h - 40)
        if not servers:
            self.empty_state(inner, "No community servers listed yet",
                             "Run your own with Open Vanilla Server (openvanilla.app/host.html), then list it so other players can find it.")
        for srv in servers:
            key = f"{srv.get('host')}:{srv.get('port', 3724)}"
            ping = self.dir_state.get(key, "?")
            row = self.list_row(inner)
            col = MUTED if ping == "?" else (GREEN if ping is not None else RED)
            tk.Label(row, text="●", bg="#17121c", fg=col, font=font(12)).pack(side="left", padx=(12, 8), pady=10)
            box = tk.Frame(row, bg="#17121c")
            box.pack(side="left", fill="x", expand=True, pady=6)
            head = tk.Frame(box, bg="#17121c")
            head.pack(fill="x")
            tk.Label(head, text=srv.get("name", srv.get("host")), bg="#17121c", fg=TEXT, font=font(10, "bold")).pack(side="left")
            self.chip(head, BUILD_NAMES.get(int(srv.get("build", 5875)), "?")).pack(side="left", padx=(8, 4))
            for tag in srv.get("tags", [])[:4]:
                self.chip(head, tag, bg="#1f1a2c", fg="#b9a6ff").pack(side="left", padx=2)
            pt = "checking…" if ping == "?" else (f"{ping} ms" if ping is not None else "offline")
            tk.Label(box, text=srv.get("description", ""), bg="#17121c", fg=TEXT, font=font(8), anchor="w",
                     wraplength=w - 330, justify="left").pack(fill="x")
            tk.Label(box, text=f"{key}    {pt}", bg="#17121c", fg=MUTED, font=font(8), anchor="w").pack(fill="x")
            entry = {k: srv.get(k) for k in ("name", "host", "port", "portal", "build")}
            self.wbutton(row, "Play here", lambda e=entry: (self.add_realm(e, select=True), self.show_page("play")),
                         primary=True).pack(side="right", padx=12)
            self.wbutton(row, "Add", lambda e=entry: self.add_realm(e)).pack(side="right")
            if srv.get("portal"):
                self.wbutton(row, "Website", lambda u=srv["portal"]: safe_open(u)).pack(side="right", padx=8)
        submit = self.defaults.get("directory_submit_url") or self.community_links().get("portal")
        if submit:
            self.link_text(x, y + h - 14, "Run a server? List it in the community directory ›", lambda: safe_open(submit), 9)
        self.link_text(x + w, y + h - 14, "Reload list", self.load_directory, 9, anchor="e")

    def remove_realm(self, r):
        self.settings["custom_realms"] = [x for x in self.settings.get("custom_realms", []) if x != r]
        self.realms = [x for x in self.realms if x is not r]
        self.realm_index = 0
        self.realm_state = {}
        self.save_settings()
        self._build_rail()
        self._fill_realm_label()
        self.refresh_realms()
        self.show_page("servers", animate=False)

    def select_realm(self, i):
        if i == self.realm_index and self.page != "servers":
            return
        self.realm_index = i
        self.save_settings()
        self._fill_realm_label()
        self._paint_rail()
        self._paint_pill()
        self.update_status()
        self.show_page(self.page, animate=False)

    # ----- Realms (the live directory of official and community realms; launcher/p2p)

    def _optmenu(self, parent, var, labels, command=None, width=None):
        opt = tk.OptionMenu(parent, var, *labels, command=(lambda _v: command()) if command else None)
        opt.config(bg=FIELD, fg=TEXT, activebackground="#33291d", activeforeground=GOLD, highlightthickness=0, bd=0,
                   relief="flat", font=font(9), cursor=self.CUR_HAND)
        if width:
            opt.config(width=width)
        opt["menu"].config(bg="#1a1510", fg=TEXT, activebackground="#4a3a22", activeforeground=GOLD)
        return opt

    def _p2p_url(self):
        return self.settings.get("p2p_directory_url") or self.defaults.get("p2p_directory_url") or P2P_DIRECTORY_URL

    def _p2p_portal(self):
        return (self.defaults.get("p2p_portal") or P2P_PORTAL).rstrip("/")

    def _launcher_token(self):
        tok = self.session.get("token")
        if not tok and self.settings.get("launcher_token"):
            tok = account.unprotect(self.settings["launcher_token"])
        return tok

    def p2p_refresh(self):
        """Fetch the live directory in the background, then ping every realm (a realmd challenge round trip)."""
        st = self.p2p
        if st["loading"]:
            return
        d = p2p_module("directory")
        if not d:
            st["error"] = "The realm browser isn't installed with this launcher (" + p2p_error("directory") + ")."
            return
        st["loading"] = True
        url = self._p2p_url()

        def work():
            try:
                realms, err = list(d.fetch(url)), ""
            except Exception as e:
                realms, err = None, (OFFLINE_TEXT if is_offline_error(str(e)) or isinstance(e, OSError)
                                     else f"Couldn't load the realm list ({e}).")
            try:
                self.after(0, self._p2p_loaded, realms, err)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _p2p_loaded(self, realms, err):
        st = self.p2p
        st.update(loading=False, error=err)
        if realms is not None:
            st["realms"] = realms
            st["fetched"] = time.time()
            gate = threading.Semaphore(6)
            d = p2p_module("directory")

            def ping(r):
                with gate:
                    try:
                        ms = d.ping(r)
                    except Exception:
                        ms = None
                try:
                    self.after(0, self._p2p_pinged, realm_key(r), ms)
                except RuntimeError:
                    pass

            for r in realms:
                threading.Thread(target=ping, args=(r,), daemon=True).start()
        self._p2p_repaint()

    def _p2p_pinged(self, key, ms):
        self.p2p["pings"][key] = ms
        self._p2p_repaint()

    def _p2p_repaint(self):
        """Redraw the Realms list once for a burst of results (pings come back one by one)."""
        if self.page != "servers" or self.tab_state.get("servers") != "realms" or self._p2p_paint_after:
            return

        def go():
            self._p2p_paint_after = None
            if self.page == "servers" and self.tab_state.get("servers") == "realms":
                self.show_page("servers", animate=False)

        self._p2p_paint_after = self.after(250, go)

    def _p2p_filter(self, key, value):
        self.p2p["filters"][key] = value
        self.settings["p2p_filters"] = dict(self.p2p["filters"])
        self.save_settings()
        self.show_page("servers", animate=False)

    def _servers_realms(self, x, y, w, h):
        st = self.p2p
        if not p2p_module("directory"):
            # No realm browser in this build: the curated community list still works.
            self.cv.create_text(x, y - 26 + 4, anchor="w", fill=AMBER, font=font(8), tags="page",
                                text="Live realm browser unavailable · showing the community list")
            self._servers_community(x, y, w, h)
            return
        if st["realms"] is None and not st["loading"] and not st["error"]:
            self.p2p_refresh()
        f = st["filters"]
        bar = self.frame_on(x, y, w - 160, 34, bg=PANEL)
        types = [("all", "All types")] + list(REALM_TYPES)
        temps = [("all", "All templates")] + list(REALM_TEMPLATES)
        shows = [("all", "All realms"), ("fav", "Favourites"), ("recent", "Recent")]
        for label, key, opts in (("Type", "type", types), ("Template", "template", temps), ("Show", "show", shows)):
            tk.Label(bar, text=label, bg=PANEL, fg=MUTED, font=font(8)).pack(side="left", padx=(0, 6))
            names = dict(opts)
            var = tk.StringVar(value=names.get(f.get(key, "all"), opts[0][1]))
            back = {v: k for k, v in opts}
            self._optmenu(bar, var, [n for _, n in opts],
                          command=lambda var=var, back=back, key=key: self._p2p_filter(key, back[var.get()]),
                          width=12).pack(side="left", padx=(0, 14))
        room = tk.BooleanVar(value=bool(f.get("room")))
        self.check(bar, "Has room", room, lambda: self._p2p_filter("room", room.get())).pack(side="left")
        self.pill_button(x + w, y + 1, 150, 32, "REFRESH", lambda: (self.p2p.update(realms=None), self.p2p_refresh(),
                                                                     self.show_page("servers", animate=False)),
                         anchor="ne", size=8, icon="refresh")
        when = ("Loading the realm list…" if st["loading"] else OFFLINE_TEXT if st["error"] == OFFLINE_TEXT
                else "Offline" if st["error"] else
                (f"{len(st['realms'] or [])} realms · live from the Open Vanilla directory" if st["realms"] is not None else ""))
        self.cv.create_text(x + w, y - 26, anchor="e", text=when, fill=AMBER if st["error"] == OFFLINE_TEXT else
                            RED if st["error"] else MUTED, font=font(8), tags="page")

        inner = self._scroll_list(x, y + 40, w, h - 40 - 48)
        self.p2p_rows = {}
        realms = st["realms"] or []
        favs = set(self.settings.get("p2p_favourites", []))
        recent = [e["key"] for e in self.settings.get("p2p_recent", [])]
        only = favs if f.get("show") == "fav" else (set(recent) if f.get("show") == "recent" else None)
        rows = filter_realms(realms, f.get("type", "all"), f.get("template", "all"), bool(f.get("room")), only)
        if f.get("show") == "recent":
            rows.sort(key=lambda r: recent.index(realm_key(r)))
        if not rows:
            if st["error"] == OFFLINE_TEXT and not realms:
                self.empty_state(inner, "Open Vanilla is offline", "You can still host and join friends directly: paste a "
                                 "friend's invite link below, or use JOIN BY ADDRESS. Press REFRESH to try again.")
            elif st["error"] and not realms:
                self.empty_state(inner, "Couldn't load the realm list", st["error"] + "\n\nPress REFRESH to try again, "
                                 "or use the COMMUNITY LIST tab.")
            elif st["loading"] or st["realms"] is None:
                self.empty_state(inner, "Loading realms…", "Asking the Open Vanilla directory which realms are up.")
            elif realms:
                self.empty_state(inner, "No realm matches these filters", "Change the filters above to see more realms.")
            else:
                self.empty_state(inner, "No realms are listed right now",
                                 "Paste an invite link a friend sent you below, or run your own with Open Vanilla Server (openvanilla.app/host.html).")
        heads = {0: "VERIFIED REALMS  ·  OFFICIAL", 1: "VERIFIED REALMS  ·  VETTED BY THE MAINTAINER",
                 2: "COMMUNITY P2P REALMS  ·  NOT VETTED, PLAY AT YOUR OWN RISK"}
        group = None
        for r in rows:
            g = realm_group(r)
            if g != group and f.get("show") != "recent":
                group = g
                tk.Label(inner, text=heads[g], bg=PANEL, fg=GOLD if g < 2 else MUTED,
                         font=font(9, "bold", True)).pack(anchor="w", pady=(8, 2), padx=2)
            self._realm_row(inner, r, w, favs)

        bot = self.frame_on(x, y + h - 40, w, 38, bg=PANEL)
        tk.Label(bot, text="INVITE LINK", bg=PANEL, fg=GOLD, font=font(9, "bold", True)).pack(side="left", padx=(0, 10))
        e = self.entry(bot, width=46)
        e.pack(side="left", fill="x", expand=True, ipady=4)
        e.insert(0, st.get("invite_text", ""))
        e.bind("<KeyRelease>", lambda ev: st.update(invite_text=e.get()))
        e.bind("<Return>", lambda ev: self.open_invite(e.get()))
        self.p2p_invite_entry = e
        self.wbutton(bot, "Join invite", lambda: self.open_invite(e.get()), primary=True, icon="link").pack(side="left", padx=(8, 0))
        self.wbutton(bot, "Join by address", self.join_address_dialog, size=8).pack(side="left", padx=(6, 0))

    def _realm_row(self, inner, r, w, favs):
        key = realm_key(r)
        grey = realm_group(r) == 2
        bg = "#121016" if grey else "#17121c"
        fg, sub = (MUTED, "#7d7466") if grey else (TEXT, MUTED)
        row = self.list_row(inner, bg, "#2a241c" if grey else "#3a2f22")
        self.p2p_rows[key] = row
        fav = key in favs
        star = tk.Label(row, image=self._tk_icon("star_on" if fav else "star", 18, GOLD if fav else "#6b5a3c"), bg=bg,
                        cursor=self.CUR_HAND)
        star.pack(side="left", padx=(10, 4), pady=10)
        star.bind("<Button-1>", lambda e: self.toggle_favourite(key))
        rtype = rf(r, "type", "pve")
        tk.Label(row, image=self._tk_icon(REALM_TYPE_ICONS.get(rtype, "realms"), 22, "#6b5a3c" if grey else GOLD_DIM),
                 bg=bg).pack(side="left", padx=(4, 10))
        box = tk.Frame(row, bg=bg)
        box.pack(side="left", fill="x", expand=True, pady=6)
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=rf(r, "name", rf(r, "host", "?")), bg=bg, fg=fg, font=font(10, "bold")).pack(side="left")
        if rf(r, "official", False):
            self._badge(head, "OFFICIAL", "crown", "#3a2a0e", GOLD, bg)
        elif rf(r, "verified", False):
            self._badge(head, "VERIFIED", "shield", "#123022", GREEN, bg)
        else:
            self._badge(head, "COMMUNITY", "realms", "#1c1a22", "#9aa0a6", bg)
        if rf(r, "e2e", False):
            self._badge(head, "ENCRYPTED", "shield", "#10282a", "#4fc3b0", bg)
        tname = dict(REALM_TYPES).get(rtype, rtype)
        tmpl = dict(REALM_TEMPLATES).get(rf(r, "template", ""), "")
        for tag in [tname, tmpl] + [t for t in rf(r, "tags", [])[:3] if t not in (tname, tmpl, "community", "official", "PvE", "PvP", "RPPvE", "RPPvP", "Classic+")]:
            if tag:
                self.chip(head, str(tag), bg="#1a1620" if grey else "#2a2014", fg="#8a8070" if grey else TAN).pack(side="left", padx=2)
        ping = self.p2p["pings"].get(key, rf(r, "ping"))
        pt = ("checking…" if key not in self.p2p["pings"] and ping is None else
              (f"{ping} ms" if ping is not None else "no answer"))
        pop = int(rf(r, "population", 0) or 0)
        cap = rf(r, "max_players")
        players = f"{pop}/{cap} players" if cap else f"{pop} online"
        via = ("  ·  via relay (a verified community node)" if rf(r, "relay", False) and rf(r, "relay_url", "")
               and "relay.openvanilla.app" not in rf(r, "relay_url", "") else "  ·  via relay" if rf(r, "relay", False) else "")
        line = f"{players}    ping {pt}{via}"
        if rf(r, "description"):
            tk.Label(box, text=rf(r, "description"), bg=bg, fg=fg, font=font(8), anchor="w",
                     wraplength=w - 420, justify="left").pack(fill="x")
        tk.Label(box, text=line, bg=bg, fg=sub, font=font(8), anchor="w").pack(fill="x")
        self.wbutton(row, "Join", lambda r=r: self.join_realm(r, rf(r, "name", "")), primary=not grey,
                     icon="play").pack(side="right", padx=12)
        if not rf(r, "official", False):
            self.wbutton(row, "Report", lambda r=r: self.report_realm(r), icon="flag", size=8).pack(side="right")

    def _badge(self, parent, text, icon, bg, fg, row_bg):
        b = tk.Label(parent, text=" " + text, image=self._tk_icon(icon, 12, fg), compound="left", bg=bg, fg=fg,
                     font=font(7, "bold"), padx=5, pady=1, highlightthickness=1, highlightbackground="#6b5426")
        b.pack(side="left", padx=(8, 0))
        return b

    def toggle_favourite(self, key):
        favs = list(self.settings.get("p2p_favourites", []))
        if key in favs:
            favs.remove(key)
        else:
            favs.append(key)
        self.settings["p2p_favourites"] = favs
        self.save_settings()
        self.show_page("servers", animate=False)

    def _remember_recent(self, key, name):
        rec = [e for e in self.settings.get("p2p_recent", []) if e.get("key") != key]
        rec.insert(0, {"key": key, "name": name, "at": int(time.time())})
        self.settings["p2p_recent"] = rec[:12]
        self.save_settings()

    def open_invite(self, text):
        """An invite link pasted in the box, or passed on the command line (openvanilla://join/…)."""
        inv = parse_link(text)
        if not inv:
            hp = (text or "").strip()
            if re.fullmatch(r"[A-Za-z0-9.\-]{1,253}(:\d{1,5})?", hp) and "." in hp:  # a plain host:port
                return self.join_address(hp)
            self.notice("That isn't an Open Vanilla invite link or a host:port address.", RED, 6)
            return False
        name = inv["name"] or "a community realm"
        if inv["kind"] == "relay":
            body = ("This invite opens a community realm hosted by another player, through Open Vanilla's relay. "
                    + ("You join as a guest; no Open Vanilla account needed." if inv.get("guest") else
                       "You sign in with your Open Vanilla account; the host never sees your password."))
            if not messagebox.askyesno("Join a realm", f"Join {name}?\n\n{body}", parent=self):
                return False
        elif not self._confirm_direct(inv["kind"], name, f"{inv['host']}:{inv['port']}"):
            return False
        self.join_realm(inv["link"], inv["name"], key=inv["host_id"] or f"{inv['host']}:{inv['port']}")
        return True

    def _confirm_direct(self, kind, name, address):
        """Joining a host directly (not through the relay): the host sees the player's IP address."""
        if kind == "lan":
            body = (f"Join {name} on your local network ({address})?\n\nThis realm runs on a PC in your home or "
                    "LAN; Open Vanilla isn't involved.")
        else:
            body = (f"Join {name} directly at {address}?\n\nYou connect straight to the host's PC, not through "
                    "Open Vanilla, so the host will see your IP address (and roughly where you are). Only join hosts "
                    "you trust.")
        return messagebox.askyesno("Join directly", body, parent=self)

    def join_address(self, address=None, guest=None, user=None, password=None):
        """Join by address: host:port, with a guest code or an account the host made for you (or neither:
        type your account in the game)."""
        address = (address or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}(:\d{1,5})?", address):
            self.notice("Enter the host's address as host:port (for example 192.168.1.20:3724).", RED, 6)
            return False
        if not self._confirm_direct("lan" if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.)", address)
                                    else "direct", address, address):
            return False
        extra = {k: v for k, v in (("guest", (guest or "").strip().upper() or None),
                                   ("username", (user or "").strip() or None),
                                   ("password", password or None)) if v}
        self.join_realm(address, address, key=address if ":" in address else address + ":3724", extra=extra)
        return True

    def join_address_dialog(self):
        dlg = self.p2p_dialog("JOIN BY ADDRESS", "Play on a friend's realm without Open Vanilla: enter the address they "
                              "gave you. Add their guest code, or the account they made for you, if they sent one.",
                              width=500)
        fields = {}
        for key, label, show in (("address", "Address (host:port)", None), ("guest", "Guest code (optional)", None),
                                 ("user", "Account (optional)", None), ("password", "Password (optional)", "•")):
            tk.Label(dlg.body, text=label, bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w", pady=(4, 0))
            e = self.entry(dlg.body, show=show, width=40)
            e.pack(fill="x", ipady=3)
            fields[key] = e
        dlg.fields = fields

        def go():
            vals = {k: e.get() for k, e in fields.items()}
            dlg.close()
            self.join_address(vals["address"], vals["guest"], vals["user"], vals["password"])

        dlg.buttons(("Join", go, True), ("Cancel", dlg.close, False))
        return dlg

    def join_realm(self, target, name="", key=None, extra=None):
        j = p2p_module("join")
        if not j:
            messagebox.showerror("Join", "Joining community realms isn't available in this launcher build.\n\n"
                                 + p2p_error("join"), parent=self)
            return
        if self.p2p.get("joining"):
            self.notice("Already joining a realm…", AMBER)
            return
        key = key or (realm_key(target) if not isinstance(target, str) else (parse_invite(target) or {}).get("host_id", target))
        self.p2p["joining"] = True
        self.notice(f"Joining {name or 'the realm'}…", GOLD, 6)
        launcher = _GameLauncher(self)

        kw = dict(extra or {})
        kw.setdefault("node_network", self.nodes_on())   # realms on volunteer nodes: sealed streams
        try:  # pass only what this p2p.join takes (launcher_token, guest, username, password)
            import inspect
            params = inspect.signature(j.join).parameters
            if "launcher_token" in params:
                kw["launcher_token"] = launcher.token
            if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
                kw = {k: v for k, v in kw.items() if k in params}
        except (TypeError, ValueError):
            pass

        def work():
            try:
                sess, err = j.join(target, launcher, **kw), None
            except Exception as e:
                sess, err = None, str(e) or type(e).__name__
            try:
                self.after(0, self._joined, key, name, sess, err)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _joined(self, key, name, sess, err):
        self.p2p["joining"] = False
        if err and is_host_key_error(err):
            messagebox.showerror("Host key changed", f"Not connecting to {name or 'this realm'}.\n\n{err}\n\n"
                                 "Each host has a key that proves it is the same PC you played on before (or the one "
                                 "in your invite). This one doesn't match. If your friend reinstalled or moved their "
                                 "realm, ask them for a new invite link. If not, someone may be pretending to be them: "
                                 "don't sign in there.", parent=self)
            return
        if err and is_offline_error(err):
            messagebox.showerror("Join", f"Couldn't join {name or 'the realm'}: {OFFLINE_TEXT}\n\nAsk the host for a "
                                 "direct invite link or their address (Realms → Join by address).\n\n({err})",
                                 parent=self)
            return
        if err:
            messagebox.showerror("Join", f"Couldn't join {name or 'the realm'}.\n\n{err}", parent=self)
            return
        old = self.p2p.get("join_session")
        if old is not None and old is not sess and hasattr(old, "stop"):
            try:
                old.stop()
            except Exception:
                pass
        self.p2p["join_session"] = sess
        self._remember_recent(key, name)
        creds = getattr(sess, "creds", None) or {}
        fp = getattr(sess, "fingerprint", None)
        self.notice(f"Joined {name or 'the realm'} — starting the game"
                    + (f"  ·  account {creds['user']}" if creds.get("user") else "")
                    + (f"  ·  host key {fp}" if fp else ""), GREEN, 8)

    def launch_at(self, host, port=3724, user=None, password=None, name=None, extra_env=None):
        """Start the picked desktop client against host:port (a community realm, or the local bridge).
        -> the client's process, or None when it couldn't start."""
        c = self.client()
        exe = self.client_exe(c)
        if c["type"] == "web" or not exe:
            self.notice("Pick an installed desktop client (bottom left) to play community realms.", AMBER, 6)
            return None
        port = int(port or 3724)
        target = host if port == 3724 else f"{host}:{port}"
        if c["type"] == "exe":
            folder = os.path.dirname(exe)
            rl = os.path.join(folder, *c.get("realmlist", "realmlist.wtf").split("/"))
            try:
                if os.path.isfile(rl) and not os.path.isfile(rl + ".openvanilla-backup"):
                    shutil.copy2(rl, rl + ".openvanilla-backup")
                with open(rl, "w", encoding="ascii", newline="\r\n") as f:
                    f.write(f"set realmlist {target}\n")
                proc = subprocess.Popen(exe_command(exe), cwd=folder)
            except OSError as e:
                messagebox.showerror("Can't start", str(e), parent=self)
                return None
            if password:
                self.clipboard_clear()
                self.clipboard_append(password)
                self.notice(f"Account {user}: password copied — paste it with Ctrl+V on the login screen", GREEN, 10)
            return proc
        env = os.environ.copy()
        env["WOW_DATA"] = wow_data_dir(self.settings.get("wow_folder", ""))
        env["WOW_HOST"] = target
        for k, v in (("WOW_USER", user), ("WOW_PASS", password)):
            env.pop(k, None)
            if v:
                env[k] = v
        if extra_env:
            env.update({k: v for k, v in extra_env.items() if k.startswith("WOW_")})
        try:
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env)
        except OSError as e:
            messagebox.showerror("Can't start", str(e), parent=self)
            return None
        if self.p2p_host is None:
            self._started()  # may close the launcher (close_on_play)
        else:
            self.notice(f"Starting {self.client()['name']}…", GREEN)
        return proc

    def report_realm(self, r):
        token = self._launcher_token()
        if not token:
            self.notice("Sign in (top right) to report a realm.", AMBER, 6)
            return
        reasons = ("Offensive name or description", "Cheating, scams or abuse", "Not what it claims to be",
                   "Shares game files it shouldn't", "Something else")
        dlg = self.p2p_dialog("REPORT A REALM", f"Tell Open Vanilla's staff what's wrong with {rf(r, 'name', 'this realm')}. "
                              "Reports are reviewed by people; the host isn't told who reported.", width=480)
        body = dlg.body
        var = tk.StringVar(value=reasons[0])
        for text in reasons:
            tk.Radiobutton(body, text=text, variable=var, value=text, bg=PANEL, fg=TEXT, selectcolor=FIELD,
                           activebackground=PANEL, activeforeground=GOLD, font=font(9), anchor="w",
                           highlightthickness=0, bd=0).pack(fill="x")
        tk.Label(body, text="Details (optional)", bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w", pady=(8, 2))
        e = self.entry(body, width=50)
        e.pack(fill="x", ipady=3)

        def send():
            reason = var.get() + (": " + e.get().strip() if e.get().strip() else "")
            dlg.close()
            payload = {"host_id": rf(r, "host_id") or realm_key(r), "reason": reason[:300]}
            url = self._p2p_portal() + "/api/directory/report"
            d = p2p_module("directory")

            def work():
                if d is not None and hasattr(d, "report"):
                    try:
                        status, info = (202 if d.report(payload["host_id"], payload["reason"], token) else 400), {}
                    except Exception as e:
                        status, info = 0, {"message": OFFLINE_TEXT if is_offline_error(str(e)) else
                                           f"The report couldn't be sent ({e})."}
                else:
                    status, info = account._request(url, "POST", payload, token=token, timeout=10)
                try:
                    self.after(0, lambda: self.notice(
                        "Thanks — the report was sent to Open Vanilla's staff." if status in (200, 201, 202, 204) else
                        (info.get("message") or f"The report couldn't be sent (HTTP {status})."),
                        GREEN if status in (200, 201, 202, 204) else RED, 6))
                except RuntimeError:
                    pass

            threading.Thread(target=work, daemon=True).start()

        dlg.buttons(("Send report", send, True), ("Cancel", dlg.close, False))
        return dlg

    def p2p_dialog(self, title, text, width=520):
        """A small window in the launcher's style (dark panel, gold Cinzel title). Non-blocking."""
        return _P2PDialog(self, title, text, width)

    # ----- Host a realm (launcher/p2p/host.py: the Solo server, listed or invite-only)

    def host_tabs(self):
        """HOST's sub-tabs: Host for friends first; Dedicated server (Advanced); Downloads only with Advanced on.
        live.json flags can hide the first two."""
        tabs = []
        if self.live.flag("host_friends"):
            tabs.append(("realm", "HOST FOR FRIENDS"))
        if self.live.flag("dedicated_server"):
            tabs.append(("server", "DEDICATED SERVER"))
        if self.advanced():
            tabs.append(("downloads", "DOWNLOADS"))
        if tabs:
            tabs.append(("node", "BECOME A NODE"))   # the explainer + leaderboard; switching on needs flags.nodes
        return tabs

    def page_host(self):
        tabs = self.host_tabs()
        x, y, w, h = self.big_panel("HOST", "server", "Run a realm on this PC for friends or the whole community")
        if not tabs:
            self.empty_state(self._scroll_list(x, y, w, h), "Hosting is switched off for now",
                             "The Open Vanilla team turned hosting off in this launcher for the moment. It comes back by itself.")
            return
        tab = self.tab_state.get("host", "realm")
        if tab not in dict(tabs):
            tab = tabs[0][0]
        self.segmented(x, y - 4, tabs, tab, lambda k: self._set_tab("host", k), w=200)
        y, h = y + 38, h - 38
        if tab == "downloads":
            self._host_downloads(x, y, w, h)
        elif tab == "node":
            self._host_node(x, y, w, h)
        elif tab == "server":
            self._host_dedicated(x, y, w, h)
        else:
            self._host_realm(x, y, w, h)

    def host_connections(self):
        """The connection choices on offer: "Through Open Vanilla" only once the relay is live (live.json flags.relay)."""
        return [(k, t) for k, t in CONNECTIONS if k != "relay" or self.live.flag("relay")]

    def _host_cfg(self):
        cfg = {"name": "", "type": "pve", "template": "classicplus", "max_players": 20, "bots": 40,
               "visibility": "private", "connection": "relay", "upnp": False, "firewall": False, "tray": False}
        cfg.update(self.settings.get("p2p_host", {}))
        if cfg["connection"] not in dict(self.host_connections()):
            cfg["connection"] = "direct"   # no relay yet: Direct, with the IP/privacy explainer before it starts
        return cfg

    def _host_realm(self, x, y, w, h):
        host = p2p_module("host")
        if not host:
            self.empty_state(self._scroll_list(x, y, w, h), "Hosting isn't available in this launcher build",
                             "The hosting module (launcher/p2p) is missing or couldn't load:\n" + p2p_error("host"))
            return
        cfg = self._host_cfg()
        running = self.p2p_host is not None
        lw = 430
        form = self.frame_on(x, y, lw, h, bg=PANEL)
        form.columnconfigure(1, weight=1)
        v = self._hostv = {}

        def label(row, text, col=0):
            tk.Label(form, text=text, bg=PANEL, fg=MUTED, font=font(8)).grid(row=row, column=col, sticky="w", pady=(2, 0))

        tk.Label(form, text="YOUR REALM", bg=PANEL, fg=GOLD, font=font(11, "bold", True)).grid(row=0, column=0, columnspan=2, sticky="w")
        label(1, "Realm name")
        e = self.entry(form, width=40)
        e.insert(0, cfg["name"])
        e.grid(row=2, column=0, columnspan=2, sticky="we", ipady=3)
        v["name"] = e
        label(3, "Type")
        label(3, "Template", 1)
        v["type"] = tk.StringVar(value=dict(REALM_TYPES).get(cfg["type"], "PvE"))
        self._optmenu(form, v["type"], [n for _, n in REALM_TYPES], width=10).grid(row=4, column=0, sticky="w")
        tf = tk.Frame(form, bg=PANEL)
        tf.grid(row=4, column=1, sticky="w")
        v["template"] = tk.StringVar(value=cfg["template"])
        for key, name in REALM_TEMPLATES:
            tk.Radiobutton(tf, text=name, variable=v["template"], value=key, bg=PANEL, fg=TEXT, selectcolor=FIELD,
                           activebackground=PANEL, activeforeground=GOLD, font=font(9), highlightthickness=0,
                           bd=0).pack(side="left", padx=(0, 10))
        label(5, "Max players")
        label(5, "Playerbots", 1)
        for col, key, hi in ((0, "max_players", 200), (1, "bots", 500)):
            sp = tk.Spinbox(form, from_=0 if key == "bots" else 1, to=hi, width=6, bg=FIELD, fg=TEXT, buttonbackground=FIELD,
                            insertbackground=GOLD, relief="flat", font=font(10), highlightthickness=1,
                            highlightbackground="#4a3b22")
            sp.delete(0, "end")
            sp.insert(0, str(cfg[key]))
            sp.grid(row=6, column=col, sticky="w", ipady=2)
            v[key] = sp
        def radio(parent, var, key, text, command=None):
            return tk.Radiobutton(parent, text=text, variable=var, value=key, bg=PANEL, fg=TEXT, selectcolor=FIELD,
                                  activebackground=PANEL, activeforeground=GOLD, font=font(9), highlightthickness=0,
                                  bd=0, command=command)

        conn = cfg["connection"]
        label(7, "Connection")
        cf = tk.Frame(form, bg=PANEL)
        cf.grid(row=8, column=0, columnspan=2, sticky="w")
        v["connection"] = tk.StringVar(value=conn)
        for key, text in self.host_connections():
            r = radio(cf, v["connection"], key, text, self._host_conn_changed)
            r.config(font=font(8))
            r.pack(anchor="w")
        row = 9
        if conn != "lan":
            vf = tk.Frame(form, bg=PANEL)
            vf.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
            tk.Label(vf, text="Listing", bg=PANEL, fg=MUTED, font=font(8)).pack(side="left", padx=(0, 8))
            v["visibility"] = tk.StringVar(value=cfg["visibility"])
            for key, name in (("public", "Public (listed)"), ("private", "Private (invite links only)")):
                radio(vf, v["visibility"], key, name).pack(side="left", padx=(0, 8))
            row += 1
        else:
            v["visibility"] = tk.StringVar(value="private")
        checks = [("tray", "Keep hosting in the tray when I close the launcher")]
        if conn == "direct":
            checks = [("upnp", "Open ports 3724 and 8085 on my router (UPnP)"),
                      ("firewall", "Add a Windows Firewall rule (asks for admin once)")] + checks
        for key in ("upnp", "firewall", "tray"):
            v[key] = tk.BooleanVar(value=bool(cfg[key]))
        for key, text in checks:
            self.check(form, text, v[key], self._host_save).grid(row=row, column=0, columnspan=2, sticky="w")
            row += 1
        note = {"relay": "Players reach you through Open Vanilla's relay: nobody sees your home address, and no router "
                         "ports are opened.",
                "direct": "Players connect straight to this PC and see your home IP address.",
                "lan": "Only people on your own network (same Wi-Fi or router) can join. Works without the internet."}[conn]
        tk.Label(form, text=note, bg=PANEL, fg=AMBER if conn == "direct" else MUTED, font=font(8), wraplength=lw - 10,
                 justify="left").grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
        if running:
            self.wbutton(form, "Stop hosting", self.host_stop, danger=True).grid(row=0, column=1, sticky="e")
        else:
            self.wbutton(form, "Start hosting", self.host_start, primary=True, icon="play").grid(row=0, column=1, sticky="e")
        if running:
            # the realm's settings are fixed while it runs (the tray option stays editable)
            stack = [form]
            while stack:
                wd = stack.pop()
                stack.extend(wd.winfo_children())
                if isinstance(wd, (tk.Entry, tk.Spinbox)):
                    wd.config(state="disabled", disabledbackground=FIELD, disabledforeground=MUTED)
                elif isinstance(wd, (tk.Radiobutton, tk.OptionMenu)) or (
                        isinstance(wd, tk.Checkbutton) and wd.cget("variable") != str(v["tray"])):
                    wd.config(state="disabled")
        self._host_live(x + lw + 20, y, w - lw - 20, h)

    def _host_save(self):
        v = getattr(self, "_hostv", None)
        if not v:
            return self._host_cfg()

        def num(key, lo, hi, dflt):
            try:
                return max(lo, min(hi, int(v[key].get())))
            except (ValueError, tk.TclError):
                return dflt

        cfg = self._host_cfg()
        cfg.update(name=v["name"].get().strip()[:40], type={n: k for k, n in REALM_TYPES}.get(v["type"].get(), "pve"),
                   template=v["template"].get(), max_players=num("max_players", 1, 200, 20), bots=num("bots", 0, 500, 40),
                   visibility=v["visibility"].get(), connection=v["connection"].get(), upnp=bool(v["upnp"].get()),
                   firewall=bool(v["firewall"].get()), tray=bool(v["tray"].get()))
        if cfg["connection"] not in dict(self.host_connections()):
            cfg["connection"] = "direct"
        self.settings["p2p_host"] = cfg
        self.save_settings()
        return cfg

    def _host_conn_changed(self):
        self._host_save()
        self.show_page("host", animate=False)

    def direct_privacy_dialog(self, on_accept):
        """Direct hosting shows who can see what before it starts; hosting starts only on I UNDERSTAND."""
        text = ("Direct mode lets friends connect straight to this PC, without Open Vanilla in between. Before you start:\n\n"
                "• Everyone you invite (and anyone they pass the link to) will see your home IP address, and from it "
                "roughly where you are (your city and internet provider).\n\n"
                "• Ports 3724 and 8085 on your router stay open to the internet while you host.\n\n"
                "• In direct mode, sign-in details between you and your friends travel unencrypted.\n\n"
                "Staying safe: only share invite links with people you trust, stop hosting when you're done, and "
                + ("choose “Through Open Vanilla” instead to keep your address hidden." if self.live.flag("relay") else
                   "use “My local network only” for friends in the same house. “Through Open Vanilla”, which keeps your "
                   "address hidden, arrives with the Open Vanilla relay."))
        dlg = self.p2p_dialog("BEFORE YOU HOST DIRECTLY", text, width=560)

        def accept():
            dlg.close()
            on_accept()

        dlg.accept = accept
        if self.live.flag("relay"):
            dlg.buttons(("I understand, start", accept, True), ("Use Open Vanilla instead", lambda: (
                dlg.close(), self._hostv["connection"].set("relay"), self._host_conn_changed()), False))
        else:   # no relay yet: the safe alternative is the local network
            dlg.buttons(("I understand, start", accept, True), ("Local network only", lambda: (
                dlg.close(), self._hostv["connection"].set("lan"), self._host_conn_changed()), False),
                ("Not now", dlg.close, False))
        return dlg

    def host_start(self, confirmed=False, planned=False):
        host = p2p_module("host")
        if not host or self.p2p_host is not None:
            return
        cfg = self._host_save()
        if not 3 <= len(cfg["name"]) <= 40:
            messagebox.showerror("Host a realm", "Give your realm a name (3 to 40 characters).", parent=self)
            return
        if cfg["connection"] == "relay" and not planned and hasattr(host, "plan_connection"):
            # Through Open Vanilla needs the relay's directory to answer; otherwise go Direct (explainer first)
            def probe():
                conn, fell_back = host.plan_connection("relay", self.live.flag("relay"), host.relay_available)
                try:
                    self.after(0, planned_cb, conn, fell_back)
                except RuntimeError:
                    pass

            def planned_cb(conn, fell_back):
                if fell_back:
                    self.settings.setdefault("p2p_host", {})["connection"] = conn
                    self.save_settings()
                    if self.page == "host":
                        self.show_page("host", animate=False)
                    self.notice("Open Vanilla's relay can't be reached right now: hosting Direct instead.", AMBER, 8)
                self.host_start(planned=True)

            self.notice("Checking Open Vanilla's relay…", GOLD, 4)
            threading.Thread(target=probe, daemon=True).start()
            return None
        if cfg["connection"] == "direct" and not confirmed:
            return self.direct_privacy_dialog(lambda: self.host_start(confirmed=True, planned=True))
        import dataclasses
        kw = dict(name=cfg["name"], type=cfg["type"], template=cfg["template"], max_players=cfg["max_players"],
                  bots=cfg["bots"], visibility=cfg["visibility"], data_dir=None)  # None: <Open Vanilla>\host, beside solo\
        try:  # the consent checkboxes, under the names this p2p version uses
            names = {f.name for f in dataclasses.fields(host.HostConfig)}
        except TypeError:
            names = set()
        direct = cfg["connection"] == "direct"
        for k, val in (("upnp_consent", direct and cfg["upnp"]), ("upnp", direct and cfg["upnp"]),
                       ("firewall", direct and cfg["firewall"]), ("connection", cfg["connection"]),
                       ("node_network", self.nodes_on())):
            if k in names:
                kw[k] = val
        try:
            hc = host.HostConfig(**kw)
            sess = host.HostSession(hc, self._host_progress_cb)
        except Exception as e:
            messagebox.showerror("Host a realm", f"Couldn't set up the realm.\n\n{e}", parent=self)
            return
        self.p2p_host = sess
        self.p2p_host_status = {}
        self.p2p_host_state = "Starting…"
        def started(err):
            if err and self.p2p_host is sess:  # it never came up: back to the form
                self.p2p_host, self.p2p_host_state = None, None
            elif self.p2p_host is sess:
                self.p2p_host_state = "Running"

        self._host_thread(sess.start, "Your realm is up.", "Couldn't start hosting", started)
        self.show_page("host", animate=False)
        self.after(1500, self._host_poll)

    def _host_progress_cb(self, *args, **kw):
        """p2p.host reports progress_cb(stage, text, fraction or None)."""
        text = next((a for a in reversed(args) if isinstance(a, str)), None) or kw.get("text")
        frac = next((a for a in args if isinstance(a, float)), None)
        if text and frac is not None:
            text = f"{text} {frac * 100:.0f}%"
        if text:
            try:
                self.after(0, self._host_progress, text)
            except RuntimeError:
                pass

    def _host_progress(self, text):
        self.p2p_host_state = text[:80]
        lab = getattr(self, "_host_state_lbl", None)
        if lab is not None and self.page == "host":
            try:
                lab.config(text=self.p2p_host_state)
            except tk.TclError:
                pass

    def _host_thread(self, fn, ok_text, fail, then=None):
        def work():
            try:
                fn()
                err = None
            except Exception as e:
                err = str(e) or type(e).__name__
            try:
                self.after(0, done, err)
            except RuntimeError:
                pass

        def done(err):
            if err:
                messagebox.showerror("Host", f"{fail}.\n\n{err}", parent=self)
            elif ok_text:
                self.notice(ok_text, GREEN, 5)
            if then:
                then(err)
            try:
                if self.page == "host":
                    self.show_page("host", animate=False)
            except tk.TclError:
                pass  # the launcher closed in then()

        threading.Thread(target=work, daemon=True).start()

    def host_stop(self, then=None):
        sess = self.p2p_host
        if sess is None:
            if then:
                then(None)
            return

        def stopped(err):
            self.p2p_host = None
            self.p2p_host_state = None
            self.p2p_host_status = {}
            self._tray_stop()
            if then:
                then(err)

        self.p2p_host_state = "Stopping… (saving characters)"
        self._host_thread(sess.stop, "Hosting stopped. Characters are saved on this PC.", "Couldn't stop cleanly", stopped)
        if self.page == "host":
            self.show_page("host", animate=False)

    def host_restart(self):
        sess = self.p2p_host
        if sess is None or not messagebox.askyesno("Restart", "Restart the realm? Players are disconnected for a minute.",
                                                   parent=self):
            return
        self.p2p_host_state = "Restarting…"

        def both():
            sess.stop()
            sess.start()

        self._host_thread(both, "Realm restarted.", "Couldn't restart",
                          lambda err: setattr(self, "p2p_host_state", "Restart failed" if err else "Running"))

    def _host_poll(self):
        sess = self.p2p_host
        if sess is None or self._host_polling:
            return
        self._host_polling = True

        def work():
            try:
                st = dict(sess.status() or {})
            except Exception as e:
                st = {"error": str(e)}
            try:
                self.after(0, done, st)
            except RuntimeError:
                pass

        def done(st):
            self._host_polling = False
            if self.p2p_host is not sess:
                return
            self.p2p_host_status = st
            self._host_paint_live()
            self.after(2000, self._host_poll)

        threading.Thread(target=work, daemon=True).start()

    def _host_live(self, x, y, w, h):
        """The live panel: reachability and listing badges, load, players with Kick/Ban, and the realm's actions."""
        self.card(x, y, w, h, "live", "hostlive")
        f = self.frame_on(x + 18, y + 16, w - 36, h - 32, bg="#0d0a11")
        self._host_live_frame = f
        self._host_live_w = w - 50
        self._host_paint_live()

    def _host_paint_live(self):
        f = getattr(self, "_host_live_frame", None)
        if f is None or self.page != "host" or not f.winfo_exists():
            return
        for c in f.winfo_children():
            c.destroy()
        bg = "#0d0a11"
        sess, st = self.p2p_host, self.p2p_host_status or {}
        top = tk.Frame(f, bg=bg)
        top.pack(fill="x")
        tk.Label(top, text="LIVE", bg=bg, fg=GOLD, font=font(11, "bold", True)).pack(side="left")
        if sess is None:
            tk.Label(f, text="Not hosting.", bg=bg, fg=TEXT, font=font(10, "bold")).pack(anchor="w", pady=(16, 4))
            tk.Label(f, text="Fill in the form and press START HOSTING. Your realm runs on this PC with the Solo server; "
                             "public realms appear in the realm browser once Open Vanilla can reach them, private ones "
                             "only through invite links you make here.", bg=bg, fg=MUTED, font=font(9),
                     wraplength=self._host_live_w, justify="left").pack(anchor="w")
            return
        reach = str(first(st, "reachability", default="none"))
        rcol = {"direct": GREEN, "upnp": GREEN, "relay": CYAN}.get(reach, RED)
        rtext = {"direct": "REACHABLE · DIRECT", "upnp": "REACHABLE · UPNP", "relay": "REACHABLE · RELAY"}.get(reach, "NOT REACHABLE")
        self._badge(top, rtext, "signal", "#151a22", rcol, bg)
        listed = bool(first(st, "listed", default=False))
        self._badge(top, "LISTED" if listed else ("UNLISTED · PRIVATE" if self._host_cfg()["visibility"] == "private"
                                                  else "NOT LISTED YET"),
                    "realms", "#1a1620", GREEN if listed else MUTED, bg)
        self._host_state_lbl = tk.Label(top, text=self.p2p_host_state or "", bg=bg, fg=AMBER, font=font(8, "bold"))
        self._host_state_lbl.pack(side="right")
        # how players reach this PC, and what they can see of it
        conn = str(first(st, "connection", default=self._host_cfg()["connection"]))
        info = tk.Frame(f, bg=bg)
        info.pack(fill="x", pady=(6, 0))
        mode = {"relay": "Through Open Vanilla (address hidden)", "direct": "Direct from your home connection",
                "lan": "Local network only"}.get(conn, conn)
        tk.Label(info, text="CONNECTION", bg=bg, fg=MUTED, font=font(7, "bold")).pack(side="left")
        tk.Label(info, text=mode, bg=bg, fg=AMBER if conn == "direct" else TEXT, font=font(9, "bold")).pack(side="left", padx=(6, 14))
        ip = first(st, "lan_ip") if conn == "lan" else first(st, "external_ip", "lan_ip")
        if conn != "relay" and ip:
            info = tk.Frame(f, bg=bg)
            info.pack(fill="x")
            tk.Label(info, text="YOUR ADDRESS", bg=bg, fg=MUTED, font=font(7, "bold")).pack(side="left")
            addr = tk.Label(info, text=f"{ip}  (who can see this?)", bg=bg, fg=GOLD, font=font(9, "bold"), cursor=self.CUR_HAND)
            addr.pack(side="left", padx=(6, 0))
            self._host_addr_lbl = addr
            self._hover_tip(addr, "Players on your network can see this address." if conn == "lan" else
                            "Everyone you invite, and anyone they pass the link to, sees this address and from it "
                            "roughly where you are (city, internet provider). Use “Through Open Vanilla” to hide it.")
        det = tk.Frame(f, bg=bg)
        det.pack(fill="x")
        ports = first(st, "exposed_ports", default=[]) or []
        fp = first(st, "fingerprint")
        bits = [("Open ports: " + ", ".join(str(p) for p in ports)) if ports else "No ports open on this PC"]
        if fp:
            bits.append(f"Host key {fp}")
        tk.Label(det, text="   ·   ".join(bits), bg=bg, fg=MUTED, font=font(8), anchor="w").pack(fill="x")
        players = first(st, "players", default=[])
        names = [p if isinstance(p, str) else rf(p, "name", "?") for p in players] if isinstance(players, (list, tuple)) else []
        count = len(names) if isinstance(players, (list, tuple)) else int(players or 0)
        cap = self._host_cfg()["max_players"]
        grid = tk.Frame(f, bg=bg)
        grid.pack(fill="x", pady=(10, 6))
        cpu, ram = first(st, "cpu", "cpu_percent"), first(st, "ram", "ram_mb")
        stats = (("PLAYERS", f"{count}/{cap}"),
                 ("CPU", f"{float(cpu):.0f}%" if cpu is not None else "—"),
                 ("RAM", f"{float(ram):.0f} MB" if ram is not None else "—"),
                 ("UPLOAD", fmt_rate(first(st, "up_kbps", "up", "upload_kbps"))),
                 ("DOWNLOAD", fmt_rate(first(st, "down_kbps", "down", "download_kbps"))))
        for i, (k, val) in enumerate(stats):
            cell = tk.Frame(grid, bg="#17121c", highlightthickness=1, highlightbackground="#3a2f22")
            cell.grid(row=0, column=i, sticky="we", padx=(0, 6))
            grid.columnconfigure(i, weight=1)
            tk.Label(cell, text=k, bg="#17121c", fg=MUTED, font=font(7, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
            tk.Label(cell, text=val, bg="#17121c", fg=TEXT, font=font(11, "bold")).pack(anchor="w", padx=8, pady=(0, 4))
        err = first(st, "error", "last_error")
        if err:
            tk.Label(f, text=str(err)[:160], bg=bg, fg=RED, font=font(8), anchor="w").pack(fill="x")
        acts2 = tk.Frame(f, bg=bg)
        acts2.pack(side="bottom", fill="x", pady=(4, 0))
        acts1 = tk.Frame(f, bg=bg)
        acts1.pack(side="bottom", fill="x", pady=(4, 0))
        acts = tk.Frame(f, bg=bg)
        acts.pack(side="bottom", fill="x", pady=(6, 0))
        self.wbutton(acts, "Guest invite (no account needed)", lambda: self.host_invite_dialog(guest=True),
                     primary=True, icon="link", size=8).pack(side="left", padx=(0, 6))
        if conn == "relay":
            self.wbutton(acts, "Invite", self.host_invite_dialog, icon="link", size=8).pack(side="left", padx=(0, 6))
        self.wbutton(acts1, "Make an account for a friend", self.host_account_dialog, icon="account",
                     size=8).pack(side="left", padx=(0, 6))
        for text, cmd, icon in (("Announce", self.host_announce, "megaphone"), ("Backup now", self.host_backup, "box"),
                                ("Restart", self.host_restart, "refresh")):
            self.wbutton(acts2, text, cmd, icon=icon, size=8).pack(side="left", padx=(0, 6))
        lst = tk.Frame(f, bg=bg)
        lst.pack(fill="both", expand=True)
        if not names:
            tk.Label(lst, text="No players online yet." if count == 0 else f"{count} players online.",
                     bg=bg, fg=MUTED, font=font(9)).pack(anchor="w", pady=6)
            # this p2p version counts players but doesn't name them: kick or ban by character name
            by = tk.Frame(lst, bg=bg)
            by.pack(fill="x")
            tk.Label(by, text="Character", bg=bg, fg=MUTED, font=font(8)).pack(side="left", padx=(0, 6))
            ent = self.entry(by, width=18)
            ent.pack(side="left", ipady=3)
            self._host_name_entry = ent
            self.wbutton(by, "Kick", lambda: ent.get().strip() and self.host_player(ent.get().strip(), "kick"),
                         size=7).pack(side="left", padx=(8, 0))
            self.wbutton(by, "Ban", lambda: ent.get().strip() and self.host_player(ent.get().strip(), "ban"),
                         danger=True, size=7).pack(side="left", padx=(4, 0))
        for n in names[:4]:
            row = tk.Frame(lst, bg="#17121c", highlightthickness=1, highlightbackground="#3a2f22")
            row.pack(fill="x", pady=1)
            tk.Label(row, text=n, bg="#17121c", fg=TEXT, font=font(9, "bold")).pack(side="left", padx=10, pady=3)
            self.wbutton(row, "Ban", lambda n=n: self.host_player(n, "ban"), danger=True, size=7).pack(side="right", padx=4)
            self.wbutton(row, "Kick", lambda n=n: self.host_player(n, "kick"), size=7).pack(side="right")
        if len(names) > 4:
            tk.Label(lst, text=f"…and {len(names) - 4} more", bg=bg, fg=MUTED, font=font(8)).pack(anchor="w")

    def host_player(self, name, what):
        sess = self.p2p_host
        if sess is None:
            return
        verb = {"kick": "Kick", "ban": "Ban"}[what]
        if not messagebox.askyesno(verb, f"{verb} {name}?" + (" They can't come back to your realm." if what == "ban" else ""),
                                   parent=self):
            return
        self._host_thread(lambda: getattr(sess, what)(name), f"{verb}ed {name}." if what == "kick" else f"Banned {name}.",
                          f"Couldn't {what} {name}")

    def host_announce(self):
        sess = self.p2p_host
        if sess is None:
            return
        dlg = self.p2p_dialog("ANNOUNCE", "A message every player on your realm sees on screen.", width=460)
        e = self.entry(dlg.body, width=48)
        e.pack(fill="x", ipady=4)
        e.focus_set()

        def send():
            text = e.get().strip()[:200]
            dlg.close()
            if text:
                self._host_thread(lambda: sess.announce(text), "Announced.", "Couldn't send the announcement")

        e.bind("<Return>", lambda ev: send())
        dlg.buttons(("Announce", send, True), ("Cancel", dlg.close, False))
        return dlg

    def host_backup(self):
        sess = self.p2p_host
        if sess is not None:
            self.notice("Backing up the realm…", GOLD, 4)
            self._host_thread(sess.backup, "Backup saved.", "Backup failed")

    def host_invite_dialog(self, guest=False):
        sess = self.p2p_host
        if sess is None:
            return
        if guest:
            dlg = self.p2p_dialog("GUEST INVITE", "A link that needs no Open Vanilla account and works even while Open Vanilla "
                                  "is offline. Your friend pastes it in the launcher's Realms tab and gets a guest "
                                  "account on your realm. Anyone with the link can use it until it runs out of uses or "
                                  "expires.", width=500)
        else:
            dlg = self.p2p_dialog("INVITE LINK", "Anyone with the link can join your realm (private realms too), until it "
                                                 "runs out of uses or expires. Send it to friends; they paste it in the "
                                                 "launcher's Realms tab or open it in their browser.", width=500)
        row = tk.Frame(dlg.body, bg=PANEL)
        row.pack(fill="x", pady=(0, 8))
        uses_opts = (("1 use", 1), ("5 uses", 5), ("25 uses", 25), ("Unlimited", 0))
        exp_opts = (("1 hour", 1), ("1 day", 24), ("1 week", 168))
        uv, ev = tk.StringVar(value="5 uses"), tk.StringVar(value="1 day")
        tk.Label(row, text="Uses", bg=PANEL, fg=MUTED, font=font(8)).pack(side="left", padx=(0, 6))
        self._optmenu(row, uv, [n for n, _ in uses_opts], width=9).pack(side="left", padx=(0, 14))
        tk.Label(row, text="Expires after", bg=PANEL, fg=MUTED, font=font(8)).pack(side="left", padx=(0, 6))
        self._optmenu(row, ev, [n for n, _ in exp_opts], width=9).pack(side="left")
        out = self.entry(dlg.body, width=56)
        out.pack(fill="x", ipady=4)
        out.config(state="readonly", readonlybackground=FIELD)
        dlg.link = out

        def show(link):
            out.config(state="normal")
            out.delete(0, "end")
            out.insert(0, link)
            out.config(state="readonly")
            self._copy(link, "Invite link copied")

        def make():
            uses, hours = dict(uses_opts)[uv.get()], dict(exp_opts)[ev.get()]

            def work():
                try:
                    link, err = (sess.guest_invite(uses, hours) if guest else sess.invite(uses, hours)), None
                except Exception as e:
                    link, err = None, str(e)
                try:
                    self.after(0, lambda: show(link) if link else messagebox.showerror(
                        "Invite", f"Couldn't make a link.\n\n{OFFLINE_TEXT + chr(10) + chr(10) if is_offline_error(err) else ''}{err}",
                        parent=self))
                except RuntimeError:
                    pass

            threading.Thread(target=work, daemon=True).start()

        dlg.make = make
        dlg.buttons(("Make & copy link", make, True), ("Close", dlg.close, False))
        return dlg

    def host_account_dialog(self):
        """A named account on this realm for a friend without the launcher (stock client): copyable details."""
        sess = self.p2p_host
        if sess is None:
            return
        dlg = self.p2p_dialog("ACCOUNT FOR A FRIEND", "For a friend who plays with the stock client instead of the "
                              "launcher. Pick a name and password (letters and numbers), then send them the details.",
                              width=500)
        row = tk.Frame(dlg.body, bg=PANEL)
        row.pack(fill="x")
        ents = {}
        for key, label, w in (("name", "Account name", 16), ("password", "Password", 16)):
            box = tk.Frame(row, bg=PANEL)
            box.pack(side="left", padx=(0, 12))
            tk.Label(box, text=label, bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w")
            e = self.entry(box, width=w)
            e.pack(ipady=3)
            ents[key] = e
        out = tk.Text(dlg.body, height=4, width=56, bg=FIELD, fg=TEXT, relief="flat", font=font(9),
                      highlightthickness=1, highlightbackground="#4a3b22", wrap="word")
        out.pack(fill="x", pady=(10, 0))
        out.config(state="disabled")
        dlg.name, dlg.password, dlg.out = ents["name"], ents["password"], out

        def show(acc):
            rl = acc.get("realmlist")
            text = (f"Realm: {acc.get('realm', '')}\nAccount: {acc['user']}\nPassword: {acc['password']}\n"
                    + (f"In realmlist.wtf: set realmlist {rl}" if rl else "Through Open Vanilla's relay: they join with the launcher "
                       "(guest invite); the stock client needs Direct or LAN mode."))
            out.config(state="normal")
            out.delete("1.0", "end")
            out.insert("1.0", text)
            out.config(state="disabled")
            self._copy(text, "Account details copied")

        def make():
            name, pw = ents["name"].get(), ents["password"].get()

            def work():
                try:
                    acc, err = sess.create_account(name, pw), None
                except Exception as e:
                    acc, err = None, str(e)
                try:
                    self.after(0, lambda: show(acc) if acc else messagebox.showerror("Account", err, parent=self))
                except RuntimeError:
                    pass

            threading.Thread(target=work, daemon=True).start()

        dlg.make = make
        dlg.buttons(("Make & copy details", make, True), ("Close", dlg.close, False))
        return dlg

    def _hover_tip(self, widget, text):
        """A small tooltip window under `widget` while the pointer is on it."""
        state = {}

        def show(_e=None):
            hide()
            t = state["tip"] = tk.Toplevel(widget, bg="#5a4626")
            t.overrideredirect(True)
            tk.Label(t, text=text, bg="#17121c", fg=TEXT, font=font(8), wraplength=320, justify="left",
                     padx=8, pady=6).pack(padx=1, pady=1)
            t.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}")

        def hide(_e=None):
            t = state.pop("tip", None)
            if t is not None:
                try:
                    t.destroy()
                except tk.TclError:
                    pass

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)
        widget.bind("<Destroy>", hide, add="+")
        widget.tip_text = text

    # tray: "keep hosting in the tray" — pystray when it is installed, else the window is minimised

    def _tray_start(self):
        self.withdraw()
        try:
            import pystray
        except ImportError:
            self.deiconify()
            self.iconify()
            return
        menu = pystray.Menu(pystray.MenuItem("Open Open Vanilla", lambda *a: self.after(0, self._tray_open), default=True),
                            pystray.MenuItem("Stop hosting and quit", lambda *a: self.after(0, self._tray_quit)))
        icon = pystray.Icon("OpenVanilla", art.kit_image("emblem", height=64) or art.icon("server", 64, GOLD),
                            "Open Vanilla — hosting " + (self._host_cfg()["name"] or "a realm"), menu)
        self._tray = icon
        threading.Thread(target=icon.run, daemon=True).start()

    def _tray_open(self):
        self._tray_stop()
        self.deiconify()
        self.lift()

    def _tray_quit(self):
        self._tray_stop()
        self.host_stop(then=lambda err: self.destroy())

    def _tray_stop(self):
        icon, self._tray = getattr(self, "_tray", None), None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    # ----- Downloads & seeding (launcher/p2p/torrent.py)

    def torrents(self):
        """The torrent client, made on first use (libtorrent loads only then)."""
        if self.p2p_torrents is None:
            t = p2p_module("torrent")
            if not t:
                return None
            ts = self.settings.setdefault("p2p_torrent", {"seeding": False, "upload_kbps": 512})
            try:
                self.p2p_torrents = t.Torrents(os.path.join(LAYOUT.cache, "torrents"), ts)
                if ts.get("seeding") and not self.p2p_torrents.seeding_enabled:
                    self.p2p_torrents.enable_seeding(int(ts.get("upload_kbps", 512)))
            except Exception as e:
                _P2P_ERRS["torrent"] = str(e)
                return None
        return self.p2p_torrents

    def _host_downloads(self, x, y, w, h):
        t = self.torrents()
        if not t:
            self.empty_state(self._scroll_list(x, y, w, h), "Downloads aren't available in this launcher build",
                             "The download module (launcher/p2p) is missing or couldn't load. Game updates still come "
                             "straight from the website.\n" + p2p_error("torrent"))
            return
        sw = 360
        self._dl_frame = self.frame_on(x, y, w - sw - 20, h, bg=PANEL)
        self._dl_paint()
        # seeding settings
        sx = x + w - sw
        self.card(sx, y, sw, h, "seeding", "seeding")
        f = self.frame_on(sx + 18, y + 16, sw - 36, h - 32, bg="#0d0a11")
        bg = "#0d0a11"
        ts = self.settings.setdefault("p2p_torrent", {"seeding": False, "upload_kbps": 512})
        on = bool(t.seeding_enabled)
        head = tk.Frame(f, bg=bg)
        head.pack(fill="x")
        tk.Label(head, image=self._tk_icon("seed", 20, GREEN if on else GOLD_DIM), bg=bg).pack(side="left", padx=(0, 8))
        tk.Label(head, text="SEEDING", bg=bg, fg=GOLD, font=font(11, "bold", True)).pack(side="left")
        tk.Label(head, text="ON" if on else "OFF", bg=bg, fg=GREEN if on else MUTED, font=font(9, "bold")).pack(side="right")
        tk.Label(f, text=("You share Open Vanilla's own downloads with other players, up to the limit below." if on else
                          "Off. Turn it on to help other players download Open Vanilla faster."),
                 bg=bg, fg=TEXT, font=font(9), wraplength=sw - 50, justify="left").pack(anchor="w", pady=(8, 8))
        row = tk.Frame(f, bg=bg)
        row.pack(fill="x")
        tk.Label(row, text="Upload limit (KB/s)", bg=bg, fg=MUTED, font=font(8)).pack(side="left")
        lim = tk.Spinbox(row, from_=32, to=100000, increment=64, width=7, bg=FIELD, fg=TEXT, buttonbackground=FIELD,
                         insertbackground=GOLD, relief="flat", font=font(10), highlightthickness=1, highlightbackground="#4a3b22")
        lim.delete(0, "end")
        lim.insert(0, str(ts.get("upload_kbps", 512)))
        lim.pack(side="right", ipady=2)
        self._seed_limit = lim

        def save_limit(_e=None):
            try:
                ts["upload_kbps"] = max(32, int(lim.get()))
            except ValueError:
                return
            self.save_settings()
            if t.seeding_enabled:
                t.enable_seeding(ts["upload_kbps"])

        lim.bind("<FocusOut>", save_limit)
        lim.bind("<Return>", save_limit)
        b = tk.Frame(f, bg=bg)
        b.pack(fill="x", pady=(12, 0))
        if on:
            self.wbutton(b, "Stop seeding", lambda: self.set_seeding(False), danger=True).pack(side="left")
        else:
            self.wbutton(b, "Turn on seeding…", lambda: self.set_seeding(True), primary=True, icon="seed").pack(side="left")
        what = tk.Label(f, text="What is seeding?", bg=bg, fg=GOLD_DIM, font=font(9, "bold"), cursor=self.CUR_HAND)
        what.pack(side="bottom", anchor="w")
        what.bind("<Button-1>", lambda e: self.seeding_explainer(info_only=True))
        self._dl_poll()

    def _dl_paint(self):
        f = getattr(self, "_dl_frame", None)
        t = self.p2p_torrents
        if f is None or t is None or self.page != "host" or not f.winfo_exists():
            return
        try:
            st = t.status() or {}
        except Exception as e:
            st = {"error": str(e)}
        for c in f.winfo_children():
            c.destroy()
        items = first(st, "torrents", "downloads", default=[]) or []
        head = tk.Frame(f, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text="DOWNLOADS", bg=PANEL, fg=GOLD, font=font(11, "bold", True)).pack(side="left")
        lt = first(st, "libtorrent", "backend")
        mode = ("peer-to-peer + web seeds" if lt in (True, "libtorrent") else
                "plain HTTP (libtorrent isn't installed)" if lt in (False, "http") else "")
        peers = first(st, "peers", default=sum(int(first(it, "peers", default=0) or 0) for it in items))
        tk.Label(head, text=(f"down {fmt_rate(first(st, 'down_kbps', 'down', default=0))}   up "
                             f"{fmt_rate(first(st, 'up_kbps', 'up', default=0))}   {peers} peers"
                             + (f"   ·   {mode}" if mode else "")),
                 bg=PANEL, fg=MUTED, font=font(8)).pack(side="right")
        if st.get("error"):
            tk.Label(f, text=st["error"], bg=PANEL, fg=RED, font=font(8), anchor="w").pack(fill="x")
        if not items:
            tk.Label(f, text="Nothing downloading. Game and realm updates show up here while they download.", bg=PANEL,
                     fg=MUTED, font=font(9)).pack(anchor="w", pady=18)
        for it in items[:7]:
            row = tk.Frame(f, bg="#17121c", highlightthickness=1, highlightbackground="#3a2f22")
            row.pack(fill="x", pady=3)
            top = tk.Frame(row, bg="#17121c")
            top.pack(fill="x", padx=10, pady=(5, 0))
            prog = float(first(it, "progress", default=0) or 0)
            tk.Label(top, text=first(it, "name", default="?"), bg="#17121c", fg=TEXT, font=font(9, "bold")).pack(side="left")
            state = first(it, "state", default="seeding" if it.get("seeding") else
                          ("done" if prog >= 1 else "downloading"))
            down, up = first(it, "down_kbps", "down"), first(it, "up_kbps", "up")
            parts = [state, f"{prog * 100:.0f}%"] + ([f"↓ {fmt_rate(down)}  ↑ {fmt_rate(up)}"] if down is not None or
                                                     up is not None else []) + [f"{first(it, 'peers', default=0)} peers"]
            tk.Label(top, text="  ·  ".join(parts), bg="#17121c", fg=MUTED, font=font(8)).pack(side="right")
            bar = tk.Label(row, image=self.img(f"dlbar_{int(prog * 100)}", art.track(400, 6, prog, GREEN if prog >= 1 else GOLD_DIM)),
                           bg="#17121c")
            bar.pack(anchor="w", padx=10, pady=(3, 7))

    def _dl_poll(self, gen=None):
        """Refresh the Downloads list every second while it is on screen (one loop per page view)."""
        if gen is None:
            self._dl_gen += 1
            gen = self._dl_gen
        elif gen != self._dl_gen or self.page != "host" or self.tab_state.get("host") != "downloads":
            return
        else:
            self._dl_paint()
        self.after(1000, self._dl_poll, gen)

    def set_seeding(self, on):
        t = self.torrents()
        if not t:
            return
        ts = self.settings.setdefault("p2p_torrent", {"seeding": False, "upload_kbps": 512})
        if not on:
            if hasattr(t, "disable_seeding"):
                t.disable_seeding()
            else:
                t.seeding_enabled = False
            ts["seeding"] = False
            self.save_settings()
            self.notice("Seeding stopped.", AMBER, 4)
            self.show_page("host", animate=False)
            return
        self.seeding_explainer()

    def seeding_explainer(self, info_only=False):
        """Shown before seeding turns on (seeding is opt-in): what it is, what is shared, the limit, how to stop."""
        ts = self.settings.setdefault("p2p_torrent", {"seeding": False, "upload_kbps": 512})
        try:
            limit = max(32, int(self._seed_limit.get()))
        except (AttributeError, ValueError, tk.TclError):
            limit = int(ts.get("upload_kbps", 512))
        text = ("Seeding means the launcher uploads pieces of Open Vanilla downloads you already have to other players, "
                "so updates reach everyone faster and Open Vanilla's servers cost less.\n\n"
                "• Only Open Vanilla's own files are shared: the launcher, the Open Vanilla client and our patch files. Never "
                "Blizzard's game files, your WoW folder, characters, or anything else on your PC.\n\n"
                f"• Upload is capped at {limit} KB/s (change it under Upload limit). Other players can see your "
                "IP address while you seed, as with any torrent.\n\n"
                "• Stop any time: Host → Downloads → STOP SEEDING. Seeding also stops when the launcher closes.")
        dlg = self.p2p_dialog("SEEDING", text, width=540)

        def accept():
            dlg.close()
            t = self.torrents()
            if not t:
                return
            ts.update(seeding=True, upload_kbps=limit)
            self.save_settings()
            t.enable_seeding(limit)
            self.notice(f"Seeding on, up to {limit} KB/s. Thank you!", GREEN, 5)
            self.show_page("host", animate=False)

        if info_only:
            dlg.buttons(("Close", dlg.close, True))
        else:
            dlg.buttons(("Turn on seeding", accept, True), ("Not now", dlg.close, False))
        dlg.accept = accept
        return dlg

    # ----- Become a node (launcher/p2p/node.py; docs/NODE_NETWORK.md). Off by default, one click off.

    NODES_JSON_URL = "https://openvanilla.app/community/nodes.json"           # the site's copy (tiers, status)
    NODES_LIVE_URL = "https://play.openvanilla.app/api/nodes/leaderboard"     # the directory's live list (patch 0016)
    NODES_PAGE_URL = "https://openvanilla.app/nodes.html"

    def nodes_on(self):
        """The node network is open: live.json flags.nodes, or OPENVANILLA_NODES=1 for the maintainer's test round."""
        return self.live.flag("nodes") or os.environ.get("OPENVANILLA_NODES") == "1"

    def node_service(self):
        if self.p2p_node is None:
            n = p2p_module("node")
            if not n:
                return None
            cfg = self.settings.setdefault("p2p_node", {})
            try:
                up = p2p_module("upnp")
                self.p2p_node = n.NodeService(cfg, save=lambda: self.after(0, self.save_settings),
                                              relay_enabled=self.nodes_on(), torrents=self.p2p_torrents,
                                              mapper=up.PortMapper(consent=True) if up else None,
                                              on_status=self._node_status_changed)
            except Exception as e:
                _P2P_ERRS["node"] = f"{type(e).__name__}: {e}"
                return None
            self.bind("<Destroy>", lambda e: e.widget is self and self._node_shutdown(), add="+")
        return self.p2p_node

    def _node_status_changed(self, st):
        """Called from the node's threads: tell the game (Node/Status.lua) and repaint if it's on screen."""
        n = p2p_module("node")
        if n:
            n.write_game_status([LAYOUT.addons_enabled, getattr(LAYOUT, "engine_addons", None)], st)
        try:
            self.after(0, self._node_paint)
        except RuntimeError:
            pass

    def _node_resume(self):
        svc = self.node_service()
        if svc is not None:
            threading.Thread(target=svc.resume, daemon=True).start()

    def _node_shutdown(self):
        """Launcher closing: the node stops with it (the setting stays, so it resumes next time)."""
        svc = self.p2p_node
        if svc is None or not svc.machine.running:
            return
        enabled = svc.cfg.get("enabled")
        svc.save = lambda: None
        try:
            svc.turn_off()
        except Exception:
            pass
        svc.cfg["enabled"] = enabled

    def _host_node(self, x, y, w, h):
        svc = self.node_service()
        if not svc:
            self.empty_state(self._scroll_list(x, y, w, h), "Nodes aren't available in this launcher build",
                             "The node module (launcher/p2p) is missing or couldn't load.\n" + p2p_error("node"))
            return
        svc.relay_enabled = self.nodes_on()
        bw = 380
        self._node_frame = self.frame_on(x, y, w - bw - 20, h, bg=PANEL)
        self._node_board_frame = self.frame_on(x + w - bw, y, bw, h, bg="#0d0a11")
        self._node_paint()
        self._node_board_paint()
        if self._node_board["data"] is None and not self._node_board["loading"]:
            self._node_board_fetch()
        self._node_poll()

    def _node_poll(self, gen=None):
        if gen is None:
            self._node_gen += 1
            gen = self._node_gen
        elif gen != self._node_gen or self.page != "host" or self.tab_state.get("host") != "node":
            return
        else:
            self._node_paint()
        self.after(2000, self._node_poll, gen)

    def _node_paint(self):
        f = getattr(self, "_node_frame", None)
        svc = self.p2p_node
        if f is None or svc is None or self.page != "host" or not f.winfo_exists():
            return
        if f.focus_get() is not None and str(f.focus_get()).startswith(str(f)):
            return          # don't repaint under the volunteer's typing
        for c in f.winfo_children():
            c.destroy()
        st = svc.status()
        cfg = svc.cfg
        on = st["on"]
        head = tk.Frame(f, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, image=self._tk_icon("server", 20, GREEN if on else GOLD_DIM), bg=PANEL).pack(side="left", padx=(0, 8))
        tk.Label(head, text="BECOME A NODE", bg=PANEL, fg=GOLD, font=font(11, "bold", True)).pack(side="left")
        color = {"verified": "#4fc3b0", "pending": GREEN, "paused": AMBER, "error": RED}.get(st["state"], MUTED)
        tk.Label(head, text=st["label"].upper(), bg=PANEL, fg=color, font=font(9, "bold")).pack(side="right")
        if st["verified"]:
            self._badge(head, "NODE", "shield", "#10282a", "#4fc3b0", PANEL)
        intro = ("Relay other players' encrypted game traffic so community realms need no open ports and nobody's "
                 "home address is shown. More nodes = more players can connect at once. A node never shares "
                 "Blizzard's files or anything on your PC, and it doesn't make any one world bigger.")
        tk.Label(f, text=intro, bg=PANEL, fg=TEXT, font=font(9), wraplength=560, justify="left").pack(
            anchor="w", pady=(8, 4))
        tiers_line = "Tiers: VERIFIED realms (official or vetted)  ·  COMMUNITY P2P realms  ·  verified P2P NODES (you, once checked)"
        tk.Label(f, text=tiers_line, bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w", pady=(0, 8))
        if not svc.relay_enabled and not on:
            tk.Label(f, text="The node network isn't open yet. The test round starts with Open Vanilla's own relay; "
                             "volunteer nodes open after it (watch the news on Home). You can set things up now.",
                     bg=PANEL, fg=AMBER, font=font(9), wraplength=560, justify="left").pack(anchor="w", pady=(0, 8))
        if st.get("error"):
            tk.Label(f, text=st["error"], bg=PANEL, fg=RED, font=font(9), wraplength=560, justify="left").pack(anchor="w")
        if on:
            gb = lambda n: f"{n / 1e9:.2f} GB"
            tk.Label(f, text=(f"Relayed today {gb(st['relayed_today'])} of {st['daily_gb']:g} GB  ·  total {gb(st['relayed_total'])}  ·  "
                              f"{st['hosts_now']} realms, {st['streams_now']} connections  ·  up to {st['kbps']} KB/s"),
                     bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w", pady=(4, 2))
            checks = st.get("checks") or {}
            if checks:
                for k, c in checks.items():
                    ok = isinstance(c, dict) and c.get("ok")
                    tk.Label(f, text=("✓ " if ok else "✗ ") + f"{k}: {c.get('detail', '') if isinstance(c, dict) else ''}",
                             bg=PANEL, fg=GREEN if ok else AMBER, font=font(8)).pack(anchor="w")
            if st.get("message"):
                tk.Label(f, text="Maintainer: " + st["message"], bg=PANEL, fg=TAN, font=font(8), wraplength=560,
                         justify="left").pack(anchor="w")
        form = tk.Frame(f, bg=PANEL)
        form.pack(fill="x", pady=(10, 0))
        v = self._nodev = {}

        def spin(col, label, key, lo, hi, step):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED, font=font(8)).grid(row=0, column=col, sticky="w", padx=(0, 12))
            sp = tk.Spinbox(form, from_=lo, to=hi, increment=step, width=7, bg=FIELD, fg=TEXT, buttonbackground=FIELD,
                            insertbackground=GOLD, relief="flat", font=font(10), highlightthickness=1,
                            highlightbackground="#4a3b22", state="disabled" if on else "normal")
            sp.delete(0, "end")
            sp.insert(0, str(cfg.get(key)))
            sp.grid(row=1, column=col, sticky="w", padx=(0, 12), ipady=2)
            v[key] = sp
        spin(0, "Bandwidth cap (KB/s)", "kbps", 256, 100000, 128)
        spin(1, "Daily cap (GB)", "daily_gb", 5, 10000, 5)
        spin(2, "Node port (TCP)", "port", 1024, 65535, 1)
        reach = tk.Frame(f, bg=PANEL)
        reach.pack(fill="x", pady=(8, 0))
        v["upnp"] = tk.BooleanVar(value=bool(cfg.get("upnp")))
        self.check(reach, "Ask my router to open the node port (UPnP / NAT-PMP)", v["upnp"]).pack(anchor="w")
        tk.Label(reach, text="…or the public address you forwarded it to (ws://IP:port, or wss://name on a VPS):",
                 bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w")
        e = self.entry(reach, width=44)
        e.insert(0, cfg.get("public_url") or "")
        e.pack(anchor="w", ipady=2)
        v["public_url"] = e
        lb = tk.Frame(f, bg=PANEL)
        lb.pack(fill="x", pady=(8, 0))
        tk.Label(lb, text="Supporter leaderboard", bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w")
        n = p2p_module("node")
        choices = list(n.LEADERBOARD_CHOICES)
        v["leaderboard"] = tk.StringVar(value=dict(choices).get(cfg.get("leaderboard"), choices[1][1]))
        self._optmenu(lb, v["leaderboard"], [t for _, t in choices], width=44).pack(side="left")
        dn = self.entry(lb, width=18)
        dn.insert(0, cfg.get("display_name") or "")
        dn.pack(side="left", padx=(8, 0), ipady=2)
        v["display_name"] = dn
        b = tk.Frame(f, bg=PANEL)
        b.pack(fill="x", pady=(12, 0))
        if on or st["state"] in ("starting", "error"):
            self.wbutton(b, "Turn off", self.node_turn_off, danger=True).pack(side="left")
            if st["state"] == "error":
                self.wbutton(b, "Try again", self.node_turn_on, primary=True).pack(side="left", padx=(8, 0))
        else:
            self.wbutton(b, "Turn on…", self.node_turn_on, primary=True, icon="server").pack(side="left")
        what = tk.Label(b, text="What is shared, and who sees what?", bg=PANEL, fg=GOLD_DIM, font=font(9, "bold"),
                        cursor=self.CUR_HAND)
        what.pack(side="left", padx=(14, 0))
        what.bind("<Button-1>", lambda e: self.node_explainer(info_only=True))

    def _node_save_form(self):
        svc, v = self.p2p_node, getattr(self, "_nodev", {})
        if not svc or not v:
            return
        cfg = svc.cfg
        for key, cast in (("kbps", int), ("daily_gb", float), ("port", int)):
            try:
                if str(v[key].cget("state")) != "disabled":
                    cfg[key] = cast(v[key].get())
            except (KeyError, ValueError, tk.TclError):
                pass
        try:
            cfg["upnp"] = bool(v["upnp"].get())
            cfg["public_url"] = v["public_url"].get().strip()
            back = {t: k for k, t in p2p_module("node").LEADERBOARD_CHOICES}
            cfg["leaderboard"] = back.get(v["leaderboard"].get(), "anonymous")
            cfg["display_name"] = v["display_name"].get().strip()[:24]
        except (KeyError, tk.TclError):
            pass
        self.save_settings()

    def node_explainer(self, info_only=False):
        n, svc = p2p_module("node"), self.node_service()
        if not n or not svc:
            return None
        text = n.consent_text(svc.cfg) + "\n\n" + n.RULES
        dlg = self.p2p_dialog("BECOME A NODE", text, width=640)
        if info_only:
            dlg.buttons(("Close", dlg.close, True))
            return dlg

        def accept():
            dlg.close()
            self.notice("Starting your node…", GOLD, 5)

            def work():
                ok = svc.accept()
                self.after(0, lambda: (self.notice("Node on. Thank you! The maintainer checks new nodes for a few days."
                                                   if ok else "The node couldn't start: see HOST > Become a node.",
                                                   GREEN if ok else RED, 7), self._node_paint()))
            threading.Thread(target=work, daemon=True).start()

        def decline():
            svc.decline()
            dlg.close()
            self._node_paint()

        dlg.buttons(("Turn on my node", accept, True), ("Not now", decline, False))
        dlg.accept = accept
        return dlg

    def node_turn_on(self):
        svc = self.node_service()
        if not svc:
            return None
        self._node_save_form()
        svc.relay_enabled = self.nodes_on()
        if svc.machine.state == "error":
            threading.Thread(target=svc.accept, daemon=True).start()
            return None
        try:
            svc.enable()
        except Exception as e:   # p2p.node.NodeError: the test round isn't open yet
            self.notice(str(e), AMBER, 8)
            return None
        return self.node_explainer()

    def node_turn_off(self):
        svc = self.p2p_node
        if svc is None:
            return
        svc.turn_off()
        self.notice("Node off. Nothing is relayed, and it stays off until you turn it on again.", AMBER, 6)
        self._node_paint()

    def _node_board_fetch(self):
        b = self._node_board
        b["loading"] = True

        def get(url):
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "OpenVanilla-Launcher"})
            with urllib.request.urlopen(req, timeout=8) as r:
                out = json.loads(r.read().decode("utf-8"))
            return out if isinstance(out, dict) else {}

        def work():
            data, err = None, ""
            try:
                data = get(self.NODES_JSON_URL)
            except Exception as e:
                err = f"The supporter list can't be reached right now ({type(e).__name__})."
            try:   # the live list replaces the numbers when the directory serves it
                live = get(self.NODES_LIVE_URL)
                if isinstance(live.get("supporters"), list):
                    data = dict(data or {}, **{k: live[k] for k in ("network", "supporters", "updated", "privacy")
                                               if k in live})
                    err = ""
            except Exception:
                pass
            b.update(data=data if isinstance(data, dict) else {}, error=err, loading=False)
            try:
                self.after(0, self._node_board_paint)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _node_board_paint(self):
        f = getattr(self, "_node_board_frame", None)
        if f is None or not f.winfo_exists():
            return
        for c in f.winfo_children():
            c.destroy()
        bg = "#0d0a11"
        tk.Label(f, text="SUPPORTERS", bg=bg, fg=GOLD, font=font(11, "bold", True)).pack(anchor="w", padx=14, pady=(12, 2))
        b = self._node_board
        lb = p2p_module("leaderboard")
        data = b["data"] or {}
        net = data.get("network") or {}
        if b["loading"]:
            tk.Label(f, text="Loading…", bg=bg, fg=MUTED, font=font(9)).pack(anchor="w", padx=14)
        elif b["error"]:
            tk.Label(f, text=b["error"], bg=bg, fg=AMBER, font=font(8), wraplength=340, justify="left").pack(anchor="w", padx=14)
        if net:
            tk.Label(f, text=(f"{net.get('nodes_verified', 0)} verified nodes · {net.get('nodes_pending', 0)} being checked\n"
                              f"{net.get('relay_gb', 0)} GB relayed · {net.get('seed_gb', 0)} GB seeded (30 days)"),
                     bg=bg, fg=MUTED, font=font(8), justify="left").pack(anchor="w", padx=14, pady=(0, 6))
        rows = lb.parse(data) if lb else []
        if not rows and not b["loading"]:
            tk.Label(f, text=data.get("status") or "No supporters listed yet. Be the first!", bg=bg, fg=TEXT, font=font(9),
                     wraplength=340, justify="left").pack(anchor="w", padx=14, pady=8)
        for r in rows[:12]:
            row = tk.Frame(f, bg="#17121c", highlightthickness=1, highlightbackground="#3a2f22")
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=f"{r['rank']}.", bg="#17121c", fg=GOLD_DIM, font=font(9, "bold"), width=3).pack(side="left")
            tk.Label(row, text=r["name"], bg="#17121c", fg=TEXT, font=font(9, "bold")).pack(side="left")
            if "node" in r["badges"]:
                self._badge(row, "NODE", "shield", "#10282a", "#4fc3b0", "#17121c")
            if "seeder" in r["badges"]:
                self._badge(row, "SEEDER", "seed", "#14220f", GREEN, "#17121c")
            tk.Label(row, text=f"{r['relay_gb']:g} GB · {r['uptime_pct']}% up", bg="#17121c", fg=MUTED,
                     font=font(8)).pack(side="right", padx=6)
        tk.Label(f, text=(data.get("privacy") or "Opt-in; no IP addresses are published."), bg=bg, fg="#7d7466",
                 font=font(7), wraplength=340, justify="left").pack(side="bottom", anchor="w", padx=14, pady=(4, 10))
        link = tk.Label(f, text="Open the full list and the rules", bg=bg, fg=GOLD_DIM, font=font(9, "bold"),
                        cursor=self.CUR_HAND)
        link.pack(side="bottom", anchor="w", padx=14)
        link.bind("<Button-1>", lambda e: safe_open(self.NODES_PAGE_URL))

    # ----- Account

    def page_account(self):
        realm = self.realms[self.realm_index]
        x, y, w, h = self.big_panel("ACCOUNT", "account", f"Realm: {realm.get('name')}  ·  {realm.get('host')}:{realm.get('port', 3724)}")
        if self.session.get("user") and self.session.get("password"):
            self._account_signed_in(x, y, w, h)
        elif getattr(self, "_acct_password", False) and not getattr(self, "_discord_flow", None):
            self._account_form(x, y, w, h)
        else:
            self._account_discord(x, y, w, h)

    def _account_discord(self, x, y, w, h):
        """Not signed in: Google (in the browser) or the Hero Key (here, no browser). New or returning, the
        same buttons: Google makes the account the first time, and the launcher keeps its Hero Key."""
        flow = getattr(self, "_discord_flow", None)
        cw = 470
        self.card(x, y, cw, 330, "acct_dc", "acct_dc")
        f = self.frame_on(x + 26, y + 22, cw - 52, 296, bg=PANEL)
        if flow:
            tk.Label(f, text="FINISH IN YOUR BROWSER", bg=PANEL, fg=GOLD, font=font(13, "bold", True)).pack(anchor="w")
            tk.Label(f, text="A sign-in page opened in your browser. Finish there and you'll be signed in here "
                             "automatically.", bg=PANEL, fg=TEXT,
                     font=font(9), wraplength=cw - 60, justify="left").pack(anchor="w", pady=(8, 16))
            row = tk.Frame(f, bg=PANEL)
            row.pack(anchor="w")
            self.wbutton(row, "Open it again", lambda: safe_open(flow.url), primary=True).pack(side="left")
            self.wbutton(row, "Cancel", self.cancel_discord).pack(side="left", padx=8)
        elif getattr(self, "_hero_busy", False):
            tk.Label(f, text="SIGNING IN…", bg=PANEL, fg=GOLD, font=font(13, "bold", True)).pack(anchor="w")
            tk.Label(f, text="Checking your Hero Key with the realm.", bg=PANEL, fg=TEXT, font=font(9)).pack(anchor="w", pady=(8, 0))
        else:
            tk.Label(f, text="SIGN IN TO OPEN VANILLA", bg=PANEL, fg=GOLD, font=font(13, "bold", True)).pack(anchor="w")
            tk.Label(f, text="New or returning: Google makes your account the first time. After that, PLAY logs "
                             "you straight in.", bg=PANEL, fg=TEXT, font=font(9), wraplength=cw - 60,
                     justify="left").pack(anchor="w", pady=(6, 10))
            self.wbutton(f, "Continue with Google", lambda: self.sign_in_google(), primary=True, size=10).pack(anchor="w")
            tk.Label(f, text="HAVE A HERO KEY?", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w", pady=(16, 2))
            row = tk.Frame(f, bg=PANEL)
            row.pack(anchor="w", fill="x")
            e_key = self.entry(row, show="•", width=26)
            e_key.pack(side="left", ipady=4)
            saved = self._saved_hero_key()
            if saved:
                e_key.insert(0, saved)
            self.wbutton(row, "Sign in", lambda: self.sign_in_hero(e_key.get()), icon="key").pack(side="left", padx=(8, 0))
            e_key.bind("<Return>", lambda ev: self.sign_in_hero(e_key.get()))

            def load():
                path = filedialog.askopenfilename(parent=self, title="Your Hero Key file",
                                                  filetypes=[("Hero Key", "*.txt *.key *.ovkey"), ("All files", "*.*")])
                if not path:
                    return
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read(20000)
                except OSError as err:
                    self._set_acct_msg(f"Couldn't read that file ({err}).", RED)
                    return
                self.sign_in_hero(text)

            tk.Label(f, text=("Your saved Hero Key is filled in: press Sign in." if saved else
                              "Paste the line that starts with ovk1, or"), bg=PANEL, fg=MUTED, font=font(8)).pack(anchor="w", pady=(4, 0))
            row2 = tk.Frame(f, bg=PANEL)
            row2.pack(anchor="w", pady=(4, 0))
            self.wbutton(row2, "Load the key file", load).pack(side="left")
            if saved:
                def forget():
                    if messagebox.askyesno("Forget the Hero Key", "Forget the Hero Key saved on this PC? Keep a copy "
                                           "first if you have none: it's your account's sign-in.", parent=self):
                        self.session.pop("hero_key", None)
                        for k in ("hero_key", "hero_account"):
                            self.settings.pop(k, None)
                        self.save_settings()
                        self.show_page("account", animate=False)

                self.wbutton(row2, "Forget it on this PC", forget).pack(side="left", padx=8)
        self.acct_msg = tk.Label(f, text=getattr(self, "_acct_msg", ("", MUTED))[0], bg=PANEL,
                                 fg=getattr(self, "_acct_msg", ("", MUTED))[1], font=font(9), wraplength=cw - 60, justify="left")
        self.acct_msg.pack(anchor="w", pady=(10, 0))
        if not flow:
            self.link_text(x, y + 350, "Guest or a realm password? Sign in another way ›",
                           lambda: self._acct_mode("signin", password=True), 9)
        rx, rw = x + cw + 30, w - cw - 30
        self.card(rx, y, rw, 330, "acct_info", "acct_info")
        self.shadow_text(rx + 22, y + 28, "HOW IT WORKS", 10, GOLD)
        info = ("Google:  press Continue with Google and pick your account in the browser. The first time, the "
                "realm makes your Open Vanilla account.\n\n"
                "Hero Key:  your account's own sign-in, one line of text. The launcher keeps it for you "
                "(encrypted on this PC) and signs you in with it, no browser and no password. Keep a copy: "
                "with it you can sign in on any PC.\n\n"
                "The launcher never sees your Google password, and your Hero Key never leaves this PC: "
                "it only signs the realm's challenge.")
        self.cv.create_text(rx + 22, y + 52, anchor="nw", text=info, fill=TEXT, font=font(9), width=rw - 44, tags="page")

    def _account_form(self, x, y, w, h):
        mode = getattr(self, "acct_mode", "signin")
        # segmented tabs
        for i, (key, label) in enumerate((("signin", "SIGN IN"), ("create", "CREATE ACCOUNT"))):
            on = key == mode
            self.pill_button(x + i * 196, y, 186, 36, label, lambda k=key: self._acct_mode(k),
                             style="gold" if on else "ghost", size=9)
        fw = 420
        f = self.frame_on(x, y + 56, fw, h - 60, bg=PANEL)
        tk.Label(f, text="Account name", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
        e_user = self.entry(f, width=34)
        e_user.pack(anchor="w", ipady=5, pady=(2, 10))
        e_user.insert(0, self.settings.get("account", ""))
        tk.Label(f, text="Password", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
        e_pw = self.entry(f, show="•", width=34)
        e_pw.pack(anchor="w", ipady=5, pady=(2, 10))
        e_pw2 = None
        if mode == "create":
            tk.Label(f, text="Confirm password", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
            e_pw2 = self.entry(f, show="•", width=34)
            e_pw2.pack(anchor="w", ipady=5, pady=(2, 10))
        var_rem = tk.BooleanVar(value=self.settings.get("remember", True))
        self.check(f, "Remember me on this PC (saved encrypted)", var_rem).pack(anchor="w", pady=(0, 10))
        self.acct_msg = tk.Label(f, text=self.busy or getattr(self, "_acct_msg", ("", MUTED))[0], bg=PANEL,
                                 fg=getattr(self, "_acct_msg", ("", MUTED))[1], font=font(9), wraplength=fw - 10, justify="left")
        btns = tk.Frame(f, bg=PANEL)
        btns.pack(anchor="w", pady=(2, 8))

        def submit():
            if mode == "signin":
                self.do_sign_in(e_user.get().strip(), e_pw.get(), var_rem.get())
            else:
                self.do_create(e_user.get().strip(), e_pw.get(), e_pw2.get(), var_rem.get())

        self.wbutton(btns, "Sign in" if mode == "signin" else "Create account", submit, primary=True).pack(side="left")
        self.wbutton(btns, "Use Google instead", lambda: (self._acct_mode("signin", password=False), self.sign_in_google()),
                     ).pack(side="left", padx=8)
        self.link_text(x, y + h - 14, "Play as a guest (in your browser) ›",
                       lambda: (self._acct_mode("signin", password=False), self.sign_in_discord(via=None)), 9)
        for e in (e_user, e_pw, e_pw2):
            if e is not None:
                e.bind("<Return>", lambda ev: submit())
        self.acct_msg.pack(anchor="w")
        (e_pw if e_user.get() else e_user).focus_set()

        # right side: what this does
        rx = x + fw + 50
        rw = w - fw - 50
        self.card(rx, y + 56, rw, 250, "acct_info", "acct_info")
        self.shadow_text(rx + 22, y + 84, "HOW ACCOUNTS WORK", 10, GOLD)
        info = ("Accounts live on each realm's server. Signing in checks your name and password with the realm's "
                "login server, the same way the game does.\n\n"
                "Once you're signed in, PLAY logs you straight in and skips the login screen.\n\n"
                "Creating an account uses the realm's website, so the realm needs a website set "
                "(the Open Vanilla realm has one).")
        self.cv.create_text(rx + 22, y + 104, anchor="nw", text=info, fill=TEXT, font=font(9), width=rw - 44, tags="page")
        portal = self.realms[self.realm_index].get("portal")
        if portal:
            self.link_text(rx + 22, y + 284, "Open the realm website ›", lambda: safe_open(portal), 9)

    def sign_in_google(self, switch=False, then=None):
        self.sign_in_discord(switch=switch, then=then, via="google")

    def sign_in_auto(self, then=None):
        """The saved Hero Key when there is one (no browser), else Google."""
        key = self._saved_hero_key()
        if key:
            self.sign_in_hero(key, then=then, quiet=True)
        else:
            self.sign_in_google(then=then)

    def sign_in_discord(self, switch=False, then=None, via="google"):
        """Sign in (or sign up) in the browser (realm patch 0042: via="google" goes straight to Google,
        None to the realm's own page: guest or password): the realm hands this launcher a one-time code on
        127.0.0.1, the code buys the game account. `switch` signs the browser out first so another
        account can be picked; `then` runs after. (Named for the Discord sign-in it replaced.)"""
        flow = getattr(self, "_discord_flow", None)
        if flow:
            safe_open(flow.url)  # already waiting: just bring the page back
            return
        realm_i = self.realm_index
        portal = self.realms[realm_i].get("portal")
        if not safe_url(portal):
            self._set_acct_msg("This realm has no secure website, so it can't sign you in through it. "
                               "Use its account name and password instead.", RED)
            self.notice("This realm doesn't support browser sign-in", AMBER, 5)
            return
        try:
            flow = account.LoopbackSignIn(portal, switch=switch, via=via)
        except OSError as e:
            self._set_acct_msg(f"Couldn't start the sign-in ({e}).", RED)
            return
        self._discord_flow = flow
        self._after_sign_in = then
        self._acct_msg = ("", MUTED)
        safe_open(flow.url)
        self.notice("Finish signing in in your browser", GOLD, 6)
        self._paint_chip()
        if self.page in ("account", "play"):
            self.show_page(self.page, animate=False)

        def work():
            code = flow.wait()
            if code:
                ok, info = account.exchange_code(portal, code)
            else:
                ok, info = False, {"message": flow.error}
            self.after(0, self._discord_done, flow, ok, info, realm_i)

        threading.Thread(target=work, daemon=True).start()

    def cancel_discord(self):
        flow = getattr(self, "_discord_flow", None)
        if flow:
            flow.cancel()

    def _discord_done(self, flow, ok, info, realm_i):
        if getattr(self, "_discord_flow", None) is not flow:
            return
        self._discord_flow = None
        then, self._after_sign_in = getattr(self, "_after_sign_in", None), None
        if ok:
            self._signed_in(info, realm_i, "web")
        else:
            msg = info.get("message") or "Sign-in failed. Try again."
            if msg != "Sign-in cancelled.":
                self.notice(msg, RED, 6)
            self._acct_msg = (msg, RED if msg != "Sign-in cancelled." else MUTED)
        self._paint_chip()
        self.update_status()
        if self.page in ("account", "play"):
            self.show_page(self.page, animate=False)
        if ok and then:
            self.after(500, then)

    # ----- Hero Keys (realm patch 0042): kept by the launcher, encrypted; sign in with no browser

    def _saved_hero_key(self):
        key = self.session.get("hero_key")
        if not key and self.settings.get("hero_key"):
            key = account.unprotect(self.settings["hero_key"])
        return key or None

    def _keep_hero_key(self, key):
        key = account.parse_hero_key(key or "")
        if not key:
            return False
        self.session["hero_key"] = key
        blob = account.protect(key)
        if blob:
            self.settings["hero_key"] = blob
        else:
            self.settings.pop("hero_key", None)     # no DPAPI (not Windows): this launcher session only
        self.save_settings()
        return True

    def sign_in_hero(self, text, then=None, quiet=False):
        key = account.parse_hero_key(text or "")
        if not key:
            self._set_acct_msg("That doesn't look like a Hero Key. It starts with ovk1. Paste the whole line, "
                               "or load the key file.", RED)
            return
        realm_i = self.realm_index
        portal = self.realms[realm_i].get("portal")
        if not safe_url(portal):
            self._set_acct_msg("This realm has no secure website, so it can't take a Hero Key.", RED)
            return
        if getattr(self, "_hero_busy", False):
            return
        self._hero_busy = True
        self._set_acct_msg("Checking your Hero Key…", AMBER)
        if self.page == "account":
            self.show_page("account", animate=False)

        def work():
            ok, info = account.hero_sign_in(portal, key)
            self.after(0, self._hero_done, ok, info, realm_i, key, then, quiet)

        threading.Thread(target=work, daemon=True).start()

    def _hero_done(self, ok, info, realm_i, key, then, quiet):
        self._hero_busy = False
        if ok:
            self._signed_in(info, realm_i, "hero", hero_key=key)
        else:
            msg = info.get("message") or "That Hero Key didn't work. Try again."
            self._acct_msg = (msg, RED)
            self.notice(msg, RED, 6)
            if quiet:
                self.show_page("account", animate=False)
        self._paint_chip()
        self.update_status()
        if self.page in ("account", "play"):
            self.show_page(self.page, animate=False)
        if ok and then:
            self.after(500, then)

    def _fetch_hero_key(self, realm_i, token, replace=False):
        """After a browser sign-in: the account's first Hero Key is made for the launcher to keep. An
        account that has one already is asked to paste it (the realm never has its secret)."""
        portal = self.realms[realm_i].get("portal")
        if not safe_url(portal) or not token:
            return

        def work():
            status, body = account.launcher_herokey(portal, token, replace=replace)
            self.after(0, self._hero_key_fetched, status, body, replace)

        threading.Thread(target=work, daemon=True).start()

    def _hero_key_fetched(self, status, body, replace):
        if status == 200 and body.get("key"):
            self._keep_hero_key(body["key"])
            self.session.pop("hero_elsewhere", None)
            self.notice("New Hero Key saved in the launcher" if replace else "Your Hero Key is saved in the launcher", GREEN, 5)
        elif status == 200 and body.get("has_key"):
            self.session["hero_elsewhere"] = True
        if self.page == "account":
            self.show_page("account", animate=False)

    def _save_hero_key_copy(self):
        key = self._saved_hero_key()
        if not key:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Save a copy of your Hero Key",
                                            initialfile="Open Vanilla Hero Key.txt", defaultextension=".txt",
                                            filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(account.hero_key_file(key))
            self.notice("Hero Key saved. Keep it somewhere safe.", GREEN, 5)
        except OSError as e:
            self.notice(f"Couldn't save it ({e})", RED, 6)

    def _signed_in(self, info, realm_i, via, hero_key=None):
        """A sign-in (browser or Hero Key) succeeded: the session, remembered encrypted on this PC."""
        if True:   # (one block, as it was in the browser sign-in's handler)
            user, pw = str(info["user"]).upper(), str(info["pass"])
            display = info.get("display_name") or user.capitalize()
            self.session = dict(user=user, password=pw, realm=realm_i, verified=True, display=display, via=via)
            self.settings.update(account=user, account_display=display, account_via=via, account_realm=realm_i,
                                 remember=True)
            for key, value in (("launcher_token", info["token"]), ("saved_password", pw)):
                blob = account.protect(value)
                if blob:
                    self.settings[key] = blob
                else:
                    self.settings.pop(key, None)  # no DPAPI (not Windows): this launcher session only
            self.session["token"] = info["token"]
            self.save_settings()
            self._acct_msg = ("", MUTED)
            self._acct_password = False
            self.notice(f"Signed in as {display}", GREEN, 4)
            self._bring_to_front()
        # the Hero Key: the one just used, else the account's first one made for the launcher
        if hero_key:
            self._keep_hero_key(hero_key)
        elif not (self._saved_hero_key() and self.settings.get("hero_account") == user):
            self.session.pop("hero_key", None)
            self.settings.pop("hero_key", None)
            self._fetch_hero_key(realm_i, info["token"])
        self.settings["hero_account"] = user
        self.save_settings()

    def _bring_to_front(self):
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    def _acct_mode(self, mode, password=None):
        self.acct_mode = mode
        if password is not None:
            self._acct_password = password
        self._acct_msg = ("", MUTED)
        self.show_page("account", animate=False)

    def _account_signed_in(self, x, y, w, h):
        user = self.session["user"]
        realm_i = self.session.get("realm", self.realm_index)
        realm = self.realms[realm_i] if realm_i < len(self.realms) else self.realms[self.realm_index]
        cw = 380
        self.card(x, y, cw, 200, "profile", "profile")
        self.cv.create_image(x + 26, y + 70, anchor="w", image=self.img("prof_av", art.avatar(76, (self.session.get("display") or user)[:1])), tags="page")
        discord = self._web_session()
        self.shadow_text(x + 118, y + 52, (self.session.get("display") or user).upper()[:22], 15, GOLD)
        ver = self.session.get("verified")
        st, col = (((("Signed in with your Hero Key" if self.session.get("via") == "hero" else "Signed in with the realm's website")
                     if discord else "Verified with the login server"), GREEN) if ver else
                   ("Saved sign-in (realm not checked yet)", AMBER) if ver is None else ("Login not verified", RED))
        self.cv.create_text(x + 118, y + 80, anchor="w", text=st, fill=col, font=font(9, "bold"), tags="page")
        self.cv.create_text(x + 118, y + 100, anchor="w", text=f"Realm: {realm.get('name')}", fill=MUTED, font=font(9), tags="page")
        remembered = bool(self.settings.get("saved_password"))
        self.cv.create_text(x + 26, y + 140, anchor="w", fill=MUTED, font=font(8), tags="page",
                            text=("Remembered on this PC (encrypted)." if remembered else "Signed in for this launcher session only."))
        self.cv.create_text(x + 26, y + 158, anchor="w", fill=MUTED, font=font(8), tags="page",
                            text="PLAY will log you straight in as this account.")
        self.pill_button(x, y + 216, 180, 36, "SIGN OUT", self.sign_out, style="danger", size=9, icon="logout")
        if discord:
            self.pill_button(x + 192, y + 216, 188, 36, "SWITCH ACCOUNT", self.switch_account, style="ghost", size=9)
        if realm.get("portal"):
            self.link_text(x, y + 276, "Realm website ›", lambda: safe_open(realm["portal"]), 9)

        rx = x + cw + 30
        rw = w - cw - 30
        if discord:
            half = (rw - 20) // 2
            self._game_login_card(rx, y, half, user)
            self._hero_key_card(rx + half + 20, y, rw - half - 20)
            return

        # change password
        self.card(rx, y, rw, 290, "chpw", "chpw")
        self.shadow_text(rx + 22, y + 28, "CHANGE PASSWORD", 10, GOLD)
        f = self.frame_on(rx + 22, y + 50, 330, 230, bg=PANEL)
        entries = []
        for label in ("Current password", "New password", "Confirm new password"):
            tk.Label(f, text=label, bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
            e = self.entry(f, show="•", width=30)
            e.pack(anchor="w", ipady=4, pady=(2, 8))
            entries.append(e)
        msg = tk.Label(f, text=getattr(self, "_pw_msg", ("", MUTED))[0], bg=PANEL,
                       fg=getattr(self, "_pw_msg", ("", MUTED))[1], font=font(9), wraplength=rw - 60, justify="left")
        self.wbutton(f, "Change password", lambda: self.do_change_password(*(e.get() for e in entries)), primary=True).pack(anchor="w")
        msg.pack(anchor="w", pady=(6, 0))
        self.pw_msg_label = msg

    def _game_login_card(self, rx, y, rw, user):
        """A Discord account's game login: PLAY uses it automatically; the stock 1.12 client needs it typed."""
        self.card(rx, y, rw, 290, "gamelogin", "gamelogin")
        self.shadow_text(rx + 22, y + 28, "YOUR GAME LOGIN", 10, GOLD)
        f = self.frame_on(rx + 22, y + 50, rw - 44, 230, bg=PANEL)
        tk.Label(f, text="PLAY signs you in automatically. Only the stock Vanilla client asks for these — "
                         "PLAY copies the password for you to paste on its login screen.",
                 bg=PANEL, fg=MUTED, font=font(9), wraplength=rw - 60, justify="left").pack(anchor="w", pady=(0, 12))
        tk.Label(f, text="Account name", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
        tk.Label(f, text=user, bg=PANEL, fg=TEXT, font=font(12, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(f, text="Password", bg=PANEL, fg=TAN, font=font(9, "bold")).pack(anchor="w")
        shown = getattr(self, "_show_game_pw", False)
        pw = self.session.get("password", "")
        tk.Label(f, text=pw if shown else "•" * len(pw), bg=PANEL, fg=TEXT, font=font(12, "bold")).pack(anchor="w")
        row = tk.Frame(f, bg=PANEL)
        row.pack(anchor="w", pady=(10, 0))

        def toggle():
            self._show_game_pw = not shown
            self.show_page("account", animate=False)

        def copy():
            self.clipboard_clear()
            self.clipboard_append(pw)
            self.notice("Game password copied", GREEN)

        self.wbutton(row, "Hide" if shown else "Show", toggle).pack(side="left")
        self.wbutton(row, "Copy password", copy, primary=True).pack(side="left", padx=8)

    def _web_session(self):
        """Signed in through the realm's website (Google, guest, the Hero Key; "discord" before 0042)."""
        return self.session.get("via") in ("discord", "web", "hero") or bool(self.session.get("token"))

    def _hero_key_card(self, rx, y, rw):
        """The account's Hero Key, kept by the launcher: copy it out, or paste the one you have."""
        self.card(rx, y, rw, 290, "herokey", "herokey")
        self.shadow_text(rx + 22, y + 28, "YOUR HERO KEY", 10, GOLD)
        f = self.frame_on(rx + 22, y + 50, rw - 44, 230, bg=PANEL)
        key = self._saved_hero_key()
        if key:
            tk.Label(f, text="Saved in this launcher (encrypted). It signs you in here with no browser and no "
                             "password. Keep a copy: with it you can sign in on any PC.",
                     bg=PANEL, fg=MUTED, font=font(9), wraplength=rw - 60, justify="left").pack(anchor="w", pady=(0, 10))
            tk.Label(f, text=key[:15] + "…", bg=PANEL, fg=TEXT, font=font(11, "bold")).pack(anchor="w", pady=(0, 10))

            def copy():
                self.clipboard_clear()
                self.clipboard_append(key)
                self.notice("Hero Key copied. Keep it private.", GREEN)

            row = tk.Frame(f, bg=PANEL)
            row.pack(anchor="w")
            self.wbutton(row, "Save a copy", self._save_hero_key_copy, primary=True, icon="key").pack(side="left")
            self.wbutton(row, "Copy", copy).pack(side="left", padx=8)
            return
        if self.session.get("hero_elsewhere"):
            tk.Label(f, text="Your account has a Hero Key already. Paste it here once and the launcher keeps it.",
                     bg=PANEL, fg=MUTED, font=font(9), wraplength=rw - 60, justify="left").pack(anchor="w", pady=(0, 8))
            e = self.entry(f, show="•", width=26)
            e.pack(anchor="w", ipady=4, pady=(0, 8))

            def keep():
                if self._keep_hero_key(e.get()):
                    self.session.pop("hero_elsewhere", None)
                    self.notice("Hero Key saved in the launcher", GREEN)
                    self.show_page("account", animate=False)
                else:
                    self.notice("That doesn't look like a Hero Key (it starts with ovk1)", RED)

            row = tk.Frame(f, bg=PANEL)
            row.pack(anchor="w")
            self.wbutton(row, "Keep it", keep, primary=True, icon="key").pack(side="left")

            def renew():
                if messagebox.askyesno("A new Hero Key", "Make a new Hero Key? Your old one stops working at once, "
                                       "everywhere.", parent=self):
                    self._fetch_hero_key(self.session.get("realm", self.realm_index), self.session.get("token"), replace=True)

            self.wbutton(row, "Lost it? New key", renew).pack(side="left", padx=8)
            return
        tk.Label(f, text="Getting your Hero Key from the realm…" if self.session.get("token") else
                 "Sign in with Google once and the launcher keeps your Hero Key.",
                 bg=PANEL, fg=MUTED, font=font(9), wraplength=rw - 60, justify="left").pack(anchor="w")

    def switch_account(self):
        """Sign out here and in the browser, then pick another Google account."""
        self._sign_out_quietly()
        self.sign_in_google(switch=True)

    # ----- account actions (network on worker threads)

    def _account_realm(self):
        r = self.realms[self.realm_index]
        return r["host"], int(r.get("port", 3724)), r.get("portal")

    def _set_acct_msg(self, text, color=MUTED):
        self._acct_msg = (text, color)
        lbl = getattr(self, "acct_msg", None)
        try:
            if lbl is not None and lbl.winfo_exists():
                lbl.config(text=text, fg=color)
        except tk.TclError:
            pass

    def do_sign_in(self, user, pw, remember, quiet=False):
        err = account.check_username(user) or (None if pw else "Enter your password.")
        if err:
            self._set_acct_msg(err, RED)
            return
        host, port, _ = self._account_realm()
        self._set_acct_msg("Checking with the login server…", AMBER)
        realm_i = self.realm_index

        def work():
            ok, msg = account.verify_login(user, pw, host, port)
            self.after(0, self._sign_in_done, user, pw, remember, ok, msg, realm_i, quiet)

        threading.Thread(target=work, daemon=True).start()

    def _sign_in_done(self, user, pw, remember, ok, msg, realm_i, quiet):
        if ok:
            self.session = dict(user=user.upper(), password=pw, realm=realm_i, verified=True)
            self.settings["account"] = user.upper()
            self.settings["remember"] = bool(remember)
            self.settings["account_realm"] = realm_i
            blob = account.protect(pw) if remember else None
            if blob:
                self.settings["saved_password"] = blob
            else:
                self.settings.pop("saved_password", None)
            self.save_settings()
            self._acct_msg = ("", MUTED)
            self.notice(f"Signed in as {user.upper()}", GREEN)
        else:
            self._set_acct_msg(msg, RED)
            return
        self._paint_chip()
        self.update_status()
        if self.page in ("account", "play"):
            self.show_page(self.page, animate=False)

    def portal_ok(self, portal):
        """Passwords only go to https sites (or this PC), and to a community server only after the player agrees."""
        if not safe_url(portal):
            messagebox.showerror("Not a secure website", "This server's website isn't https, so Open Vanilla won't send your "
                                 "password to it. Ask the server owner to set up https.", parent=self)
            return False
        host = urllib.parse.urlsplit(portal).hostname or ""
        official = {urllib.parse.urlsplit(r.get("portal") or "").hostname for r in self.defaults.get("realms", [])}
        trusted = self.settings.setdefault("trusted_portals", [])
        if host in LOCAL_HOSTS or host in official or host in trusted:
            return True
        if not self.settings.get("confirm_portals", True):
            return True
        if not messagebox.askyesno("Send your password to this server?",
                                   f"Your account name and password will be sent to {host}, which is run by the "
                                   "server's owner, not Open Vanilla.\n\nOnly continue if you trust this server. "
                                   "Use a password you don't use anywhere else.", parent=self):
            return False
        trusted.append(host)
        self.save_settings()
        return True

    def do_create(self, user, pw, pw2, remember):
        err = account.check_username(user) or account.check_password(pw) or (None if pw == pw2 else "The passwords don't match.")
        if err:
            self._set_acct_msg(err, RED)
            return
        host, port, portal = self._account_realm()
        if not portal:
            self._set_acct_msg("This realm has no website set, so accounts can't be created from here. "
                               "Ask the realm owner, or add the website URL on the Realms page.", RED)
            return
        if not self.portal_ok(portal):
            return
        self._set_acct_msg("Creating your account…", AMBER)
        realm_i = self.realm_index

        def work():
            ok, msg = account.register(portal, user, pw)
            if ok:
                vok, vmsg = account.verify_login(user, pw, host, port)
                self.after(0, self._sign_in_done, user, pw, remember, vok if vok is not None else True,
                           vmsg, realm_i, False)
                self.after(0, self.notice, msg, GREEN)
            else:
                self.after(0, self._set_acct_msg, msg, RED)

        threading.Thread(target=work, daemon=True).start()

    def do_change_password(self, old, new, new2):
        def say(text, color):
            self._pw_msg = (text, color)
            try:
                self.pw_msg_label.config(text=text, fg=color)
            except (tk.TclError, AttributeError):
                pass

        err = account.check_password(new) or (None if new == new2 else "The new passwords don't match.")
        if not old:
            err = "Enter your current password."
        if err:
            say(err, RED)
            return
        r = self.realms[self.session.get("realm", self.realm_index)]
        if not r.get("portal"):
            say("This realm has no website set, so the password can't be changed from here.", RED)
            return
        if not self.portal_ok(r["portal"]):
            return
        say("Changing password…", AMBER)
        user = self.session["user"]

        def work():
            ok, msg = account.change_password(r["portal"], user, old, new)
            self.after(0, done, ok, msg)

        def done(ok, msg):
            if ok:
                self.session["password"] = new
                if self.settings.get("saved_password"):
                    blob = account.protect(new)
                    if blob:
                        self.settings["saved_password"] = blob
                    self.save_settings()
                self._pw_msg = ("", MUTED)
                self.notice("Password changed", GREEN)
                self.show_page("account", animate=False)
            else:
                say(msg, RED)

        threading.Thread(target=work, daemon=True).start()

    def _sign_out_quietly(self):
        token = self.session.get("token")
        portal = self.realms[self.session.get("realm", self.realm_index)].get("portal") if self.session else None
        if token and portal:
            threading.Thread(target=account.launcher_signout, args=(portal, token), daemon=True).start()
        self.session = {}
        for key in ("saved_password", "launcher_token", "account_via", "account_display"):
            self.settings.pop(key, None)
        self.save_settings()

    def sign_out(self):
        self._sign_out_quietly()
        self._paint_chip()
        self.update_status()
        self.notice("Signed out")
        self.show_page("account", animate=False)

    def _restore_session(self):
        token = account.unprotect(self.settings.get("launcher_token")) if self.settings.get("launcher_token") else None
        if token:
            realm_i = int(self.settings.get("account_realm", self.realm_index))
            realm_i = realm_i if realm_i < len(self.realms) else self.realm_index
            portal = self.realms[realm_i].get("portal")
            pw = account.unprotect(self.settings.get("saved_password"))
            # Shown as signed in at once (offline play still works); the realm confirms in the background.
            self.session = dict(user=self.settings.get("account", ""), password=pw or "", realm=realm_i, verified=None,
                                display=self.settings.get("account_display"), via=self.settings.get("account_via") or "web",
                                token=token)

            def work():
                status, info = account.launcher_me(portal, token)
                self.after(0, self._launcher_me_done, status, info)

            threading.Thread(target=work, daemon=True).start()
            self._paint_chip()
            return
        user = self.settings.get("account")
        pw = account.unprotect(self.settings.get("saved_password")) if self.settings.get("remember", True) else None
        if user and pw:
            realm_i = int(self.settings.get("account_realm", self.realm_index))
            realm_i = realm_i if realm_i < len(self.realms) else self.realm_index
            self.session = dict(user=user, password=pw, realm=realm_i, verified=None)
            r = self.realms[realm_i]

            def work():
                ok, _ = account.verify_login(user, pw, r["host"], int(r.get("port", 3724)))
                self.after(0, self._restore_done, ok)

            threading.Thread(target=work, daemon=True).start()
        self._paint_chip()

    def _launcher_me_done(self, status, info):
        if not self.session.get("token"):
            return
        if status == 200:
            self.session.update(user=str(info["user"]).upper(), password=str(info["pass"]), verified=True,
                                display=info.get("display_name") or self.session.get("display"))
            self.settings.update(account=self.session["user"], account_display=self.session["display"])
            blob = account.protect(self.session["password"])
            if blob:
                self.settings["saved_password"] = blob
            self.save_settings()
        elif status in (401, 403):
            self._sign_out_quietly()
            self._acct_msg = (info.get("message") or "Your sign-in ended. Sign in again.", AMBER)
            if self._saved_hero_key():
                self.sign_in_hero(self._saved_hero_key(), quiet=True)   # the kept Hero Key signs in again
        # 0 = the realm is unreachable: stay signed in on the saved login (verified stays None)
        self._paint_chip()
        self.update_status()
        if self.page in ("play", "account"):
            self.show_page(self.page, animate=False)

    def _restore_done(self, ok):
        if not self.session:
            return
        if ok is False:
            # The saved password no longer works (changed on the website?): keep the name, drop the password.
            self.session = {}
            self.settings.pop("saved_password", None)
            self.save_settings()
            self._acct_msg = ("Your saved password didn't work any more. Please sign in again.", AMBER)
        else:
            self.session["verified"] = ok
        self._paint_chip()
        self.update_status()
        if self.page in ("play", "account"):
            self.show_page(self.page, animate=False)

    # ----- Settings

    def page_settings(self):
        x, y, w, h = self.big_panel("SETTINGS", "settings", f"Launcher {self.version}")
        inner = self._scroll_list(x, y, w, h - 42)
        bgc = PANEL

        def section(title):
            tk.Label(inner, text=title, bg=bgc, fg=GOLD, font=font(11, "bold", True)).pack(anchor="w", pady=(10, 4))

        adv = self.advanced()
        section("GAME CLIENTS")
        tk.Label(inner, text="PLAY (Online and Solo) starts the game below. OpenVanilla.exe starts it for you: there's no "
                             "need to run the game's own exe." + (" Paste a download link for any client and the "
                             "launcher offers it to players who don't have it." if adv else ""), bg=bgc, fg=MUTED,
                 font=font(8), wraplength=w - 40, justify="left").pack(anchor="w", pady=(0, 6))
        for i, c in enumerate(self.clients):
            row = self.list_row(inner)
            top = tk.Frame(row, bg="#17121c")
            top.pack(fill="x", padx=12, pady=(8, 2))
            tk.Label(top, text=c["name"], bg="#17121c", fg=GOLD if i == self.client_index else TEXT, font=font(10, "bold")).pack(side="left")
            self.chip(top, c.get("version", "")).pack(side="left", padx=8)
            exe = self.client_exe(c)
            state = ("plays in the browser" if c["type"] == "web" else ("installed" if exe else "not installed"))
            tk.Label(top, text=state, bg="#17121c", fg=GREEN if exe else AMBER, font=font(8, "bold")).pack(side="left")
            if c["type"] == "web":
                self.var_webfs = tk.BooleanVar(value=self.settings.get("web_fullscreen", True))
                self.check(row, "Open the browser window fullscreen (F11 leaves it)", self.var_webfs, self._save_web_fullscreen).pack(anchor="w", padx=12, pady=(0, 8))
                continue
            line = tk.Frame(row, bg="#17121c")
            line.pack(fill="x", padx=12, pady=2)
            where = exe if exe else (c.get("path") or "Not set")
            tk.Label(line, text="Location", bg="#17121c", fg=MUTED, font=font(8), width=10, anchor="w").pack(side="left")
            tk.Label(line, text=where, bg="#17121c", fg=TEXT if exe else MUTED, font=font(8), anchor="w").pack(side="left", fill="x", expand=True)
            self.wbutton(line, "Browse…", lambda c=c: self.pick_client_path(c)).pack(side="right")
            if not adv:   # the download link is a developer control (Advanced)
                tk.Frame(row, bg="#17121c", height=8).pack()
                continue
            line2 = tk.Frame(row, bg="#17121c")
            line2.pack(fill="x", padx=12, pady=(2, 10))
            tk.Label(line2, text="Download", bg="#17121c", fg=MUTED, font=font(8), width=10, anchor="w").pack(side="left")
            e = self.entry(line2, width=70)
            e.config(font=font(9))
            e.insert(0, c.get("download_url", ""))
            e.pack(side="left", ipady=2, fill="x", expand=True)
            e.bind("<FocusOut>", lambda ev, c=c, e=e: self.set_client_link(c, e.get()))
            e.bind("<Return>", lambda ev, c=c, e=e: self.set_client_link(c, e.get()))
            self.wbutton(line2, "Save", lambda c=c, e=e: self.set_client_link(c, e.get())).pack(side="left", padx=6)

        section("VANILLA CLIENT V1.3 GAME DATA  (for the Open Vanilla desktop client)")
        wow = self.settings.get("wow_folder", "")
        data = wow_data_dir(wow)
        line = tk.Frame(inner, bg=bgc)
        line.pack(fill="x")
        tk.Label(line, text=wow or "Not set", bg=bgc, fg=TEXT if data else RED, font=font(9), anchor="w").pack(side="left", fill="x", expand=True)
        self.wbutton(line, "Browse…", self.pick_wow_folder).pack(side="right")
        tk.Label(inner, text="Your own English Vanilla Client v1.3 (build 5875). Open Vanilla reads its Data folder and never writes to it."
                             + ("" if not wow or data else "  ⚠ no .MPQ files found there"),
                 bg=bgc, fg=MUTED, font=font(8)).pack(anchor="w")

        section("LAUNCHER")
        self.var_anim = tk.BooleanVar(value=self.settings.get("animated_background", True))
        self.var_fx = tk.BooleanVar(value=self.settings.get("effects", True))
        self.var_close = tk.BooleanVar(value=self.settings.get("close_on_play", False))
        self.var_sound = tk.BooleanVar(value=self.settings.get("mute_game", False))
        self.var_native = tk.BooleanVar(value=self.settings.get("native_titlebar", False))
        for text, var in (("Animated background", self.var_anim), ("Particles and animations", self.var_fx),
                          ("Close the launcher when the game starts", self.var_close), ("Start the game muted", self.var_sound),
                          ("Use the Windows title bar (takes effect next start)", self.var_native)):
            self.check(inner, text, var, self.save_toggles).pack(anchor="w", pady=1)
        self.var_auto = tk.BooleanVar(value=self.settings.get("auto_update", True))
        self.check(inner, "Download launcher updates in the background (you choose when to restart)", self.var_auto,
                   self.save_toggles).pack(anchor="w", pady=1)
        self.var_adv = tk.BooleanVar(value=adv)
        self.check(inner, "Advanced: show developer controls (client download links, GitHub search, Downloads tab)",
                   self.var_adv, self._set_advanced).pack(anchor="w", pady=1)

        def toggle(text, key, default=True):
            var = tk.BooleanVar(value=self.settings.get(key, default))
            self._setting_vars[key] = var
            self.check(inner, text, var, lambda: self._save_flag(key, var.get())).pack(anchor="w", pady=1)

        def note(text):
            tk.Label(inner, text=text, bg=bgc, fg=MUTED, font=font(8), wraplength=w - 40, justify="left").pack(anchor="w", pady=(0, 4))

        def buttons(*items):
            row = tk.Frame(inner, bg=bgc)
            row.pack(anchor="w", pady=(4, 2))
            for label, cmd in items:
                self.wbutton(row, label, cmd).pack(side="left", padx=(0, 6))

        self._setting_vars = {}
        section("FOLDERS")
        note(("Portable: everything lives beside OpenVanilla.exe." if LAYOUT.portable else
              "Installed: your files live in your user folder, so reinstalling never touches them.")
             + f"  {LAYOUT.data}")
        for label, folder, what in self.folder_shortcuts():
            row = tk.Frame(inner, bg=bgc)
            row.pack(fill="x", pady=1)
            self.wbutton(row, label, lambda f=folder: self.open_path(f), icon="folder", size=8).pack(side="left")
            tk.Label(row, text=what, bg=bgc, fg=MUTED, font=font(8)).pack(side="left", padx=8)

        section("DOWNLOADS")
        note("Vanilla Client v1.3 isn't downloaded inside the launcher: GET THE GAME opens its page in your browser. "
             "Other downloads can be cancelled from the loading bar and resume where they stopped.")

        section("ACCOUNT & SECURITY")
        toggle("Remember my password on this PC (encrypted for your Windows account)", "remember")
        toggle("Ask before sending my password to a community server", "confirm_portals")
        note("Passwords are only ever sent to https websites (or a server on this PC). Open Vanilla never sees your password; "
             "each realm checks it itself.")
        buttons(("Forget saved password", self._forget_password),
                (f"Forget trusted servers ({len(self.settings.get('trusted_portals', []))})", self._forget_trusted))

        section("PRIVACY")
        toggle("Load the community directory (servers, mods, projects) from the Open Vanilla website", "load_directory")
        toggle("Ping community servers while the Servers page is open (shows their ping)", "ping_servers")
        if nowplaying:
            toggle("Share what I'm listening to (title and artist on your Persona profile)", "share_listening", default=False)
            note("Off by default. Reads the song Windows is playing (needs the optional 'winsdk' package) or your "
                 "linked Spotify, every 10 seconds; only the title and artist are shared, with players who look "
                 "at your profile. The desktop game picks it up when your character enters the world.")
            buttons(("Unlink Spotify", self._unlink_spotify) if self.settings.get("spotify") else ("Link Spotify…", self._link_spotify))
        note("The launcher sends no analytics or crash reports. It contacts: the Open Vanilla website on GitHub Pages "
             "(updates, news, directory), the realm you pick (login and ping), GitHub when you search it, and the "
             "download site of anything you choose to download. Settings stay on this PC.")
        buttons(("Privacy policy", lambda: self._open_site_page("privacy.html")),
                ("Clear all local data…", self._clear_local_data))

        if ai_setup and ai_setup.enabled(self.live):   # Settings > AI (live.json flag "ai" can hide it)
            ai_setup.settings_section(self, inner, LAYOUT.data, section, note, buttons, w)

        section("ABOUT")
        note(f"Open Vanilla Launcher {self.version} · an independent, open-source fan project. World of Warcraft is a "
             "trademark of Blizzard Entertainment, Inc.; Open Vanilla is not affiliated with or endorsed by Blizzard. "
             "The engine is built on benilla (MIT / Apache-2.0); Play Solo uses SPP Classics (CMaNGOS); the display "
             "font is Cinzel (SIL OFL). Open Vanilla ships no Blizzard game files.")
        buttons(("Terms", lambda: self._open_site_page("terms.html")),
                ("Security", lambda: self._open_site_page("security.html")),
                ("Source code", lambda: safe_open(self.community_links().get("github"))),
                ("Report a bug", lambda: safe_open(self.community_links().get("bug_reports"))))

        foot = self.frame_on(x, y + h - 36, w, 34, bg=PANEL)
        self.wbutton(foot, "Open AddOns", lambda: self.open_path(ADDONS_DIR)).pack(side="left")
        self.wbutton(foot, "Open screenshots", lambda: self.open_path(self.screenshots_dir())).pack(side="left", padx=6)
        self.wbutton(foot, "Open logs", lambda: self.open_path(LAYOUT.logs)).pack(side="left")
        legal = tk.Label(foot, text="Privacy & legal", bg=PANEL, fg=GOLD_DIM, font=font(8, "bold"), cursor="hand2")
        legal.pack(side="right")
        legal.bind("<Button-1>", lambda e: self._open_site_page("privacy.html"))
        tk.Label(foot, text=f"Launcher {self.version}  ·", bg=PANEL, fg=MUTED, font=font(8)).pack(side="right", padx=4)

    def folder_shortcuts(self):
        """(button, folder, what it holds) for Settings > Folders: the layout 2 user folders."""
        return [("AddOns", ADDONS_DIR, "Addons every client loads (AddOns\\Enabled; switched-off ones sit in AddOns\\Disabled)"),
                ("Screenshots", self.screenshots_dir(), "Your in-game screenshots"),
                ("Logs", LAYOUT.logs, "Launcher, update and server logs (attach them to bug reports)"),
                ("Realms", LAYOUT.realms, "Solo (SPP Classics)"),
                ("Backups", LAYOUT.backups, "Character backups and anything an update moved aside"),
                ("Install folder", INSTALL_DIR, "OpenVanilla.exe, app\\, Game\\ and Server\\ (program files)")]

    def screenshots_dir(self):
        """Screenshots\\, unless only the game's own folder has any yet (the engine's, or WoW 1.12.1's)."""
        cands = [LAYOUT.screenshots, os.path.join(CONFIG_DIR, "Screenshots")]
        if self.settings.get("wow_folder"):
            cands.append(os.path.join(self.settings["wow_folder"], "Screenshots"))
        for d in cands:
            try:
                if os.listdir(d):
                    return d
            except OSError:
                continue
        return LAYOUT.screenshots

    def _set_advanced(self):
        self.settings["advanced"] = bool(self.var_adv.get())
        self.save_settings()
        self.show_page("settings", animate=False)

    def _client_override(self, c, key, value):
        ov = self.settings.setdefault("clients", {}).setdefault(c["id"], {})
        if value:
            ov[key] = value
            c[key] = value
        else:
            ov.pop(key, None)
            base = next((d for d in self.defaults.get("clients", []) if d.get("id") == c["id"]), {})
            if base.get(key):
                c[key] = base[key]
            else:
                c.pop(key, None)
        self.save_settings()

    def set_client_link(self, c, url):
        url = url.strip()
        if url == (c.get("download_url") or ""):
            return
        if url and not url.lower().startswith(("http://", "https://")):
            self.notice("Download links must start with http:// or https://", RED, 4)
            return
        self._client_override(c, "download_url", url)
        self.notice(f"Saved the download link for {c['name']}", GREEN)
        self.update_status()

    def pick_client_path(self, c):
        if c["type"] == "engine":
            path = filedialog.askopenfilename(parent=self, title="Choose the Open Vanilla engine (Open Vanilla Game.exe)", filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
        else:
            path = filedialog.askdirectory(parent=self, title=f"Choose the {c['name']} folder (the one with Wow.exe)")
        if not path:
            return
        self._client_override(c, "path", path)
        if not self.client_exe(c):
            messagebox.showwarning("Game client", f"{c.get('exe', 'Wow.exe')} wasn't found there. Pick the folder that contains it.", parent=self)
        self.update_status()
        self.show_page("settings", animate=False)

    def _save_web_fullscreen(self):
        self.settings["web_fullscreen"] = self.var_webfs.get()
        self.save_settings()

    def pick_wow_folder(self):
        while True:
            path = filedialog.askdirectory(parent=self, title="Choose your game's Data folder")
            if not path:
                return
            issues = wow_problems(path)
            if not issues:
                break
            if not messagebox.askretrycancel("That folder won't work", "\n".join(issues) + "\n\nPick a different folder?",
                                             parent=self):
                return
        self.settings["wow_folder"] = path
        self._wow_issues = []
        self.save_settings()
        self.update_status()
        self.show_page("settings", animate=False)

    def _save_flag(self, key, value):
        self.settings[key] = bool(value)
        self.save_settings()

    def _open_site_page(self, page):
        base = (self.community_links().get("portal") or "https://openvanilla.app/").rstrip("/")
        safe_open(f"{base}/{page}")

    def _forget_password(self):
        self.settings.pop("saved_password", None)
        self.save_settings()
        self.notice("Saved password removed from this PC.", GREEN)

    def _forget_trusted(self):
        self.settings["trusted_portals"] = []
        self.save_settings()
        self.notice("Community servers will ask again before you send them a password.", GREEN)
        self.show_page("settings", animate=False)

    def _clear_local_data(self):
        if not messagebox.askyesno("Clear all local data?",
                                   "This removes your launcher settings, saved login, added servers and trusted servers "
                                   "from this PC, then closes the launcher. Your game files are not touched.", parent=self):
            return
        if self.busy_download():
            self.cancel_download(ask=False)
        try:
            os.remove(SETTINGS_PATH)
        except FileNotFoundError:
            pass
        except OSError as e:
            self.notice(f"Couldn't remove settings: {e}"[:110], RED, 6)
            return
        self.save_settings = lambda: None  # don't write them back on the way out
        self.destroy()

    def save_toggles(self):
        self.settings["animated_background"] = self.var_anim.get()
        self.settings["effects"] = self.var_fx.get()
        self.settings["close_on_play"] = self.var_close.get()
        self.settings["mute_game"] = self.var_sound.get()
        self.settings["native_titlebar"] = self.var_native.get()
        self.settings["auto_update"] = self.var_auto.get()
        self.save_settings()

    def save_settings(self):
        self.settings["realm_index"] = self.realm_index
        self.settings["realm_host"] = (self.realms[self.realm_index] or {}).get("host", "") if self.realms else ""
        try:
            write_json(SETTINGS_PATH, self.settings)
        except OSError as e:
            messagebox.showerror("Settings", f"Could not save settings:\n{e}", parent=self)

    # ----- Help

    def page_support(self):
        """The tip jar: same words and art as the website's, with the two links from links.txt."""
        x, y, w, h = self.big_panel("SUPPORT THE REALM", "heart")
        comm = self.community_links()
        lw = 470
        # left: the jar art, framed, and what supporters get under it
        jar = os.path.join(ASSETS, "support_jar.webp")
        try:
            im = Image.open(jar).convert("RGBA")
            ih = round(im.height * lw / im.width)
            im = im.resize((lw, ih), Image.Resampling.LANCZOS)
            mask = Image.new("L", im.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, lw - 1, ih - 1], radius=12, fill=255)
            im.putalpha(mask)
            ImageDraw.Draw(im).rounded_rectangle([0, 0, lw - 1, ih - 1], radius=12, outline=(150, 116, 52, 255), width=2)
            self.cv.create_image(x, y, anchor="nw", image=self.img("support_jar", im), tags="page")
        except OSError:
            ih = 0
        py = y + ih + 18
        self.shadow_text(x, py, "WHAT SUPPORTERS GET", 10, GOLD)
        perks = ("A Supporter role in the Discord, and your name on the supporters wall if you'd like",
                 "A vote on what gets built next",
                 "Community goals unlock rewards for everyone when they're met")
        py += 22
        for p in perks:
            self.cv.create_text(x + 4, py, anchor="nw", text="\u2022", fill=GOLD_DIM, font=font(10, "bold"), tags="page")
            t = self.cv.create_text(x + 20, py, anchor="nw", text=p, fill=TEXT, font=font(9), width=lw - 24, tags="page")
            bb = self.cv.bbox(t)
            py = (bb[3] if bb else py + 18) + 6

        # right: the pitch and the two tip buttons
        rx, rw = x + lw + 40, w - lw - 40
        self.cv.create_image(rx, y + 16, anchor="w", image=self.img("support_title", art.emboss_text("Keep the realm running", 22, "#f3d179")),
                             tags="page")
        body = ("Open Vanilla is free and built by volunteers. Tips pay for hosting first, then fixes and new features, "
                "and every one gets a public receipt from Orion.")
        t = self.cv.create_text(rx, y + 44, anchor="nw", text=body, fill=TEXT, font=font(10), width=rw, tags="page")
        bb = self.cv.bbox(t)
        by = (bb[3] if bb else y + 100) + 22
        card = safe_url(comm.get("donate_card") or "https://ko-fi.com/orionvanilla")

        def tip(url):
            if not safe_open(url or ""):
                self.notice("Tips open at launch; nothing is charged until then.", GOLD, 4.0)

        self.pill_button(rx, by, rw, 40, "TIP ON KO-FI", lambda: tip(card), style="gold", size=10, icon="heart")
        self.cv.create_text(rx + rw // 2, by + 54, text="Card or PayPal \u00b7 one-time or monthly", fill=MUTED, font=font(8), tags="page")
        by += 84
        self.cv.create_line(rx + 30, by, rx + rw - 30, by, fill="#4a3b22", tags="page")
        fine = ("Tips never buy power, items or game time." if card else
                "Tips open at launch; nothing is charged until then. Tips never buy power, items or game time.")
        self.cv.create_text(rx + rw // 2, by + 14, anchor="n", text=fine, fill=MUTED, font=font(8), width=rw, justify="center", tags="page")
        portal = comm.get("portal")
        if portal:
            self.link_text(rx + rw // 2, by + 56, "See where the money goes \u2192", lambda: safe_open(portal), size=9, anchor="center")

    def page_help(self):
        x, y, w, h = self.big_panel("HELP", "help")
        cols = [
            ("PLAYING", "1.  Pick how to play in the switch at the bottom left: ONLINE (a realm), SOLO (your own world "
                        "on this PC, with bots) or BROWSER.\n"
                        "2.  Online: pick a realm in the left rail or on the Realms tab; Account signs you in.\n"
                        "3.  Press PLAY. If something's missing, the bar above PLAY says what, and PLAY fixes it.\n"
                        "OpenVanilla.exe starts the game for you: never run Game\\Open Vanilla Game.exe directly."),
            ("PLAY SOLO", "The first SOLO press downloads SPP Classics into Realms\\Solo (progress in the bar) and opens "
                          "SPP's setup window once: type 1, wait, then 0. After that PLAY starts the servers hidden, "
                          "starts the game and logs you in as SOLO / SOLO; closing the game saves and stops everything."),
            ("HOSTING", "Running your own realm is a separate download, Open Vanilla Server (openvanilla.app/host.html): "
                        "an always-on SPP realm with its website, Server Studio and GM tools. Friends join it from "
                        "REALMS → Add realm with your address."),
            ("FOLDERS & UPDATES", "Addons live in AddOns\\Enabled and work in every client; Settings → Folders opens "
                                  "AddOns, Screenshots, Logs and Realms. Updates download quietly: press UPDATE READY to "
                                  "restart into them. News and links refresh by themselves."),
        ]
        cw = (w - 20) // 2
        for i, (title, body) in enumerate(cols):
            cx = x + (i % 2) * (cw + 20)
            cy = y + (i // 2) * 210
            self.card(cx, cy, cw, 196, title, f"help{i}")
            self.shadow_text(cx + 22, cy + 26, title, 10, GOLD)
            self.cv.create_text(cx + 22, cy + 48, anchor="nw", text=body, fill=TEXT, font=font(9), width=cw - 44, tags="page")

    # ----- helpers

    def open_path(self, path):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])        # Finder (xdg-open doesn't exist on macOS)
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", path])
        else:
            self.notice(f"Folder: {path}", GOLD, 8)

    def notice(self, text, color=GOLD, seconds=3.0):
        self._notice = (text, color, time.time() + seconds)
        self.update_status()

    # ================================================================ status bar & PLAY

    def readiness(self):
        """(ok, headline, detail, style, action) for the energy bar and PLAY, for the selected client."""
        mode = self.play_mode()
        if mode == "solo":
            return self.solo_readiness()
        c = self.client()
        realm = self.realms[self.realm_index]
        st = self.realm_state.get(self.realm_index)
        name = c["name"].upper()
        if c["type"] == "web" or mode == "browser":
            if not self.web_url():
                return False, "THIS SERVER HAS NO WEBSITE", "Pick a server with a website for browser play, or another client.", "red", "servers"
            return True, "READY · PLAYS IN YOUR BROWSER", f"{realm.get('name')} · {self.web_url()}", "blue", None
        if not self.client_exe(c):
            url = self.client_download(c)
            if url:
                if c["type"] == "exe":  # a stock client: the player points us at their own install
                    return False, f"SET UP {name}", "Press PLAY to get Vanilla Client v1.3 or pick your game's Data folder.", "amber", "choose_install"
                if is_file_link(url):
                    return False, f"GET {name}", "Click here to download it, or set its folder in Settings → Game clients.", "amber", "download_client"
                return False, f"SET UP {name}", "Click here for how to get it, or set its folder in Settings → Game clients.", "amber", "download_client"
            if c["type"] == "exe":
                return False, f"SET UP {name}", "Press PLAY to get Vanilla Client v1.3 or pick your game's Data folder.", "amber", "choose_install"
            label = f"{name} · COMING SOON" if c.get("coming_soon") else f"SET UP {name}"
            return False, label, "Add its download link or install folder in Settings → Game clients.", "amber", "settings"
        if c["type"] == "engine" and not wow_data_dir(self.settings.get("wow_folder", "")):
            return False, "CHOOSE YOUR GAME'S DATA FOLDER", "Press PLAY to point Open Vanilla at your game data (or pick the browser client).", "amber", "choose_install"
        if c["type"] == "engine" and self._wow_issues:
            return False, "YOUR WOW FOLDER NEEDS A FIX", f"{self._wow_issues[0]}. Press PLAY to pick another folder.", "red", "choose_install"
        rb, cb = int(realm.get("build", 5875)), int(c.get("build", 5875))
        if rb != cb:
            need = BUILD_NAMES.get(rb, str(rb))
            return False, f"THIS SERVER NEEDS {need}", f"{realm.get('name')} runs {need}. Pick a {need} client below, or another server.", "amber", "servers"
        if st and st["status"] == "offline":
            return True, "SERVER OFFLINE", "You can start the client; logging in will fail until the server is up.", "red", "servers"
        if c["type"] == "engine":
            who = (f"Signed in as {self.session.get('display') or self.session['user'].capitalize()}"
                   if self.session.get("password") else "PLAY signs you in first (in your browser)")
        else:
            who = "Realmlist set automatically"
        return True, "READY TO PLAY", f"{realm.get('name')} · {who}", "blue", None

    def update_status(self):
        cv = self.cv
        job = self.job
        b = self.bar_state
        side = ""
        enabled = True
        if job and not job.get("done"):
            frac = job.get("progress", 0)
            what = " ".join(p for p in (job.get("verb", "DOWNLOADING"), job["label"]) if p)
            if job.get("total"):
                head = f"{what} ({int(frac * 100)}%)…"
                detail = job.get("detail") or f"{fmt_size(job.get('received', 0))} of {fmt_size(job['total'])}"
                b.update(style="blue", fraction=frac, indeterminate=False, busy=True)
            else:
                head = f"{what}…"
                detail = job.get("detail") or fmt_size(job.get("received", 0)) or "Starting…"
                b.update(style="violet", fraction=0, indeterminate=True, busy=True)
            side = f"{job.get('speed', 0) / 1e6:.1f} MB/s" if job.get("speed") else ""
            detail = f"{detail}  ·  click the bar to cancel" if detail else "Click the bar to cancel"
            enabled = False
        else:
            ok, head, detail, style, _ = self.readiness()
            st = self.realm_state.get(self.realm_index)
            if ok and not st and self.play_mode() == "online":
                b.update(style="violet", fraction=0, indeterminate=True, busy=True)
                detail = "Checking the server…"
            else:
                b.update(style=style, fraction=1.0, indeterminate=False, busy=False)
            if st and st.get("ping") is not None and self.play_mode() == "online":
                side = f"{st['ping']} ms"
            enabled = ok
        # the update runs beside whatever the bar shows; the gold button above PLAY appears when it's ready
        pill, _ = self.update_pill()
        if pill:
            side = pill
        self._paint_update_button()
        self._paint_play(enabled)
        if self._notice:
            detail, dcol = self._notice[0], self._notice[1]
        else:
            dcol = MUTED
        b["dirty"] = True
        fnt = tkfont.Font(family=DISPLAY_FAMILY, size=10, weight="bold")
        while fnt.measure(head) > self.bar_w - 90 and len(head) > 6:
            head = head[:-2].rstrip() + "…"
        cv.itemconfig(self.bar_text, text=head)
        cv.itemconfig(self.bar_shadow, text=head)
        cv.itemconfig(self.bar_detail, text=detail, fill=dcol)
        cv.itemconfig(self.bar_side, text=side)
        c = self.client()
        mode = self.play_mode()
        sub = {"browser": "IN YOUR BROWSER", "solo": "SOLO  ·  ON THIS PC"}.get(mode) or \
            ("IN BROWSER" if c["type"] == "web" else f"ONLINE  ·  {c['name']}")
        cv.itemconfig(self.play_sub, text=sub.upper())
        self._render_bar(time.perf_counter() - self._t0)

    def _paint_update_button(self):
        """UPDATE READY · RESTART, above PLAY on every page, once a checked update is staged."""
        want = bool(self.update_ready) and self.page == "play"   # other pages: the text beside the bar says it
        if want == getattr(self, "_update_btn_shown", False):
            return
        self._update_btn_shown = want
        self.cv.delete("updatebtn")
        if want:
            w = 236
            self.pill_button(WIN_W - 14 - w, WIN_H - BOT - 44, w, 34,
                             f"UPDATE READY  \u00b7  RESTART ({self.update_ready['version']})", self.apply_update,
                             style="gold", tags=("updatebtn",), size=8, icon="download")

    def _paint_play(self, enabled):
        self._play_enabled = enabled
        state = "disabled" if not enabled else ("hover" if self._hover else "normal")
        self.cv.itemconfig(self.play_item, image=self.play_imgs[state])

    def _play_hover(self, on):
        self._hover = on
        self.cv.config(cursor=self.CUR_HAND if on else "")
        self._paint_play(self._play_enabled)

    def _play_press(self):
        if self._play_enabled:
            self.cv.itemconfig(self.play_item, image=self.play_imgs["pressed"])
            self.cv.coords(self.play_item, self.play_x, self.play_y + 1)
        self.after(110, self._play_release)

    def _play_release(self):
        self.cv.coords(self.play_item, self.play_x, self.play_y)
        self._paint_play(self._play_enabled)
        self.play()

    def _update_cancelled(self, dl):
        if self.download is dl:
            self.download = None
        self.notice("Update download cancelled.", AMBER, 4)
        self.update_status()

    def busy_download(self):
        """The running job (client, mod, repack, Solo), or None. A background update never blocks anything."""
        if self.job and not self.job.get("done"):
            return self.job
        return None

    def cancel_download(self, ask=True):
        d = self.busy_download()
        if not d:
            return True
        if ask and d.get("solo"):
            if not messagebox.askyesno("Stop Solo?", "Stop Play Solo? The solo servers shut down (your solo characters "
                                       "are saved first) and the game is disconnected.", parent=self):
                return False
        elif ask and not messagebox.askyesno("Stop the download?",
                                             "Stop the download? A game download can be resumed later from where it stopped.",
                                             parent=self):
            return False
        d["cancel"] = True
        self.notice("Stopping…", AMBER, 3)
        return True

    def close_app(self):
        if self.busy_download() and not self.cancel_download():
            return
        if self.p2p_host is not None:  # hosting: keep it running in the tray, or stop it (saving characters) first
            if self._host_cfg().get("tray"):
                self._tray_start()
                return
            if not messagebox.askyesno("Stop hosting?", "Your realm is running. Closing the launcher stops it "
                                       "(characters are saved first) and disconnects its players. Close anyway?", parent=self):
                return
            self.withdraw()
            self.host_stop(then=lambda err: self.close_app())
            return
        if self.solo_session is not None or self.solo_run is not None:  # solo saves characters first: close after
            self.withdraw()
            self.after(500, self._close_when_solo_stopped, 0)
            return
        self.destroy()

    def _close_when_solo_stopped(self, waited):
        if (self.solo_session is None and self.solo_run is None) or waited > 300:
            self.destroy()
        else:
            self.after(500, self._close_when_solo_stopped, waited + 1)

    def _status_click(self):
        if self.busy_download():
            self.cancel_download()
            return
        action = self.readiness()[4]
        if action in ("solo_install", "solo_vanilla", "solo_play", "solo_pack"):
            self.play_solo_mode()
        elif action == "choose_install":
            self.show_page("install")
        elif action == "download_client":
            self.get_client()
        elif action in ("settings", "servers", "solo", "host"):
            self.show_page(action)

    def update_pill(self):
        """(text, action) for the small update text beside the bar (home_logic.update_pill)."""
        can_stage = bool(self.update_info and updater.pick_asset(self.update_info, LAYOUT.mode))
        return home_logic.update_pill(self.update_info, self.update_ready, self.download, can_stage,
                                      self.settings.get("auto_update", True))

    def _update_click(self):
        """The small update text beside the bar: restart into a ready update, retry, download, or the release page."""
        action = self.update_pill()[1]
        if action == "apply":
            self.apply_update()
        elif action == "retry":
            self.download = None
            self.start_download()
        elif action in ("download", "page"):
            self.start_download()

    def play(self):
        mode = self.play_mode()
        if mode == "solo":
            self.play_solo_mode()
            return
        c = self.client()
        ok, head, detail, _, action = self.readiness()
        if not ok:
            self._status_click()
            return
        if c["type"] == "web" or mode == "browser":
            self.play_web()
            return
        self.sync_client_addons(c)
        realm = self.realms[self.realm_index]
        signed_in = self.session.get("password") and self.session.get("realm", self.realm_index) == self.realm_index
        if not signed_in and safe_url(realm.get("portal")):
            # Not signed in: the kept Hero Key (no browser), else Google; then PLAY carries on.
            self.notice("Signing you in…" if self._saved_hero_key() else "Sign in to play — finishing in your browser", GOLD, 6)
            self.sign_in_auto(then=self.play)
            return
        exe = self.client_exe(c)
        if (self.realm_state.get(self.realm_index) or {}).get("via") == "website":
            self._through_portal(realm, lambda r: self._play_desktop(c, exe, r))
            return
        self._play_desktop(c, exe, realm)

    def _play_desktop(self, c, exe, realm):
        if c["type"] == "exe":
            self.play_exe(c, exe, realm)
            return
        env = os.environ.copy()
        env["WOW_DATA"] = wow_data_dir(self.settings["wow_folder"])
        port = int(realm.get("port", 3724))
        env["WOW_HOST"] = realm["host"] if port == 3724 else f"{realm['host']}:{port}"
        for k in ("WOW_USER", "WOW_PASS"):
            env.pop(k, None)
        user = self.session.get("user") or self.settings.get("account")
        if user:
            env["WOW_USER"] = user
        # The engine auto-submits the login when both WOW_USER and WOW_PASS are set.
        if self.session.get("password") and self.session.get("realm", self.realm_index) == self.realm_index:
            env["WOW_PASS"] = self.session["password"]
        if self.settings.get("mute_game"):
            env["WOW_NOSOUND"] = "1"
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env)
        except OSError as e:
            messagebox.showerror("Can't start", str(e), parent=self)
            return
        self._started()

    def _through_portal(self, realm, then):
        """A browser realm (no public game ports): start a local bridge to its website's game relay with the
        launcher's sign-in, then `then(realm)` with the realm pointed at the bridge (127.0.0.1:<port>)."""
        token = self._launcher_token()
        if not token:
            self.notice("Sign in to play this realm with the desktop game", GOLD, 6)
            self.sign_in_auto(then=self.play)
            return
        b_mod = p2p_module("bridge")
        if not b_mod or not hasattr(b_mod, "PortalBridge"):
            self.notice("This launcher can't reach browser realms with the desktop game: update it, or play in the browser.", RED, 10)
            return
        self.stop_portal_bridge()
        try:
            bridge = b_mod.PortalBridge(realm.get("portal"), token)
        except Exception as e:
            self.notice(str(e), RED, 8)
            return
        self.notice("Connecting through the realm's website…", GOLD, 6)

        def work():
            try:
                err = bridge.check()
                if not err:
                    bridge.start()
            except Exception as e:
                err = f"Couldn't start the connection ({e})."
            try:
                self.after(0, done, err)
            except RuntimeError:
                pass

        def done(err):
            if err:
                bridge.stop()
                self.notice(err, RED, 10)
                return
            self.portal_bridge = bridge
            then(dict(realm, host="127.0.0.1", port=bridge.auth_port))

        threading.Thread(target=work, daemon=True).start()

    def stop_portal_bridge(self):
        b, self.portal_bridge = self.portal_bridge, None
        if b:
            try:
                b.stop()
            except Exception:
                pass

    def play_exe(self, c, exe, realm):
        """A stock client (1.12.1, 3.3.5a, …): point its realmlist at the server, pre-fill the account, start it."""
        folder = os.path.dirname(exe)
        port = int(realm.get("port", 3724))
        if not valid_host(realm.get("host")):
            messagebox.showerror("Bad server address", f"{realm.get('host')!r} isn't a valid server address.", parent=self)
            return
        host = realm["host"] if port == 3724 else f"{realm['host']}:{port}"
        rl = os.path.join(folder, *c.get("realmlist", "realmlist.wtf").split("/"))
        try:
            os.makedirs(os.path.dirname(rl), exist_ok=True)
            if os.path.isfile(rl) and not os.path.isfile(rl + ".openvanilla-backup"):
                shutil.copy2(rl, rl + ".openvanilla-backup")
            with open(rl, "w", encoding="ascii", newline="\r\n") as f:
                f.write(f"set realmlist {host}\n")
        except OSError as e:
            messagebox.showerror("Can't set the realmlist", f"{rl}\n\n{e}", parent=self)
            return
        user = self.session.get("user") or self.settings.get("account")
        if user:
            cfg = os.path.join(folder, "WTF", "Config.wtf")
            try:
                lines = open(cfg, encoding="utf-8", errors="replace").read().splitlines() if os.path.isfile(cfg) else []
                lines = [l for l in lines if not l.lower().startswith("set accountname ")]
                lines.append(f'SET accountName "{user}"')
                os.makedirs(os.path.dirname(cfg), exist_ok=True)
                with open(cfg, "w", encoding="utf-8", newline="\r\n") as f:
                    f.write("\n".join(lines) + "\n")
            except OSError:
                pass
        try:
            subprocess.Popen(exe_command(exe), cwd=folder)
        except OSError as e:
            messagebox.showerror("Can't start", str(e), parent=self)
            return
        if self._web_session() and self.session.get("password"):
            # The stock client can't be logged in for you: its password is on the clipboard.
            self.clipboard_clear()
            self.clipboard_append(self.session["password"])
            self.notice("Game password copied — paste it with Ctrl+V on the login screen", GREEN, 8)
            return
        self._started()

    # ---------- PLAY > Solo (launcher/spp.py: SPP Classics in Realms\Solo, set up and started from here)

    def spp_paths(self):
        """Realms\\Solo, or the SPP Classics install the player pointed Solo at."""
        if not spp:
            return None
        server = self.settings.get("spp_server")
        if server and spp.is_spp_server(server):
            return spp.SppPaths(LAYOUT.solo, server=server)
        return spp.SppPaths(LAYOUT.solo)

    def spp_state(self):
        p = self.spp_paths()
        return spp.detect_state(p) if p else None

    def spp_download(self):
        """(url, sha256, size) of SPP Classics: live.json or links.txt may point it somewhere newer."""
        url = live_content.safe_link(self.links.get("SPP_URL") or "") or spp.SPP_ZIP_URL
        sha = self.links.get("SPP_SHA256") or None
        try:
            size = int(self.links.get("SPP_SIZE") or 0) or (spp.SPP_ZIP_SIZE if url == spp.SPP_ZIP_URL else None)
        except ValueError:
            size = None
        return url, sha, size

    def solo_client(self):
        """(exe, kind, data folder) Solo starts: the selected desktop client, any installed one, else WoW.exe in
        the player's WoW 1.12.1 folder. None when there's no game yet."""
        for c in [self.client()] + [c for c in self.clients if c is not self.client()]:
            if c.get("type") not in ("engine", "exe"):
                continue
            exe = self.client_exe(c)
            if not exe:
                continue
            if c["type"] == "exe":
                return exe, "exe", None
            data = wow_data_dir(self.settings.get("wow_folder", ""))
            if data:
                return exe, "engine", data
        wow = self.settings.get("wow_folder")
        for n in ("WoW.exe", "Wow.exe", "wow.exe"):
            if wow and os.path.isfile(os.path.join(wow, n)):
                return os.path.join(wow, n), "exe", None
        return None

    def solo_readiness(self):
        if not spp:
            if solo:   # the older Open Vanilla solo pack (live.json flags.solo_pack)
                return True, "READY · SOLO ON THIS PC", "Press PLAY to start the solo server on this PC.", "blue", "solo_pack"
            return home_logic.solo_step(None, False)
        return home_logic.solo_step(self.spp_state(), bool(self.solo_client()), self.solo_run is not None,
                                    self.spp_download()[2])

    def play_solo_mode(self):
        """PLAY in Solo mode does Solo's next step: download -> guided Vanilla step -> play."""
        if self.busy_download():
            self.notice("Wait for the download to finish (or cancel it from the bar) first.", AMBER, 4)
            return
        action = self.solo_readiness()[4]
        if action == "solo_pack":
            self.play_solo()
        elif action == "solo_install":
            self.solo_install()
        elif action == "solo_vanilla":
            self.solo_vanilla()
        elif action == "choose_install":
            self.show_page("install")
        elif action == "solo_play":
            self.solo_play()

    def solo_install(self):
        """Download SPP Classics into Realms\\Solo, unpack it and fetch its server files, with progress in the bar."""
        p = self.spp_paths()
        url, sha, size = self.spp_download()
        if spp.detect_state(p) == "missing":
            host = urllib.parse.urlsplit(url).hostname or "GitHub"
            if not messagebox.askokcancel(
                    "Play Solo",
                    "Play Solo runs your own Vanilla realm on this PC with SPP Classics (CMaNGOS, with "
                    "playerbots to group with). It works offline once it's set up.\n\n"
                    f"The launcher downloads SPP Classics ({home_logic.human_size(size) if size else 'about 110 MB'}) "
                    f"from {host} into\n{p.root}\nthen fetches its server files (about 700 MB) and walks you through "
                    "one setup step. No install or admin rights needed; downloads resume if they stop.", parent=self):
                return
        job = self.job = dict(label="SPP CLASSICS", verb="DOWNLOADING", progress=0.0, received=0, total=0, speed=0,
                              detail="Starting…", spp=True)
        stages = {"download": ("DOWNLOADING", "SPP CLASSICS"), "unpack": ("UNPACKING", "SPP CLASSICS"),
                  "base": ("FETCHING", "SPP SERVER FILES")}

        def report(stage, text, frac=None):
            verb, label = stages.get(stage, ("SETTING UP", "SPP CLASSICS"))
            job.update(verb=verb, label=label, detail=text, progress=frac or 0.0, total=1 if frac is not None else 0)
            try:
                self.after(0, self.update_status)
            except RuntimeError:
                pass

        inst = spp.SppInstaller(p, url=url, sha256=sha, size=size, report=report, cancel=job)

        def work():
            err = None
            try:
                inst.run("base")
            except spp.Cancelled:
                job["cancelled"] = True
            except (spp.SppError, OSError, ValueError) as e:
                err = str(e)
            except Exception as e:  # a bug must not leave the bar stuck
                err = f"Something went wrong: {e}"
            try:
                self.after(0, self._solo_install_done, job, err)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()
        self.update_status()
        if self.page == "solo":
            self.show_page("solo", animate=False)

    def _solo_install_done(self, job, err):
        job["done"] = True
        if self.job is job:
            self.job = None
        if job.get("cancelled"):
            self.notice("Solo setup paused. Press PLAY to carry on where it stopped.", AMBER, 6)
        elif err:
            messagebox.showerror("Play Solo", f"{err}\n\nPress PLAY to try again: finished parts are kept.", parent=self)
        else:
            self.notice("SPP Classics is ready for its one guided step.", GREEN, 6)
            self.solo_vanilla()
        self.update_status()
        if self.page in ("solo", "play"):
            self.show_page(self.page, animate=False)

    def solo_vanilla(self):
        """Step 4: SPP's own setup menu, in a console the player types into. The launcher watches for it to finish."""
        try:
            spp.SppInstaller(self.spp_paths()).open_vanilla_setup()
        except (spp.SppError, OSError) as e:
            messagebox.showerror("Play Solo", str(e), parent=self)
            return
        steps = "\n\n".join(f"{i}.  {t}" for i, t in enumerate(spp.VANILLA_STEPS, 1))
        dlg = self.p2p_dialog("SET UP VANILLA (ONCE)", "SPP Classics' own setup window just opened. In it:\n\n" + steps +
                              "\n\nThe launcher watches for it to finish: PLAY turns ready by itself.", width=580)
        dlg.buttons(("OK", dlg.close, True), ("Open the window again", lambda: (dlg.close(), self.solo_vanilla()), False))
        self._solo_watch_gen = getattr(self, "_solo_watch_gen", 0) + 1
        self.after(4000, self._solo_watch, self._solo_watch_gen, 0)
        return dlg

    def _solo_watch(self, gen, n):
        if gen != getattr(self, "_solo_watch_gen", 0) or n > 2700:   # a newer watch, or 3 hours
            return
        if self.spp_state() == "ready":
            self.notice("Solo is set up. Press PLAY to play.", GREEN, 10)
            self.update_status()
            if self.page in ("solo", "play"):
                self.show_page(self.page, animate=False)
            return
        self.after(4000, self._solo_watch, gen, n + 1)

    def solo_play(self):
        """Start SPP's servers hidden, point the game at 127.0.0.1, play; closing the game saves and stops them."""
        if self.solo_run is not None:
            self.notice("Solo is already running. Close the game to stop it.", AMBER, 4)
            return
        cl = self.solo_client()
        if not cl:
            self.show_page("install")
            return
        exe, kind, data = cl
        if self.client().get("type") in ("engine", "exe"):
            self.sync_client_addons(self.client())
        job = self.job = dict(label="SOLO WORLD", verb="STARTING THE", progress=0.0, received=0, total=0, speed=0,
                              detail="Starting the solo servers…", solo=True)
        heads = {"start": ("STARTING THE", "SOLO WORLD"), "play": ("", "PLAYING SOLO"), "stop": ("STOPPING", "SOLO"),
                 "done": ("", "SOLO STOPPED")}

        def report(stage, text, frac=None):
            verb, label = heads.get(stage, ("", "SOLO"))
            job.update(verb=verb, label=label, detail=text, progress=frac or 0.0, total=1 if frac is not None else 0)
            try:
                self.after(0, self.update_status)
            except RuntimeError:
                pass

        paths = self.spp_paths()
        run = self.solo_run = spp.SoloPlay(paths, exe, kind=kind, report=report, cancel=job, data_folder=data,
                                           servers=spp.SppServers(paths, logs_dir=LAYOUT.logs))

        def work():
            err = None
            try:
                run.run()
            except spp.Cancelled:
                pass
            except (spp.SppError, OSError) as e:
                err = str(e)
            except Exception as e:  # a bug must not leave the bar stuck
                err = f"Something went wrong: {e}"
            try:
                self.after(0, self._solo_play_done, job, err)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()
        self.update_status()

    def _solo_play_done(self, job, err):
        job["done"] = True
        if self.job is job:
            self.job = None
        self.solo_run = None
        if err:
            messagebox.showerror("Play Solo", err, parent=self)
        else:
            self.notice("Solo stopped. Your characters are saved in Realms\\Solo.", GREEN, 6)
        self.update_status()

    def page_solo(self):
        """PLAY > Solo: the four steps, where it lives, and an existing SPP install instead of a new one."""
        x, y, w, h = self.big_panel("PLAY SOLO", "play", "SPP Classics  ·  CMaNGOS with playerbots  ·  on this PC")
        if not spp:
            self.empty_state(self._scroll_list(x, y, w, h), "Play Solo isn't in this launcher build",
                             "launcher/spp.py is missing. Online and browser play still work.")
            return
        state = self.spp_state()
        lw = (w - 20) // 2
        self.card(x, y, lw, h, "solo_steps", "solo_steps")
        self.shadow_text(x + 22, y + 26, "FOUR STEPS, ONE TIME", 10, GOLD)
        yy = y + 58
        for i, (label, done, cur) in enumerate(home_logic.solo_checklist(state), 1):
            mark, col = ("✓", GREEN) if done else (("›", GOLD) if cur else ("·", MUTED))
            self.cv.create_text(x + 26, yy, anchor="w", text=mark, fill=col, font=font(12, "bold"), tags="page")
            self.cv.create_text(x + 50, yy, anchor="w", text=f"{i}.  {label}", fill=TEXT if (cur or done) else MUTED,
                                font=font(10, "bold" if cur else "normal"), tags="page")
            yy += 34
        ok, head, detail, style, action = self.solo_readiness()
        self.cv.create_text(x + 22, yy + 10, anchor="nw", text=detail, fill=MUTED, font=font(9), width=lw - 44, tags="page")
        if self.busy_download():
            self.pill_button(x + 22, y + h - 60, lw - 44, 38, "CANCEL", self.cancel_download, style="danger", size=10,
                             icon="close")
        elif action:
            label = {"solo_install": "DOWNLOAD SPP CLASSICS" if state == "missing" else "CONTINUE SETUP",
                     "solo_vanilla": "OPEN THE GUIDED STEP", "choose_install": "CHOOSE GAME DATA FOLDER",
                     "solo_play": "PLAY SOLO"}.get(action, "CONTINUE")
            if action == "solo_install" and state == "missing" and self.spp_download()[2]:
                label += f"  ({home_logic.human_size(self.spp_download()[2])})"
            self.pill_button(x + 22, y + h - 60, lw - 44, 38, label, self._solo_page_go, style="gold", size=10,
                             icon="download" if action == "solo_install" else "play")
        x2 = x + lw + 20
        self.card(x2, y, lw, h, "solo_where", "solo_where")
        self.shadow_text(x2 + 22, y + 26, "WHERE IT LIVES", 10, GOLD)
        p = self.spp_paths()
        custom = bool(self.settings.get("spp_server")) and p.server == os.path.abspath(self.settings["spp_server"])
        where = p.server if custom else p.root
        self.cv.create_text(x2 + 22, y + 50, anchor="nw", fill=TEXT, font=font(9), width=lw - 44, tags="page",
                            text=f"{where}\n\nYour solo characters stay there, apart from any online realm. Log in as SOLO "
                                 "with password SOLO. Closing the game saves the world and stops the servers.\n\n"
                                 "Already have SPP Classics? Point Solo at it instead of downloading it again.")
        by = y + h - 60
        self.pill_button(x2 + 22, by, 200, 38, "OPEN FOLDER", lambda: self.open_path(where), size=9, icon="folder")
        if custom:
            self.pill_button(x2 + 232, by, lw - 254, 38, "USE REALMS\\SOLO", self._solo_default_folder, size=9)
        else:
            self.pill_button(x2 + 232, by, lw - 254, 38, "I HAVE SPP CLASSICS…", self._locate_solo_spp, size=9)
        self.link_text(x2 + 22, by - 18, "SPP Classics project page ›",
                       lambda: safe_open(self.links.get("SPP_PAGE") or spp.SPP_PAGE), 8)

    def _solo_page_go(self):
        if self.play_mode() != "solo" and "solo" in dict(self.play_modes()):
            self.set_play_mode("solo")
        self.play_solo_mode()

    def _locate_solo_spp(self):
        path = filedialog.askdirectory(parent=self, title="Choose your SPP Classics folder (SPP_Classics_V2 or its SPP_Server)")
        if not path:
            return
        server = next((c for c in (path, os.path.join(path, spp.SERVER_FOLDER)) if spp.is_spp_server(c)), None)
        if not server:
            messagebox.showerror("That isn't SPP Classics", "There's no Launcher.bat and Server folder there. Pick the "
                                 "SPP_Classics_V2 folder (or the SPP_Server folder inside it).", parent=self)
            return
        self.settings["spp_server"] = server
        self.save_settings()
        self.update_status()
        self.show_page("solo", animate=False)

    def _solo_default_folder(self):
        self.settings.pop("spp_server", None)
        self.save_settings()
        self.update_status()
        self.show_page("solo", animate=False)

    # ---------- PLAY SOLO (play_local.SoloSession: download the solo pack once, start it hidden, play, stop)

    def play_solo(self):
        if not solo:
            return
        if self.solo_session is not None:
            self.notice("Solo is already running. Close the game to stop it.", AMBER, 4)
            return
        if self.busy_download():
            self.notice("Wait for the download to finish (or cancel it) first.", AMBER, 4)
            return
        c = self.client()
        exe = self.client_exe(c) if c["type"] in ("engine", "exe") else None
        session = solo.SoloSession(reporter=None, client=exe, settings=self.settings)
        self.notice("Checking the solo server…", GOLD, 4)

        def check():
            try:
                status, manifest = session.pack_status()
                err = None
            except solo.SoloError as e:
                status, manifest, err = None, None, str(e)
            self.after(0, self._play_solo_confirmed, session, status, manifest, err)

        threading.Thread(target=check, daemon=True).start()

    def _play_solo_confirmed(self, session, status, manifest, err):
        if err or status == "offline":
            messagebox.showerror("Play Solo", err or "The solo server isn't downloaded yet and the download server "
                                 "can't be reached. Connect to the internet once and try again.", parent=self)
            return
        if status in ("missing", "update"):
            size = solo.human_size(int(manifest["size"]))
            text = ("Play Solo runs your own Open Vanilla world on this PC: the same client, addons and Vanilla Remastered content, "
                    f"with playerbots to group with. It downloads the solo server ({size}, once) into Realms\\SoloPack; "
                    "no install or admin rights. The first start makes the world's maps from your game client "
                    "(10-20 minutes)." if status == "missing" else
                    f"A new solo server is ready ({manifest['version']}, {size}). Download it now?")
            if not messagebox.askokcancel("Play Solo", text + "\n\n" + solo.SOLO_NOTE, parent=self):
                return
        job = self.job = dict(label="SOLO", verb="PLAY", progress=0.0, received=0, total=0, speed=0, solo=True,
                              detail="")
        session.reporter = _SoloJob(self, job)
        self.solo_session = session

        def watch():  # "click the bar to cancel" sets job["cancel"]: stop the session
            if self.solo_session is not session:
                return
            if job.get("cancel"):
                session.stop()
            self.after(400, watch)

        def work():
            err = None
            try:
                session.run()
            except solo.Cancelled:
                pass
            except solo.SoloError as e:
                err = str(e)
            except Exception as e:  # a bug must not leave the bar stuck
                err = f"Something went wrong: {e}"
            self.after(0, self._play_solo_done, job, err)

        self.after(400, watch)
        threading.Thread(target=work, daemon=True).start()
        self.update_status()

    def _play_solo_done(self, job, err):
        job["done"] = True
        if self.job is job:
            self.job = None
        self.solo_session = None
        if err:
            messagebox.showerror("Play Solo", err, parent=self)
        else:
            self.notice("Solo stopped. Your solo characters are saved on this PC.", GREEN, 6)
        self.update_status()

    def _started(self):
        self.notice(f"Starting {self.client()['name']}…", GREEN)
        if self.portal_bridge:
            # the game's connection runs through this launcher: minimise it instead of closing it
            self.notice("Keep the launcher open while you play: the game connects through it.", GOLD, 12)
            if self.settings.get("close_on_play"):
                self.after(1500, self.minimize)
            return
        if self.settings.get("close_on_play"):
            self.after(1500, self.destroy)

    # ---------- downloads (client, server software, mods, repacks, repos)

    def choose_install(self, c=None):
        """Pick the player's own World of Warcraft 1.12.1 folder, check it (wow_import: archives, WoW.exe build)
        and lock it in for this client and the Open Vanilla engine. Returns True when a good folder was saved."""
        c = c or self.client()
        while True:
            path = filedialog.askdirectory(parent=self, title="Choose your game's Data folder (or the folder with WoW.exe)")
            if not path:
                return False
            data = wow_data_dir(path)
            root = os.path.dirname(data) if data else path  # they may pick Data\ itself
            issues = wow_problems(root)
            if c["type"] == "exe" and not self.client_exe(dict(c, path=root)):
                issues = ["There's no WoW.exe in that folder."] + issues
            if not issues:
                break
            if not messagebox.askretrycancel("That folder won't work", "\n".join(issues) + "\n\nPick a different folder?",
                                             parent=self):
                return False
        self._lock_in(c, root)
        return True

    def _lock_in(self, c, root):
        """Save a checked 1.12.1 folder for this client and the Open Vanilla engine."""
        self.settings["wow_folder"] = root
        self._wow_issues = []
        self._client_override(c, "path", root)  # saves settings
        self.notice("Vanilla Client v1.3 found. You're ready to play.", GREEN, 5)
        self.update_status()
        if self.page in ("play", "settings", "install"):
            self.show_page("play" if self.page == "install" else self.page, animate=False)
        return True

    def get_client(self):
        if self.client()["type"] == "exe":  # stock clients: install a fresh copy or pick the player's own
            self.show_page("install")
            return
        url = self.client_download()
        if not url:
            self.notice("No download link set for this client yet (Settings → Game clients).", AMBER, 5)
            self.show_page("settings")
            return
        self.fetch_or_open(url, self.client()["name"])

    def open_client_page(self, c=None):
        """The 1.12.1 client is never downloaded inside the launcher: open its page in the player's browser."""
        url = self.client_download(c or self.client())
        if not url:
            self.notice("No download page set for this client yet (Settings → Game clients).", AMBER, 5)
            return
        safe_open(url)
        self.notice("Opened in your browser. When it's unzipped, press SELECT EXISTING FOLDER.", GREEN, 8)

    def install_classic(self, c=None, target=None):
        """Download the 1.12.1 client zip into a new folder on the energy bar, extract it, check it, lock it in.
        A stopped download resumes from its .part file the next time."""
        c = c or self.client()
        url = self.client_download(c)
        if not url:
            return
        self.download_unpack(url, "VANILLA CLIENT V1.3", target or self.classic_target(), "wow.exe",
                             lambda job: self._classic_done(c, job), "Vanilla Client v1.3")

    def download_unpack(self, url, label, target, marker, on_done, what):
        """Download a zip on the energy bar (resumable, mirrors, checksum when known), unpack it into target and
        hand on_done the job; job["root"] = the unpacked folder that holds `marker`."""
        if not is_file_link(url):
            safe_open(url)
            self.notice(f"Opened the {what} download page in your browser")
            return
        if self.job and not self.job.get("done"):
            self.notice("Another download is still running.", AMBER)
            return
        parent = os.path.dirname(target)
        if os.path.isdir(target) and os.listdir(target) and not any(
                f.lower().endswith(".part") or f.lower().endswith(".zip") for f in os.listdir(parent) if os.path.isfile(os.path.join(parent, f))):
            if not messagebox.askyesno("Folder isn't empty", f"{target} already has files in it.\n\nInstall into it anyway?", parent=self):
                return
        if not self.confirm_download(url, what, target):
            return
        fresh = not (os.path.isdir(target) and os.listdir(target))
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            self.notice(f"Can't create {target}: {e}"[:110], RED, 6)
            return
        name = os.path.basename(urllib.parse.urlsplit(url).path) or "download.zip"
        zpath = os.path.join(parent, name)
        part = zpath + ".part"
        job = self.job = dict(label=label, verb="DOWNLOADING", progress=0.0, received=0, total=0, speed=0, path=zpath)

        def download():
            if os.path.isfile(zpath) and zipfile.is_zipfile(zpath):
                return  # already downloaded earlier (e.g. the extract was interrupted)
            mirrors, job["md5"] = download_mirrors(url)
            total, last = 0, None
            for attempt in range(len(mirrors) * 3):
                src = mirrors[attempt % len(mirrors)]
                if attempt >= len(mirrors):
                    job.update(detail=f"Server busy, retrying ({attempt + 1})…")
                    time.sleep(min(30, 3 * attempt))
                try:
                    total = self._fetch_into(src, part, parent, job)
                    last = None
                    break
                except Cancelled:
                    raise
                except urllib.error.HTTPError as e:
                    if e.code == 416 and os.path.isfile(part):  # nothing left to fetch: the .part is complete
                        last = None
                        break
                    last = e
                    if e.code in (401, 403, 404):
                        continue  # try the next mirror straight away
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    if isinstance(e, OSError) and str(e).startswith("Not enough disk space"):
                        raise
                    last = e
            if last:
                raise OSError(f"Couldn't download it ({last}). Press the download button again to resume.")
            if total and os.path.getsize(part) < total:
                raise OSError("The download stopped early. Press the download button again to resume.")
            job.pop("detail", None)
            if job.get("md5"):
                job.update(verb="VERIFYING", progress=0.0, received=0, speed=0, detail="Checking the download…")
                h, done, size = hashlib.md5(), 0, os.path.getsize(part)  # nosec B324 - archive.org publishes md5; this checks for corruption
                job["total"] = size
                with open(part, "rb") as f:
                    for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                        check_cancel(job)
                        h.update(chunk)
                        done += len(chunk)
                        job.update(received=done, progress=done / size)
                if h.hexdigest().lower() != job["md5"].lower():
                    os.remove(part)  # corrupt: never resume from it
                    raise OSError("The download was corrupted (checksum mismatch). Press the download button to try again.")
            os.replace(part, zpath)

        def extract():
            job.update(verb="EXTRACTING", progress=0.0, received=0, speed=0, detail="Unpacking…")
            root_real = os.path.realpath(target)
            with zipfile.ZipFile(zpath) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                total = sum(i.file_size for i in infos) or 1
                job["total"] = total
                done = 0
                for i in infos:
                    check_cancel(job)
                    dest = os.path.realpath(os.path.join(target, i.filename))
                    if not dest.startswith(root_real + os.sep):
                        continue  # never write outside the target folder
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(i) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out, 1024 * 1024)
                    done += i.file_size
                    job.update(received=done, progress=done / total, detail=f"{fmt_size(done)} of {fmt_size(total)}")
            found = find_marker()
            if found:
                return found
            # some zips (the archive.org 1.12.1 one) hold the Windows installer instead of the game folder
            setup = next((os.path.join(d, f) for d, _ds, fs in os.walk(target) for f in fs
                          if f.lower().endswith(".exe") and "setup" in f.lower()), None)
            if setup and sys.platform == "win32":
                job.update(verb="INSTALLING", progress=0.5, received=0, total=0, speed=0,
                           detail="Running the game installer (its window shows the progress)…")
                game = os.path.join(target, "World of Warcraft")
                subprocess.run([setup, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", f"/DIR={game}"],
                               check=False)  # nosec B603 - the installer the player chose to download
                found = find_marker()
                if found:
                    shutil.rmtree(os.path.dirname(setup), ignore_errors=True)  # installer files no longer needed
                    return found
            raise OSError(f"The zip didn't contain {marker}.")

        def find_marker():
            """The folder holding the marker file (zips usually wrap everything in one top folder)."""
            for dirpath, _dirs, files in os.walk(target):
                if any(f.lower() == marker for f in files):
                    return dirpath
            return None

        def work():
            try:
                download()
                job["root"] = extract()
                try:
                    os.remove(zpath)  # the game is unpacked; the zip is no longer needed
                except OSError:
                    pass
                job.update(done=True, progress=1.0)
            except Cancelled:
                job.update(done=True, cancelled=True)
                if job.get("verb") == "EXTRACTING" and fresh:
                    shutil.rmtree(target, ignore_errors=True)  # half-unpacked: the next install starts clean
            except Exception as e:
                job.update(done=True, error=str(e))
            self.after(0, on_done, job)

        threading.Thread(target=work, daemon=True).start()
        self.notice(f"Downloading {what}. You can keep using the launcher.", GOLD, 5)
        self.show_page("play", animate=False)
        self.update_status()

    @staticmethod
    def _fetch_into(src, part, parent, job):
        """Append src to the .part file (resuming with a Range request). Returns the full file size."""
        if not src.lower().startswith(("https://", "http://")):
            raise OSError("not a web download link")
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        headers = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
        if have:
            headers["Range"] = f"bytes={have}-"
        with urllib.request.urlopen(urllib.request.Request(src, headers=headers), timeout=45) as r:
            if have and r.status != 206:
                have = 0  # the server ignored the resume: start over
            total = int(r.headers.get("Content-Length") or 0) + have
            free = shutil.disk_usage(parent).free
            if total and free < (total - have) + total * 1.1 + 200e6:
                raise OSError(f"Not enough disk space: need about {fmt_size((total - have) + total * 1.1)}, "
                              f"{fmt_size(free)} free on that drive.")
            job["total"] = total
            job.pop("detail", None)
            t0, got = time.time(), have
            with open(part, "ab" if have else "wb") as out:
                while True:
                    check_cancel(job)
                    chunk = r.read(512 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
                    job.update(received=got, progress=(got / total) if total else 0,
                               speed=(got - have) / max(0.001, time.time() - t0))
        if total and got < total:
            raise OSError("connection dropped")
        return total

    def _classic_done(self, c, job):
        self.job = None
        if job.get("cancelled"):
            part = job["path"] + ".part"
            got = os.path.getsize(part) if os.path.isfile(part) else 0
            self.notice(f"Download paused at {fmt_size(got)}. Press DOWNLOAD & INSTALL to resume." if got
                        else "Install cancelled.", AMBER, 8)
        elif job.get("error"):
            self.notice(f"Install failed: {job['error']}"[:110], RED, 8)
        else:
            root = job["root"]
            issues = wow_problems(root)
            if issues:
                self.notice(f"Installed to {root}, but: {issues[0]}"[:110], AMBER, 8)
            else:
                self._lock_in(c, root)
                self.notice(f"Vanilla Client v1.3 installed to {root}. Ready to play.", GREEN, 8)
        self.update_status()

    def get_server(self):
        """The server software is built in (HOST > Dedicated server); there is nothing to download."""
        self.tab_state["host"] = "server"
        self.show_page("host")

    def confirm_download(self, url, label, dest):
        """A secure (https) download starts right away, with a notice of where it comes from and where it
        goes; only a link without https asks first, since that file could be changed on the way."""
        parts = urllib.parse.urlsplit(url or "")
        host = parts.hostname or "an unknown site"
        if parts.scheme == "https":
            self.notice(f"Downloading {label} from {host} to {dest}"[:110], GOLD, 6)
            return True
        insecure = "\n\nThis link isn't secure (no https), so the file could be changed on the way."
        return messagebox.askyesno(
            "Download this?",
            f"Download {label} from {host}?\n\n{url}\n\nIt will be saved to:\n{dest}{insecure}\n\n"
            "Only continue if you trust this site.",
            icon="warning", default="no", parent=self)

    def fetch_or_open(self, url, label, then=None):
        """Direct file links download in the launcher (with the energy bar); pages open in the browser."""
        if is_file_link(url):
            self.start_job(url, label, then=then)
        else:
            safe_open(url)
            self.notice(f"Opened the {label.title()} download page in your browser")

    def start_job(self, url, label, then=None, dest_dir=None, verb="DOWNLOADING"):
        if self.job and not self.job.get("done"):
            self.notice("Another download is still running.", AMBER)
            return
        if not safe_url(url) and not url.lower().startswith("http://"):
            self.notice("Only web (http/https) downloads are allowed.", RED, 5)
            return
        dest_dir = dest_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        if not self.confirm_download(url, label, dest_dir):
            return
        os.makedirs(dest_dir, exist_ok=True)
        name = os.path.basename(urllib.parse.urlsplit(url).path) or "download.zip"
        job = self.job = dict(label=label.upper(), verb=verb, progress=0.0, received=0, total=0, speed=0,
                              path=os.path.join(dest_dir, name))

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "OpenVanilla-Launcher"})
                with urllib.request.urlopen(req, timeout=25) as r, \
                        tempfile.NamedTemporaryFile(delete=False, dir=dest_dir, suffix=".part") as out:
                    total = int(r.headers.get("Content-Length") or 0)
                    job["total"] = total
                    t0, got = time.time(), 0
                    tmp = out.name
                    while True:
                        check_cancel(job)
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                        job.update(received=got, progress=(got / total) if total else 0,
                                   speed=got / max(0.001, time.time() - t0))
                os.replace(tmp, job["path"])
                job.update(done=True, progress=1.0)
            except Cancelled:
                job.update(done=True, cancelled=True)
                try:
                    os.remove(tmp)
                except (OSError, NameError):
                    pass
            except Exception as e:
                job.update(done=True, error=str(e))
            self.after(0, self._job_done, job, then)

        threading.Thread(target=work, daemon=True).start()
        self.update_status()

    def _job_done(self, job, then):
        self.job = None
        if job.get("cancelled"):
            self.notice("Download cancelled.", AMBER, 4)
        elif job.get("error"):
            self.notice(f"Download failed: {job['error']}"[:110], RED, 6)
        elif then:
            try:
                then(job["path"])
            except Exception as e:
                self.notice(f"{job['label'].title()}: {e}"[:110], RED, 6)
        else:
            self.notice(f"{job['label'].title()} saved to Downloads", GREEN, 5)
            self.open_path(os.path.dirname(job["path"]))
        self.update_status()

    def install_from_url(self, url, label):
        target = self.client_addons_dir()
        if not target:
            self.notice("Mods install into a desktop client. Pick one in the Game Client box.", AMBER, 5)
            return

        def then(path):
            installed = install_zip(path, target)
            try:
                os.remove(path)
            except OSError:
                pass
            self.notice("Installed: " + ", ".join(installed), GREEN, 5)
            if self.page == "mods":
                self.show_page("mods", animate=False)

        self.start_job(url, label, then=then, dest_dir=tempfile.gettempdir(), verb="INSTALLING")

    # ---------- community directory (servers, mods, repacks)

    def load_directory(self):
        url = self.defaults.get("directory_url") if self.settings.get("load_directory", True) else None

        def work():
            data = None
            if url:
                try:
                    data = http_json(url, timeout=8)
                except Exception:
                    data = None
            self.after(0, self._directory_loaded, data)

        threading.Thread(target=work, daemon=True).start()

    def _directory_loaded(self, data):
        if isinstance(data, dict):
            self.directory = clean_directory(data)
            self.directory["_live"] = True
            self._dir_pings_started = False
        if self.page in ("servers", "mods"):
            self.show_page(self.page, animate=False)

    def ping_directory(self):
        """Ping listed servers only while the Servers page is open, and at most 30 of them,
        so a bad listing can't turn every launcher into traffic against someone else's host."""
        if getattr(self, "_dir_pings_started", False) or not self.settings.get("ping_servers", True):
            return
        self._dir_pings_started = True
        for srv in self.directory.get("servers", [])[:30]:
            threading.Thread(target=self._ping_dir, args=(srv,), daemon=True).start()

    def _ping_dir(self, srv):
        ping = tcp_ping(srv.get("host"), srv.get("port", 3724))
        key = f"{srv.get('host')}:{srv.get('port', 3724)}"
        try:
            self.after(0, self._dir_pinged, key, ping)
        except RuntimeError:
            pass

    def _dir_pinged(self, key, ping):
        self.dir_state[key] = ping
        if self.page == "servers" and self.tab_state.get("servers") == "community":
            if not getattr(self, "_dir_refresh_pending", False):
                self._dir_refresh_pending = True
                self.after(400, self._dir_refresh)

    def _dir_refresh(self):
        self._dir_refresh_pending = False
        if self.page == "servers":
            self.show_page("servers", animate=False)

    # ================================================================ background work

    def refresh_realms(self):
        for i, realm in enumerate(list(self.realms)):
            threading.Thread(target=self._probe_realm, args=(i, realm), daemon=True).start()

    def _probe_realm(self, i, realm):
        host, port = realm.get("host"), realm.get("port", 3724)
        ping = tcp_ping(host, port)
        status, detail, via = ("online" if ping is not None else "offline"), "", "tcp"
        portal = realm.get("portal")
        health = None
        if portal and str(portal).startswith("https://"):
            t0 = time.perf_counter()
            health = realm_health(portal)
            if health:
                status, detail = health
                if ping is None and status != "offline":
                    ping, via = int((time.perf_counter() - t0) * 1000), "website"
        if portal and not health:
            t0 = time.perf_counter()
            try:
                data = http_json(portal.rstrip("/") + "/api/status", timeout=5)
                svc = data.get("services", {})
                world = svc.get("mangosd") == "online"
                auth = svc.get("realmd") == "online"
                status = "online" if (auth and world) else ("partial" if (auth or world) else "offline")
                detail = f"Login {'up' if auth else 'down'} · world {'up' if world else 'down'}"
            except urllib.error.HTTPError as e:
                # A browser realm (wenilla-realm) answers 401 here: its website is up. It publishes no game
                # ports; the desktop game plays through the website instead (PortalBridge).
                web_ms = int((time.perf_counter() - t0) * 1000)
                if ping is None and e.code in (401, 403) and str(portal).startswith("https://"):
                    status, ping, via = "online", web_ms, "website"
                    detail = "Plays through the realm's website"
                elif ping is None:
                    detail = f"Website answered {e.code}; login port closed"
                else:
                    detail = "Login server answering"
            except Exception:
                detail = "Login port only (website unreachable)" if ping is not None else "Website and login port unreachable"
        elif ping is not None:
            detail = "Login server answering"
        busy = None
        if solo and i == 0 and portal:  # the official realm: full, slow or down? (its /healthz)
            try:
                busy = solo.probe_realm(realm)
            except Exception:
                busy = None
        try:
            self.after(0, self._realm_result, i, dict(status=status, ping=ping, detail=detail, busy=busy, via=via))
        except RuntimeError:
            pass

    def _realm_result(self, i, st):
        self.realm_state[i] = st
        if st.get("busy") and self.busy_tracker:
            was = self.busy_tracker.busy
            if self.busy_tracker.update(st["busy"]) and self.busy_hushed != self.busy_tracker.state and not self.solo_session:
                self.busy_hushed = self.busy_tracker.state
                self.notice(f"{self.busy_tracker.reason} PLAY SOLO plays offline on this PC while you wait.", AMBER, 15)
            elif not self.busy_tracker.busy:
                self.busy_hushed = None
            if was != self.busy_tracker.busy and self.page == "play":
                self.show_page("play", animate=False)  # PLAY SOLO turns gold (or back)
        if i == self.realm_index:
            self._paint_pill()
            self._paint_realm_status()
            self.update_status()
        if self.page == "servers" and self.tab_state.get("servers") == "mine":
            self.show_page("servers", animate=False)

    def check_for_update(self):
        """At start, in the background: the live content, a staged update from an earlier run, and the signed
        release manifest (a newer one starts downloading by itself; "Update ready" appears when it's checked)."""
        url = self.defaults.get("update_manifest")

        def work():
            try:
                if self.live.refresh() == "updated":
                    self.after(0, self._live_updated)
            except Exception:
                pass
            try:
                ready = updater.ready(LAYOUT, self.version)
            except OSError:
                ready = None
            if ready:
                self.after(0, self._set_update_ready, ready)
            if not url:
                return
            try:
                m = signed_manifest(url, timeout=6)
            except Exception:
                return
            if m is None:   # unsigned or tampered: no update offer (patch notes neither)
                return
            if version_tuple(m.get("version", "0")) > version_tuple(self.version) and m.get("url"):
                self.after(0, self._set_update, m)
            if m.get("patch_notes_url"):
                try:
                    notes = http_json(m["patch_notes_url"], timeout=6)
                    self.after(0, self._set_notes, notes)
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True).start()

    def _live_updated(self):
        """New live content arrived: links, flags and realm defaults change what pages show."""
        self.links.update(self.live.doc.get("links", {}))
        self.links.update(read_links_txt([INSTALL_DIR]))
        self.defaults = apply_links_overrides(self.defaults, self.links)
        self.reload_clients()          # live `clients` the player added follow the maintainer's list
        if self.live.doc.get("message"):
            msg = self.live.doc["message"]
            self.notice(msg["text"], {"warn": AMBER, "good": GREEN}.get(msg.get("level"), GOLD), 12)
        self._paint_modes()            # flags can switch Solo / Browser on or off
        self._fill_client_label()
        if self.page in ("play", "host", "notes", "mods", "solo"):
            self.show_page(self.page, animate=False)
        self.update_status()

    def _set_update(self, m):
        self.update_info = m
        if self.update_ready and not updater.newer(m["version"], self.update_ready["version"]):
            self.update_status()
            return
        if updater.pick_asset(m, LAYOUT.mode) and self.settings.get("auto_update", True):
            self.start_download()   # quietly, in the background: PLAY stays usable
        self.update_status()

    def _set_update_ready(self, info):
        if self.update_ready and not updater.newer(info["version"], self.update_ready["version"]):
            return
        self.update_ready = info
        self.update_status()
        if self.page == "play":
            self.show_page("play", animate=False)

    def _set_notes(self, notes):
        if isinstance(notes, dict) and notes.get("version"):
            self.patch_notes = notes
            if self.page in ("play", "notes"):
                self.show_page(self.page, animate=False)

    def start_download(self):
        """Stage the update in Cache\\Updates (resumable, SHA-256 from the signed manifest). A copy run from
        source can't replace itself: it opens the release page instead."""
        m = self.update_info
        if not m or (self.download and not self.download.get("done")):
            return
        if not updater.pick_asset(m, LAYOUT.mode):
            safe_open(self.community_links().get("github", "").rstrip("/") + "/releases/latest")
            self.notice("Opened the download page: this copy runs from source and updates with git.", GOLD, 6)
            return
        dl = self.download = dict(progress=0.0, received=0, speed=0, total=0, background=True)

        def work():
            t0 = time.time()

            def prog(done, total):
                dl.update(received=done, total=total or 0, progress=(done / total) if total else 0,
                          speed=done / max(0.001, time.time() - t0))
            try:
                info = updater.stage(m, LAYOUT, progress=prog, cancel=lambda: dl.get("cancel"))
                dl.update(done=True, progress=1.0)
                self.after(0, self._set_update_ready, info)
            except fetch_mod.Cancelled:
                self.after(0, self._update_cancelled, dl)
                return
            except Exception as e:
                dl.update(done=True, error=str(e))
            self.after(0, self.update_status)

        threading.Thread(target=work, daemon=True).start()
        self.update_status()

    def apply_update(self):
        """Update ready -> restart: hand off to the silent setup (installer) or the swap step (zip), then exit."""
        info = self.update_ready
        if not info:
            return
        if self.p2p_host is not None or self.solo_session is not None or self.solo_run is not None \
                or (self.dedicated and self.dedicated.servers.procs):
            if not messagebox.askyesno("Restart to update?", "Updating closes the launcher, which stops your realm or "
                                       "solo servers (characters are saved first). Update now?", parent=self):
                return
        try:
            updater.handoff(info, LAYOUT)
        except Exception as e:
            self.update_ready = None
            self.notice(f"Update not started: {e}"[:110], RED, 8)
            self.update_status()
            return
        self.notice(f"Updating to {info['version']}: Open Vanilla restarts in a moment…", GOLD, 10)
        self.after(400, self._exit_for_update)

    def _exit_for_update(self):
        for stop in (lambda: self.p2p_host and self.p2p_host.stop(),
                     lambda: getattr(self, "solo_run", None) and self.solo_run.servers.stop(),
                     lambda: getattr(self, "dedicated", None) and self.dedicated.stop_all()):
            try:
                stop()
            except Exception:
                pass
        self.destroy()


def install_zip(zip_path, addons_dir):
    """Extract the addon folders (those holding a .toc) from a zip into AddOns.

    Handles plain addon zips, multi-addon packs and GitHub "Repo-main/Addon.toc" zips (the folder
    is renamed to the .toc's name, as the game requires). Refuses paths outside AddOns."""
    os.makedirs(addons_dir, exist_ok=True)
    root = os.path.realpath(addons_dir)
    with zipfile.ZipFile(zip_path) as z:
        names = [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]
        raw = {n.replace("\\", "/"): n for n in z.namelist()}
        tocs = sorted((n for n in names if n.lower().endswith(".toc")), key=lambda n: n.count("/"))
        if not tocs:
            raise ValueError("That zip has no .toc file, so it is not a WoW addon.")
        picks = []  # (prefix inside zip, folder name in AddOns)
        for t in tocs:
            parts = t.split("/")
            prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
            if any(prefix.startswith(p) and p for p, _ in picks):
                continue  # a library inside an addon we already take whole
            if prefix == "" and picks:
                continue
            folder = parts[-1][:-4]
            if any(f.lower() == folder.lower() for _, f in picks):
                continue
            picks.append((prefix, folder))
        plan, installed = [], []
        for prefix, folder in picks:
            for n in names:
                if prefix and not n.startswith(prefix):
                    continue
                if not prefix and "/" in n:
                    continue
                target = os.path.realpath(os.path.join(root, folder, n[len(prefix):]))
                if not target.startswith(root + os.sep):
                    raise ValueError(f"Unsafe path in zip: {n}")
                plan.append((raw[n], target))
            installed.append(folder)
        for n, target in plan:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(n) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return installed


def fmt_size(n):
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def fmt_count(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"




class _GameLauncher:
    """Handed to p2p.join.join(): starts the picked desktop client against a realm (or the local relay bridge).
    Called from join's worker thread; the launch itself runs on the Tk thread.

        game_launcher(env, realmlist) -> process        (p2p.join: env has WOW_HOST/WOW_USER/WOW_PASS/WOW_REALM)
        game_launcher(host, port=3724, user=None, password=None) -> process
    Also carries what join may need: .token (the launcher sign-in token), .portal, .exe, .wow_folder."""

    def __init__(self, app):
        self.app = app
        c = app.client()
        self.exe = app.client_exe(c) if c["type"] != "web" else None
        self.build = int(c.get("build", 5875))
        self.wow_folder = app.settings.get("wow_folder", "")
        self.token = app._launcher_token()
        self.portal = app._p2p_portal()
        self.launched = []

    def __call__(self, host, port=3724, user=None, password=None, **kw):
        env = None
        if isinstance(host, dict):  # (env, realmlist)
            env, realmlist = host, str(port)
            host, _, p = realmlist.rpartition(":") if ":" in realmlist else (realmlist, "", "3724")
            port, user, password = int(p or 3724), env.get("WOW_USER"), env.get("WOW_PASS")
        self.launched.append((host, int(port or 3724), user))
        done = threading.Event()
        result = []

        def go():
            try:
                result.append(self.app.launch_at(host, port, user, password, kw.get("name"), extra_env=env))
            finally:
                done.set()

        self.app.after(0, go)
        if not done.wait(30) or not result or result[0] is None:
            raise RuntimeError("The game client didn't start.")
        return result[0]


class _P2PDialog:
    """A small non-blocking window in the launcher's style: gold Cinzel title, body text, kit buttons."""

    def __init__(self, app, title, text, width=520):
        self.app = app
        old = getattr(app, "_p2p_dialog", None)
        if old is not None:
            old.close()
        app._p2p_dialog = self
        self.title = title
        self.text = text
        top = self.top = tk.Toplevel(app, bg=PANEL, highlightthickness=1, highlightbackground="#5a4626")
        top.title(title.title())
        top.transient(app)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda e: self.close())
        tk.Label(top, image=app.img(f"dlg_title_{title}", art.emboss_text(title, 17, "#f3d179")), bg=PANEL).pack(
            anchor="w", padx=22, pady=(18, 4))
        tk.Frame(top, bg="#4a3b22", height=1).pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(top, text=text, bg=PANEL, fg=TEXT, font=font(9), wraplength=width - 44, justify="left").pack(
            anchor="w", padx=22)
        self.body = tk.Frame(top, bg=PANEL)
        self.body.pack(fill="x", padx=22, pady=(10, 0))
        self.bar = tk.Frame(top, bg=PANEL)
        self.bar.pack(fill="x", padx=22, pady=(14, 18))
        top.update_idletasks()
        x = app.winfo_rootx() + (WIN_W - width) // 2
        y = app.winfo_rooty() + 140
        top.geometry(f"{width}x{max(160, top.winfo_reqheight())}+{max(0, x)}+{max(0, y)}")

    def buttons(self, *specs):
        """(label, command, primary) …, laid out right to left like the launcher's dialogs."""
        self.button_cmds = {}
        for label, cmd, primary in specs:
            self.button_cmds[label] = cmd
            self.app.wbutton(self.bar, label, cmd, primary=primary).pack(side="right", padx=(8, 0))
        self.top.update_idletasks()
        self.top.geometry(f"{self.top.winfo_width()}x{self.top.winfo_reqheight()}")

    def close(self):
        if getattr(self.app, "_p2p_dialog", None) is self:
            self.app._p2p_dialog = None
        try:
            self.top.destroy()
        except tk.TclError:
            pass


class _SoloJob(solo.Reporter if solo else object):
    """Play Solo progress in the launcher's energy bar, through the same job dict downloads use.
    Called from the solo worker thread; the Tk side reads the dict on its next frame."""
    LABELS = {"download": "DOWNLOADING THE SOLO SERVER", "unpack": "UNPACKING THE SOLO SERVER",
              "extract": "MAKING MAPS FROM YOUR CLIENT", "database": "PREPARING THE SOLO WORLD",
              "start": "STARTING THE SOLO WORLD", "play": "PLAYING SOLO", "ready": "SOLO SERVERS RUNNING",
              "stop": "STOPPING SOLO", "done": "SOLO STOPPED"}

    def __init__(self, app, job):
        self.app, self.job = app, job

    def _refresh(self):
        try:
            self.app.after(0, self.app.update_status)
        except RuntimeError:
            pass

    def stage(self, key, text):
        self.job.update(label=self.LABELS.get(key, "SOLO"), verb="SOLO \u00b7", progress=0.0, total=0, received=0,
                        detail=text)
        self._refresh()

    def progress(self, done, total=None, text=None):
        if total:
            self.job.update(progress=max(0.0, min(1.0, done / total)), total=total, received=done)
        if text:
            self.job["detail"] = text
        self._refresh()

    def info(self, text):
        self.job["detail"] = text
        self._refresh()

    def warn(self, text):
        self.job["detail"] = text
        self._refresh()

def _windows_app_id():
    """Give the launcher its own taskbar identity, so Windows shows the Open Vanilla icon (not pythonw's)
    and groups its windows under Open Vanilla. Must run before the first window is created."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenVanilla.Launcher")
    except Exception:
        pass


SELF_TEST_MODULES = ("p2p.host", "p2p.join", "p2p.directory", "p2p.torrent", "play_local", "workshop", "spp", "home_logic", "game_clients",
                     "server_host", "updater", "live_content", "layout", "fetch", "server_control", "asset_server",
                     "studio", "aiohttp", "pymysql")


def self_test(out_path):
    """`OpenVanilla.exe --self-test FILE` (release.yml): import every module the frozen build must contain."""
    import importlib
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(1, here)
    lines, bad = [f"Open Vanilla {read_version()} frozen={FROZEN} layout={LAYOUT.mode}"], 0
    for name in SELF_TEST_MODULES:
        try:
            importlib.import_module(name)
            lines.append(f"ok   {name}")
        except Exception as e:
            bad += 1
            lines.append(f"FAIL {name}: {type(e).__name__}: {e}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if bad else 0


def run_tool(argv):
    """`OpenVanilla.exe --run web-backend [PORT]`: the dedicated server's website/API/Studio, from the frozen
    modules (HOST > Dedicated server starts it hidden)."""
    tool = argv[argv.index("--run") + 1] if argv.index("--run") + 1 < len(argv) else ""
    os.makedirs(LAYOUT.logs, exist_ok=True)
    for name in ("stdout", "stderr"):   # a windowed exe may start without them; print() must not fail
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.path.join(LAYOUT.logs, "web-backend.log"), "a", encoding="utf-8", errors="replace"))
    if tool == "web-backend":
        port = next((a for a in argv[argv.index("--run") + 2:] if a.isdigit()), "18090")
        import asset_server
        sys.argv = ["asset_server.py", port]
        asset_server.main()
        return 0
    return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--apply-update" in argv:      # the zip build's swap step, run from the staged new version
        return updater.main_apply(argv)
    if "--self-test" in argv:
        i = argv.index("--self-test")
        return self_test(argv[i + 1] if i + 1 < len(argv) else os.path.join(LAYOUT.logs, "self-test.txt"))
    if "--run" in argv:
        return run_tool(argv)
    _windows_app_id()
    startup(argv)
    app = Launcher()
    if "--updated" in argv:
        app.after(1200, lambda: app.notice(f"Open Vanilla is up to date: version {app.version}.", GREEN, 8))
    elif "--update-failed" in argv:
        app.after(1200, lambda: app.notice("The update couldn't be applied (see Logs\\update.log). It will try again.", RED, 10))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
