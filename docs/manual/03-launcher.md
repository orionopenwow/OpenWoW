slug: launcher
title: The launcher
kicker: Chapter 3 · Play
summary: The Windows launcher page by page: Home and PLAY, client setup, the Workshop, realms, account, settings, updates, and where your files live.

## Install {#install}

Download from the [home page](../index.html) (**Desktop Client**):

- `OpenVanilla-Setup-<version>.exe`: the installer (recommended). It installs for your user only, no admin needed, and updates itself.
- `OpenVanilla_<version>_Win64.zip`: a portable copy. Unzip anywhere and run `OpenVanilla.exe`; your data stays beside it.

Needs Windows 10 or 11, 64-bit. Run `OpenVanilla.exe`, never `Game\Open Vanilla Game.exe` directly.

## Home and the PLAY button {#home}

Home has one **PLAY** button. The switch at the bottom left picks how you play:

| Mode | PLAY does |
| --- | --- |
| **Online** | Starts the game client and signs you in to the selected realm |
| **Solo** | Starts your own offline realm and logs you in ([Play Solo](solo.html)) |
| **Browser** | Opens the realm's browser client in its own window |

Browser realms such as Vanilla Remastered (`play.openvanilla.app`) open no game ports to the internet, only their website. In Online mode the launcher plays them through that website: it signs you in, starts a private connection on your PC and points the game at it (the status line says **Plays through the realm's website**). Keep the launcher open while you play; with "close when the game starts" on, it minimises instead. On Linux and macOS, `WoW.exe` runs through Wine.

The bar above PLAY says what's ready or missing, for example **READY TO PLAY**, **CHOOSE YOUR GAME'S DATA FOLDER**, **YOUR WOW FOLDER NEEDS A FIX** or **SERVER OFFLINE**. Pressing PLAY fixes what it can. In Online mode the **▾** menu next to the client picks which client to use, and ends with **More clients in Workshop ›**. News, Discord and Support buttons sit around it.

## Set up Vanilla Client v1.3 {#client-setup}

The launcher's game setup page (it opens when PLAY can't find a client) has two choices:

- **Install a fresh copy → Download & install:** downloads Vanilla Client v1.3 from the Internet Archive (a few GB; it resumes if interrupted). Open Vanilla doesn't host Blizzard's files.
- **I already have it → Select existing folder:** pick the folder with `WoW.exe`. The launcher checks it and never changes the game's files.

The checker needs build **5875** and the eleven standard archives in `Data` (dbc, speech, fonts, interface, misc, sound, wmo, terrain, texture, model, patch). If one is missing or damaged it says so ("Missing texture.MPQ", "This is build 4297; Open Vanilla needs Vanilla Client v1.3 (build 5875)") and offers to pick another folder. When you press PLAY it writes `realmlist.wtf` for you, keeping a backup of the old one.

## The Workshop page {#workshop-page}

Tabs: **Addons**, **Projects**, **Clients**, **Installed** (and **GitHub** in Advanced mode).

- **Addons:** browse and install. Installs go into `AddOns\Enabled` and are used by every client you play with.
- **Projects:** community projects and forks from the directory.
- **Clients:** add or remove game clients (**Add to my clients**, **Download**, **Open clients.txt**).
- **Installed:** your addons, with **Enable/Disable** each, **Install from .zip** and **Open folder**.

Compatibility labels: **Works**, **Partly**, **Needs fixes**, **Not checked**, and **Ours** for the Open Vanilla addons. Install buttons on the website open the launcher directly (they use `openvanilla://workshop/install/...` links) and every download is checked against its fingerprint. Full details in [Publish to the Workshop](workshop.html#install).

> **Note:** With the browser client selected, the page tells you the browser manages its own addons.

## Realms {#realms-page}

**Realm browser**, **My servers** and **Community list**, plus the invite box. See [Realms and friends](realms.html).

## Account {#account-page}

**Sign in to Open Vanilla** has two ways in, the same for new and returning players. **Continue with Google** opens Google's page in your browser; the first time, the realm makes your account, and the launcher keeps your **Hero Key**. **Have a Hero Key?** paste the line that starts with `ovk1` (or **Load the key file**) and press **Sign in**: no browser and no password. The launcher keeps the key encrypted on this PC and uses it whenever you need signing in (PLAY while signed out, an expired sign-in). Signed in, **Your Hero Key** has **Save a copy** and **Copy**; an account that made its key elsewhere can paste it once, or make a new one (the old one stops working). **Forget it on this PC** removes it. Guests and realms with their own passwords: **Guest or a realm password? Sign in another way ›**, with **Remember me on this PC (saved encrypted)**.

## Settings {#settings}

| Section | What's there |
| --- | --- |
| Account & security | Forget saved password, forget trusted servers, ask before sending your password to a community server |
| Game clients | Your clients and which one PLAY uses |
| Folders | Open the data, addons, screenshots and **logs** folders |
| Launcher | Close when the game starts, start muted, animated background, particles, Windows title bar, browser window full screen |
| Downloads | Update in the background, and (Advanced) torrent seeding |
| Privacy | Share what you're listening to (off by default) |
| AI (optional) | Set up an AI workspace: see [Connect an AI](ai.html#setup) |

**Advanced** (off by default) shows client download links, GitHub search and torrent seeding. **Clear all local data…** resets the launcher. The launcher sends no analytics or crash reports.

## Updates {#updates}

The launcher checks for updates by itself and ignores anything that isn't signed by Open Vanilla's release key or is older than what you have. Updates download quietly in the background ("Downloading update 42%"), are checked against their fingerprint, and then a gold **UPDATE READY · RESTART** button appears above PLAY. Updating replaces only program files: your addons, settings, realms and screenshots are never touched. If an update fails, it says so and tries again next time (details in `Logs\update.log`).

## Where your files live {#folders}

Your **data folder** is `%LOCALAPPDATA%\OpenVanilla` for the installer (an install from before the rename keeps its older data folder), or the folder beside `OpenVanilla.exe` for the zip.

| Folder | What's in it |
| --- | --- |
| `AddOns\Enabled`, `AddOns\Disabled` | Your addons, on and off |
| `Realms\Solo`, `Realms\Hosted` | Your offline and hosted realms |
| `Screenshots`, `Logs`, `Backups` | As named; logs are what to attach to a bug report |
| `Settings\settings.json` | Launcher settings |
| `Cache\` | Live content, update downloads |
| `clients.txt` | Extra game clients you added by hand |

Program files (`OpenVanilla.exe`, `app\`, `Game\`, `Server\`) are replaced by updates; don't keep anything of yours there. The engine keeps its game settings and saved variables in `Game\benilla-config`.

## Help and support {#help}

The **Help** medallion has four cards: Playing, Play Solo, Hosting, Folders & Updates. **Support the realm** opens the tip jar ([Tips](community.html#tips)). And this manual is always one click away from the website.
