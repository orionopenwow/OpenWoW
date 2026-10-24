"""Build the Open Vanilla client repack.

    python build_repack.py                      # build engine + launcher, assemble, zip
    python build_repack.py --engine-repo PATH   # build the engine from another checkout (e.g. kind-fermi)
    python build_repack.py --engine-exe PATH    # use an engine binary you already built
    python build_repack.py --publish            # also copy the zip + manifest to www/downloads

What goes in (layout 2, see launcher/layout.py and docs/LAUNCHER.md):
    OpenVanilla.exe              the launcher (openvanilla_launcher.py frozen with PyInstaller --onedir): the one
                             thing players run. Play Solo (play_local.py, spp.py), Host for friends
                             (launcher/p2p), the Workshop, the updater and the dedicated-server modules
                             (server_control, asset_server, studio) are all frozen in; nothing is a
                             separate download.
    app/                     the launcher's internals (--contents-directory app), plus
      app/data/              defaults.json, version.json, patch_notes.json, links.txt (shipped defaults)
      app/addons/            the Classic+ addons; the launcher copies them into AddOns/Enabled
      app/agent/             the AI starter kit (agent/): Settings > AI copies it into the user-data folder
    Game/Open Vanilla Game.exe the engine, a benilla player build (cargo --profile ship --no-default-features)
    Server/www/              the realm website the dedicated server's web backend serves
    links.txt                the player's own overrides (every line commented out to start with)
    LICENSES/  README.txt
  zip only (the installer keeps user data in %LOCALAPPDATA%\\OpenVanilla instead):
    AddOns/Enabled  AddOns/Disabled  Realms/Solo  Realms/Hosted  Screenshots  Logs  Backups

What never goes in: MPQs, extracted game data, Blizzard's FrameXML/GlueXML or its signed
blizzard_* addons. Players point the launcher at their own 1.12.1 install. The final check
refuses to zip a package that contains any of those.
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo root (this file is in packaging/)
DEFAULT_ENGINE_REPO = os.path.join(os.path.expanduser("~"), "Desktop", "benilla-main", "benilla-main")
ADDON_SRC = os.path.join(HERE, "Data", "Interface", "AddOns")
LAUNCHER_SRC = os.path.join(HERE, "launcher")
RELEASE = os.path.join(HERE, "release")
WWW_DOWNLOADS = os.path.join(HERE, "www", "downloads")
SETTINGS = os.path.join(HERE, "launcher_settings.json")

# Anything matching these must not ship (Blizzard game data and interface code).
FORBIDDEN = ["*.mpq", "*.toc.sig", "*/blizzard_*/*", "*/gluexml/*", "*/framexml/*",
             "*.blp", "*.m2", "*.wmo", "*.adt", "*.dbc"]


def log(msg):
    print(f"[repack] {msg}", flush=True)


def die(msg):
    print(f"[repack] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ engine

def build_engine(repo):
    if not os.path.isfile(os.path.join(repo, "Cargo.toml")):
        die(f"No Cargo.toml in {repo}. Pass --engine-repo to your benilla/kind-fermi checkout.")
    if not shutil.which("cargo"):
        die("cargo is not on PATH. Install Rust from https://rustup.rs (with the MSVC build tools).")
    cmd = ["cargo", "build", "-p", "benilla", "--profile", "ship", "--no-default-features"]
    log("building engine: " + " ".join(cmd) + f"   (in {repo}; first build takes a while)")
    r = subprocess.run(cmd, cwd=repo)
    if r.returncode != 0:
        die("engine build failed (see cargo output above).")
    exe = os.path.join(repo, "target", "ship", "benilla.exe" if os.name == "nt" else "benilla")
    if not os.path.isfile(exe):
        die(f"cargo finished but {exe} is missing.")
    return exe


def engine_licenses(repo, dst):
    os.makedirs(dst, exist_ok=True)
    found = 0
    for name in ("LICENSE-MIT", "LICENSE-APACHE"):
        p = os.path.join(repo, name)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dst, f"benilla-{name}.txt"))
            found += 1
    tp = os.path.join(repo, "third_party")
    if os.path.isdir(tp):
        for comp in os.listdir(tp):
            for f in os.listdir(os.path.join(tp, comp)):
                if f.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT")):
                    shutil.copy2(os.path.join(tp, comp, f), os.path.join(dst, f"{comp}-{f}.txt"))
                    found += 1
    ofl = os.path.join(LAUNCHER_SRC, "assets", "launcher", "fonts", "Cinzel-OFL.txt")
    if os.path.isfile(ofl):
        shutil.copy2(ofl, os.path.join(dst, "Cinzel-font-OFL.txt"))
    if not found:
        log("warning: no licence files found in the engine repo; add them before publishing.")


# ------------------------------------------------------------------ launcher

# Modules the launcher imports lazily (importlib, try/except, or by name at run time), so PyInstaller
# must be told to freeze them in: Host for friends, Play Solo, the Workshop, the updater, live content
# and the dedicated server. A missing one used to mean "Hosting isn't available in this build".
HIDDEN_IMPORTS = ("play_local", "workshop", "nowplaying", "layout", "updater", "fetch", "live_content", "spp", "home_logic", "game_clients",
                  "server_host", "server_control", "authcheck", "asset_server", "account", "wow_import", "ed25519",
                  "launcher_art", "ai_setup", "aiohttp", "pymysql", "tls", "certifi")
COLLECT_SUBMODULES = ("p2p", "studio")
LAUNCHER_NAME = "OpenVanilla"      # OpenVanilla.exe
OLD_LAUNCHER_EXE = "OpenWoW.exe"        # bridge twin: launchers before the rename only update this name
ENGINE_NAME = "Open Vanilla Game.exe"
CONTENTS_DIR = "app"               # PyInstaller >= 6: the internals folder beside the exe


def package_modules(pkg):
    """Every module of a package that lives in launcher/ or the repo root (p2p, studio)."""
    for base in (LAUNCHER_SRC, HERE):
        root = os.path.join(base, pkg)
        if os.path.isfile(os.path.join(root, "__init__.py")):
            out = []
            for d, dirs, files in os.walk(root):
                dirs[:] = sorted(x for x in dirs if x != "__pycache__" and os.path.isfile(os.path.join(d, x, "__init__.py")))
                rel = os.path.relpath(d, base).replace(os.sep, ".")
                out += [rel] + [f"{rel}.{f[:-3]}" for f in sorted(files) if f.endswith(".py") and f != "__init__.py"]
            return out
    return []


SITE_TEXT = (".html", ".css", ".js", ".json", ".txt", ".xml", ".webmanifest", ".svg", ".md", ".py", ".lua")


def unused_site_assets(www):
    """Images under www/assets that nothing refers to: old drafts, mockups and earlier logo versions.

    They stay in the repo and on the website; only the self-hosting copy in the zip (Server/www)
    leaves them out. An image counts as used if its file name, or its name without the extension,
    appears in any text file of the site or the repo's Python and Lua, so names built in code
    ('assets/premise_' + key + '.jpg') keep their whole family. Returns normcased absolute paths."""
    text = []
    for top in (www, LAUNCHER_SRC, HERE):
        for d, dirs, files in os.walk(top):
            dirs[:] = [x for x in dirs if x not in (".git", "node_modules", "__pycache__", "dist", "build",
                                                     "release", "downloads", "_local")]
            if top != www and os.path.commonpath([os.path.abspath(d), os.path.abspath(www)]) == os.path.abspath(www):
                continue
            for f in files:
                if f.endswith(SITE_TEXT):
                    try:
                        with open(os.path.join(d, f), encoding="utf-8", errors="ignore") as fh:
                            text.append(fh.read())
                    except OSError:
                        pass
        if top == HERE:
            break
    blob = "\n".join(text)
    families = set(re.findall(r"assets/(?:[\w-]+/)*([a-z]+_)['\"]?\s*\+", blob))
    families |= set(re.findall(r"assets/(?:[\w-]+/)*([a-z]+_)\$\{", blob))
    unused = set()
    assets = os.path.join(www, "assets")
    for d, _, files in os.walk(assets):
        for f in files:
            stem = os.path.splitext(f)[0]
            if f in blob or stem in blob or any(stem.startswith(fam) for fam in families):
                continue
            unused.add(os.path.normcase(os.path.join(d, f)))
    return unused


# AVIF support (~4 MB zipped): the launcher never opens an .avif; PIL skips a missing plugin.
EXCLUDE_MODULES = ("PIL._avif", "PIL.AvifImagePlugin")


def pyinstaller_args(work, ico):
    """The PyInstaller command line for the launcher (one exe + app/ folder)."""
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
           "--contents-directory", CONTENTS_DIR,
           "--name", LAUNCHER_NAME, "--icon", ico,
           "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "build"),
           "--specpath", work,
           "--add-data", f"{os.path.join(LAUNCHER_SRC, 'assets', 'launcher')}{sep}assets/launcher",
           "--paths", LAUNCHER_SRC, "--paths", HERE]
    for m in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", m]
    for m in EXCLUDE_MODULES:
        cmd += ["--exclude-module", m]
    for m in COLLECT_SUBMODULES:
        cmd += ["--collect-submodules", m]
        # --collect-submodules runs in a subprocess that doesn't see --paths (p2p lives in launcher/), so
        # name every module of the package too.
        for m2 in package_modules(m):
            cmd += ["--hidden-import", m2]
    if os.path.isdir(os.path.join(HERE, "solo", "templates")):   # Play Solo's config templates (play_local)
        cmd += ["--add-data", f"{os.path.join(HERE, 'solo', 'templates')}{sep}solo/templates"]
    cmd.append(os.path.join(LAUNCHER_SRC, "openvanilla_launcher.py"))
    return cmd


def build_launcher(work, onedir=True):
    """Freeze the launcher. Returns the folder holding OpenVanilla.exe and app/."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        log("installing PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pyinstaller>=6", "pillow", "aiohttp", "pymysql"])
    import PyInstaller
    if int(PyInstaller.__version__.split(".")[0]) < 6:
        die(f"PyInstaller {PyInstaller.__version__} is too old: 6.0 or newer is needed (--contents-directory).")
    sys.path.insert(0, LAUNCHER_SRC)
    import launcher_art
    ico = os.path.join(work, "openvanilla.ico")
    launcher_art.emblem(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    log("freezing launcher with PyInstaller…")
    r = subprocess.run(pyinstaller_args(work, ico))
    if r.returncode != 0:
        die("PyInstaller failed.")
    folder = os.path.join(work, "dist", LAUNCHER_NAME)
    if not os.path.isdir(os.path.join(folder, CONTENTS_DIR)):
        die(f"PyInstaller finished but {folder}{os.sep}{CONTENTS_DIR} is missing.")
    return folder


# ------------------------------------------------------------------ addons

def read_toc(folder):
    name = os.path.basename(folder)
    for f in os.listdir(folder):
        if f.lower() == name.lower() + ".toc":
            meta = {}
            with open(os.path.join(folder, f), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("##"):
                        k, _, v = line[2:].partition(":")
                        meta[k.strip().lower()] = v.strip()
            meta["title"] = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", meta.get("title", name)).replace("Classic+", "").strip()
            return meta
    return None


def is_own_addon(folder, meta):
    """Ours = no Blizzard signature file and an Open Vanilla/Classic+ author tag."""
    if os.path.basename(folder).lower().startswith("blizzard_"):
        return False
    if any(f.lower().endswith(".toc.sig") for f in os.listdir(folder)):
        return False
    author = meta.get("author", "").lower()
    return "x-classicplus" in meta or author in ("open vanilla", "openvanilla")


def copy_addons(dst):
    if not os.path.isdir(ADDON_SRC):
        alt = os.path.join(HERE, "Data", "interface", "addons")
        src = alt if os.path.isdir(alt) else None
    else:
        src = ADDON_SRC
    if not src:
        die(f"addon source not found: {ADDON_SRC}")
    shipped = []
    for name in sorted(os.listdir(src), key=str.lower):
        folder = os.path.join(src, name)
        if not os.path.isdir(folder):
            continue
        meta = read_toc(folder)
        if not meta or not is_own_addon(folder, meta):
            continue
        shutil.copytree(folder, os.path.join(dst, name),
                        ignore=shutil.ignore_patterns("*.bak", "*.tmp", "__pycache__"))
        shipped.append((name, meta))
    log(f"addons: {', '.join(n for n, _ in shipped)}")
    return shipped


# ------------------------------------------------------------------ text files

def patch_notes(version, addons, changelog_path):
    sections = []
    if changelog_path and os.path.isfile(changelog_path):
        # CHANGELOG format: "## Section" headers and "- item" lines
        cur = None
        with open(changelog_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if line.startswith("## "):
                    cur = {"title": line[3:].strip(), "items": []}
                    sections.append(cur)
                elif line.lstrip().startswith(("- ", "* ")) and cur is not None:
                    cur["items"].append(line.lstrip()[2:].strip())
    sections.append({
        "title": "Launcher",
        "items": [
            "Redesigned launcher: hand-painted UI kit, animated vortex, floating embers and a living energy bar.",
            "Accounts: sign in, create an account and change your password right in the launcher.",
            "Signed in? PLAY logs you straight into the realm, no login screen.",
            "Pick your game client at the bottom left: Open Vanilla, the browser version, or a stock 1.12.1 / 3.3.5a client.",
            "Servers: your list plus the community directory; Mods: community addons and repacks; GitHub search built in.",
            "Update check with a real download progress bar and checksum verification.",
        ],
    })
    feature = [(n, m) for n, m in addons if m.get("x-classicplus", "").lower() != "core" and not n.startswith("!")]
    sections.append({
        "title": f"Classic+ addons ({len(feature)})",
        "items": [f"{m.get('x-classicplus') or m['title']}: {m.get('notes', '')}".strip(": ") for n, m in feature],
    })
    names = [m.get("x-classicplus") or m["title"] for _, m in feature]
    highlights = (sections[0]["items"][:2] if len(sections) > 2 else [])
    highlights += [sections[-2]["items"][0], sections[-2]["items"][1],
                   f"{len(names)} Classic+ addons: " + ", ".join(names[:5]) + ("…" if len(names) > 5 else "")]
    return {
        "version": version,
        "date": datetime.date.today().isoformat(),
        "highlights": highlights[:4],
        "sections": sections,
    }


def readme(version, addons):
    feature = [(n, m) for n, m in addons if m.get("x-classicplus", "").lower() != "core" and not n.startswith("!")]
    lines = [
        "=" * 64,
        f"  Open Vanilla Classic+  ·  version {version}",
        "=" * 64,
        "",
        "START HERE: double-click OpenVanilla.exe. It is the only program you need to run.",
        "",
        "WHAT YOU NEED",
        "  Your own English World of Warcraft 1.12.1 (build 5875) install. Open Vanilla reads it and never",
        "  changes its game data. No Blizzard files are included here.",
        "",
        "HOW TO PLAY",
        "  1. Run OpenVanilla.exe (tip: right-click it -> Send to -> Desktop).",
        "  2. Pick a mode in the switch at the bottom left: ONLINE (the Open Vanilla realm), SOLO (your own",
        "     world on this PC with playerbots: SPP Classics, which the launcher downloads, sets up",
        "     and starts for you) or BROWSER.",
        "  3. Press PLAY. If something is missing (your WoW 1.12.1 folder, Solo's one-time setup), the",
        "     bar above PLAY says what, and pressing PLAY fixes it.",
        "",
        "  OpenVanilla.exe starts the game (Game\\Open Vanilla Game.exe, or your own WoW.exe) for you: don't run",
        "  the game exe directly. To run your own realm, get OpenVanilla-Server.zip (openvanilla.app/host.html).",
        "",
        "  Updates download by themselves: when the launcher shows 'Update ready', press it and",
        "  Open Vanilla restarts on the new version. News and links refresh without any update.",
        "",
        "FOLDERS",
        "  OpenVanilla.exe          the launcher: start here",
        "  app\\                 the launcher's own files (don't change them)",
        "  Game\\                the Open Vanilla engine (Open Vanilla Game.exe, started by OpenVanilla.exe) and its",
        "                       settings (benilla-config)",
        "  AddOns\\Enabled       addons every game client loads; Workshop installs land here",
        "  AddOns\\Disabled      addons you switched off",
        "  Realms\\Solo          Play Solo (SPP Classics) once you have used it",
        "  Realms\\Hosted        realms you host for friends",
        "  Server\\              the realm website (running your own realm: OpenVanilla-Server.zip)",
        "  Screenshots, Logs, Backups, Settings, Cache",
        "                       (Settings -> Folders in the launcher opens each of them)",
        "  links.txt            your own link overrides (see the comments inside)",
        "",
        "  With the installer, your addons, realms, screenshots, logs and settings live in",
        "  %LOCALAPPDATA%\\OpenVanilla instead, so reinstalling never touches them.",
        "",
        f"INCLUDED CLASSIC+ ADDONS ({len(feature)})",
    ]
    for n, m in feature:
        lines.append(f"  - {m.get('x-classicplus') or m['title']}: {m.get('notes', '')}")
    lines += [
        "",
        "CREDITS & LICENCES",
        "  The Open Vanilla engine is built on benilla (https://github.com/samwhosung/benilla),",
        "  MIT / Apache-2.0. Play Solo uses SPP Classics (https://github.com/celguar/spp-classics-cmangos),",
        "  downloaded from its own releases when you first use it. Licence texts are in LICENSES.",
        "  World of Warcraft is a trademark of Blizzard Entertainment, Inc. Open Vanilla is an",
        "  independent fan project, not affiliated with or endorsed by Blizzard.",
        "",
    ]
    return "\r\n".join(lines)


def user_links(links_text):
    """The player's links.txt: every setting commented out (the real defaults ship in app/data/links.txt),
    so a later update's new defaults are never hidden behind a stale copy."""
    out = ["# Your Open Vanilla link overrides. The launcher's defaults are in app\\data\\links.txt and updates",
           "# change them; a line you uncomment here wins over them (and over the live content).",
           "# Example: remove the '# ' in front of SPP_URL to use another SPP Classics download.", ""]
    for line in links_text.splitlines():
        t = line.strip()
        if t and not t.startswith(("#", ";")) and "=" in t:
            out.append("# " + t)
        elif t.startswith("# ---"):
            out.append(t)
    return "\r\n".join(out) + "\r\n"


USER_FOLDERS_IN_ZIP = ("AddOns/Enabled", "AddOns/Disabled", "Realms/Solo", "Realms/Hosted", "Screenshots", "Logs", "Backups")


def assemble(out, launcher_dir, engine, version, changelog, engine_repo=None):
    """Lay the release folder out (layout 2). Returns (addons, notes)."""
    for item in os.listdir(launcher_dir):   # OpenVanilla.exe + app/
        src = os.path.join(launcher_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(out, item))
        else:
            shutil.copy2(src, os.path.join(out, item))
    if not os.path.isfile(os.path.join(out, LAUNCHER_NAME + ".exe")) and os.name == "nt":
        die(f"the launcher build has no {LAUNCHER_NAME}.exe")
    if os.path.isfile(os.path.join(out, LAUNCHER_NAME + ".exe")):
        # the rename bridge: an identical copy under the old name, so launchers from before the rename
        # (whose updater only replaces OpenWoW.exe) still update; the new launcher prefers OpenVanilla.exe
        shutil.copy2(os.path.join(out, LAUNCHER_NAME + ".exe"), os.path.join(out, OLD_LAUNCHER_EXE))
    app = os.path.join(out, CONTENTS_DIR)
    if engine:
        os.makedirs(os.path.join(out, "Game"), exist_ok=True)
        shutil.copy2(engine, os.path.join(out, "Game", ENGINE_NAME))
    addons = copy_addons(os.path.join(app, "addons"))
    agent = os.path.join(HERE, "agent")
    if os.path.isdir(agent):   # the AI starter kit; Settings > AI copies it into the user-data folder
        shutil.copytree(agent, os.path.join(app, "agent"), ignore=shutil.ignore_patterns(".*", "__pycache__"))
    data = os.path.join(app, "data")
    os.makedirs(data, exist_ok=True)
    shutil.copy2(os.path.join(LAUNCHER_SRC, "defaults.json"), os.path.join(data, "defaults.json"))
    with open(os.path.join(data, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "built": datetime.datetime.now().isoformat(timespec="seconds")}, f, indent=2)
    notes = patch_notes(version, addons, changelog)
    with open(os.path.join(data, "patch_notes.json"), "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)
    links_src = os.path.join(HERE, "links.txt")
    if os.path.isfile(links_src):
        shutil.copy2(links_src, os.path.join(data, "links.txt"))
        with open(links_src, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(out, "links.txt"), "w", encoding="utf-8", newline="") as f:
            f.write(user_links(text))
    www = os.path.join(HERE, "www")
    if os.path.isdir(www):   # the realm website for the dedicated server's web backend (no download files)
        base_ignore = shutil.ignore_patterns("*.zip", "*.exe", "*.wasm", "*.wasm.*", "*.part", "__pycache__")
        unused = unused_site_assets(www)

        def ignore(d, names):
            skip = set(base_ignore(d, names))
            return skip | {n for n in names if os.path.normcase(os.path.join(d, n)) in unused}
        shutil.copytree(www, os.path.join(out, "Server", "www"), ignore=ignore)
    os.makedirs(os.path.join(out, "Server"), exist_ok=True)
    with open(os.path.join(out, "Server", "README.txt"), "w", encoding="utf-8", newline="") as f:
        f.write("This is the realm website's files. Running your own realm is a separate download:\r\n"
                "OpenVanilla-Server.zip (openvanilla.app/host.html). The launcher is for playing.\r\n")
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8", newline="") as f:
        f.write(readme(version, addons))
    engine_licenses(engine_repo or "", os.path.join(out, "LICENSES"))
    return addons, notes


def read_version():
    """The release version: the VERSION file (dev\\Release.bat sets it), else launcher/version.json."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            v = f.read().strip()
        if v:
            return v
    except OSError:
        pass
    return json.load(open(os.path.join(LAUNCHER_SRC, "version.json"))).get("version", "0.0.0")


def public_url():
    links_file = os.path.join(HERE, "links.txt")
    if os.path.isfile(links_file):
        try:
            with open(links_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("PORTAL_URL") and "=" in line:
                        _, val = line.split("=", 1)
                        if val.strip():
                            return val.strip().rstrip("/")
        except Exception:
            pass
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f).get("public_url", "").rstrip("/")
    except (OSError, ValueError):
        return ""


# ------------------------------------------------------------------ checks & zip

def forbidden_files(root):
    bad = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/")
            if any(fnmatch.fnmatchcase("/" + rel.lower(), p) for p in FORBIDDEN):
                bad.append(rel)
    return bad


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_zip(src_dir, zip_path, empty_dirs=()):
    """Zip src_dir under its own name. empty_dirs (relative, /-separated) become folder entries so the
    portable zip shows AddOns, Realms, Screenshots… from the start."""
    top = os.path.basename(src_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, files in os.walk(src_dir):
            for f in sorted(files):
                full = os.path.join(dirpath, f)
                z.write(full, os.path.join(top, os.path.relpath(full, src_dir)))
        for d in empty_dirs:
            z.writestr(top + "/" + d.strip("/") + "/", "")


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default=None, help="version string (default: the VERSION file)")
    ap.add_argument("--engine-repo", default=os.environ.get("OPENVANILLA_ENGINE_REPO", DEFAULT_ENGINE_REPO))
    ap.add_argument("--engine-exe", help="use this prebuilt engine binary instead of building")
    ap.add_argument("--no-engine", action="store_true", help="build without the engine (the stock 1.12.1 client only)")
    ap.add_argument("--launcher-dir", help="use this prebuilt launcher folder (OpenVanilla.exe + app/) instead of PyInstaller")
    ap.add_argument("--changelog", default=os.path.join(HERE, "CHANGELOG.md"),
                    help="optional notes file merged into patch notes (## Section / - item)")
    ap.add_argument("--publish", action="store_true", help="copy zip, version.json and patch notes to www/downloads")
    ap.add_argument("--onedir", action="store_true", help="accepted for older scripts; the launcher is always OpenVanilla.exe + app/")
    args = ap.parse_args()

    if args.publish:  # never publish a build that still points players at placeholder addresses
        for rel in ("links.txt", os.path.join("launcher", "defaults.json")):
            with open(os.path.join(HERE, rel), encoding="utf-8") as f:
                left = [ln.strip() for ln in f if not ln.lstrip().startswith("#")
                        and (".invalid" in ln or "set-invite-here" in ln)]
            if left:
                die(f"{rel} still has placeholders (run set_realm.py first):\n  " + "\n  ".join(left[:5]))
    version = args.version or read_version()
    name = f"OpenVanilla_{version}_Win64"
    out = os.path.join(RELEASE, name)
    work = os.path.join(RELEASE, "_build")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    os.makedirs(work, exist_ok=True)

    # 1 · binaries
    engine = None
    if not args.no_engine:
        engine = args.engine_exe or build_engine(args.engine_repo)
        if "keldurn" in os.path.basename(engine).lower():
            die("refusing to ship a Keldurn binary as the engine; build the engine from source instead.")
        log(f"engine: {engine}")
    launcher = args.launcher_dir or build_launcher(work)
    log(f"launcher: {launcher}")

    # 2 · layout: OpenVanilla.exe, app/ (+ data, addons), Game/, Server/, links.txt, README.txt, LICENSES
    addons, notes = assemble(out, launcher, engine, version, args.changelog, args.engine_repo)

    # 4 · safety check, then zip
    bad = forbidden_files(out)
    if bad:
        die("package contains game files that must not ship:\n  " + "\n  ".join(bad[:20]))
    zip_path = os.path.join(RELEASE, name + ".zip")
    make_zip(out, zip_path, USER_FOLDERS_IN_ZIP)
    digest = sha256(zip_path)
    with open(zip_path + ".sha256", "w") as f:
        f.write(f"{digest}  {os.path.basename(zip_path)}\n")
    size = os.path.getsize(zip_path)
    log(f"built {zip_path} ({size / 1e6:.1f} MB)  sha256 {digest}")

    if args.publish:
        os.makedirs(WWW_DOWNLOADS, exist_ok=True)
        shutil.copy2(zip_path, os.path.join(WWW_DOWNLOADS, os.path.basename(zip_path)))
        base = public_url() + "/downloads" if public_url() else "/downloads"
        manifest = {"version": version, "url": f"{base}/{os.path.basename(zip_path)}", "size": size,
                    "sha256": digest, "patch_notes_url": f"{base}/patch_notes.json"}
        with open(os.path.join(WWW_DOWNLOADS, "version.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        with open(os.path.join(WWW_DOWNLOADS, "patch_notes.json"), "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2)
        log(f"published to {WWW_DOWNLOADS} (version.json points launchers at the new zip)")

        # keep the community directory's repack entries pointing at the newest files
        dir_path = os.path.join(HERE, "www", "community", "directory.json")
        try:
            with open(dir_path, encoding="utf-8") as f:
                directory = json.load(f)
        except (OSError, ValueError):
            directory = {"servers": [], "mods": [], "repacks": []}
        repacks = [r for r in directory.get("repacks", []) if r.get("kind") not in ("client", "server")
                   or not any(n in r.get("name", "") for n in ("Open Vanilla", "OpenWoW"))]   # replaces ours, old name too
        repacks.insert(0, {"name": "Open Vanilla client (Windows)", "kind": "client", "client": "1.12.1", "version": version,
                           "url": manifest["url"], "size": size,
                           "description": "OpenVanilla.exe: play online or solo (SPP Classics). Needs your own WoW 1.12.1 data."})
        directory["repacks"] = repacks
        directory["updated"] = datetime.date.today().isoformat()
        os.makedirs(os.path.dirname(dir_path), exist_ok=True)
        with open(dir_path, "w", encoding="utf-8") as f:
            json.dump(directory, f, indent=2)
        log("community directory updated (www/community/directory.json)")


if __name__ == "__main__":
    main()
