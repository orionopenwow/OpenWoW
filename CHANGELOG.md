# Open Vanilla changelog
(build_repack.py turns the newest sections into the launcher's patch notes: "## Section" headers, "- item" lines.)

## New in 1.54.1
- Hotfix: launcher sign-in certificates chain to ISRG Root X1 (RSA); the launcher trusts Mozilla's roots too.
- Hotfix: a game button clicks when you lift after it shows pushed (slow phones).
- Hotfix: phone taps click for real (game-tick taps); Herald travels on foot.

## New in 1.54.0
- Launcher sign-in: Continue with Google and the Hero Key the launcher keeps, no Discord sign-in (realm patch 0042).

## New in 1.53.1
- Duels: no more "attempt to index global DuelsBars (a nil value)" (Bars.lua:184): every saved table (DuelsBars, DuelsLoadouts, DuelsIntro, DuelsPitPrefs) is made again before use, when the client set it to nil after….

## New in 1.53.0
- Duels on the realm lists: the launcher plays it in the desktop game (through its website, like the official realm), the site's realm list has a Duels row; live content carries both official realms so installed….
- Realm client: the ground guard (no falling through ground still streaming in) and a software-GPU warning on the play page.

## New in 1.52.0
- Aa.
- Realm images: labelled with this repo (org.opencontainers.image.source), so openvanilla-realm and openvanilla-mangos show under the repo's Packages with a description.
- Release workflow: every release is marked Latest (Latest was stuck on 1.30.8, so the site's downloads and version.json stayed there).
- Releases build again: the generated-files check no longer depends on line endings (Duels patch-Z packs LF; Workshop zips compared LF), and patch-Z rebuilt for Boss Fights.
- Launcher: the official realm's status from its /healthz (it has no /api/status and no game ports, so it showed Offline while up); world server down shows PARTLY UP.
- Repo basics (MIT LICENSE, CONTRIBUTING, issue forms); no falling leaves on the site.
- Boss Fights: the run's extras (mangos 0062): quick reset after a wipe, pull timer and ready check, end screen with meters and a death recap, ghost split, practice/hardcore/story, weekly twists, Raid Roulette, Dragon….

## New in 1.51.0
- Generated files rebuilt for the release.
- Boss Fights: Onyxia bot tactics round 2 (mangos 0063: an off-tank on whelps, spread in the air, hold until the tank has her after landing, Berserker Rage against the fear); Bot Captain panel for the leader; on-screen….
- Duels: the pit (mangos 0061): the record, announcer, cards, winner stays on, crowd, hourly brawl, challenges, Weekly Duel Cup, sparring dummy; the site's live ladder, pit now, cup bracket and a stream overlay.
- Boss Fights site and Herald: this week's twist, fastest this week, live runs, People/With bots/Hardcore boards, latest runs, Hall of Fame, a run page (bossfights-run.html); write_live v2 with per-run files; Herald….
- Duelz.
- Armory: a gear picker with sources and filters, tier sets, my sets, talent builds, a preview with stats (860x500); icons show (the 9th return of GetItemInfo, a ? and a warm-up for unseen items); item names hang under….
- Boss Fights: no trash in Onyxia's Lair, the raid starts in her room 30 yd back (mangos 0060, StartAtBoss); a QUEUE tab under ARMORY.
- Discord invite is discord.gg/hVeUxYwbkr everywhere.

## New in 1.50.0
- Bossfights_check.sh --real: a fight that never started fails (it passed with every fight step skipped).
- Boss Fights: ONLINE (BOSSFIGHTS_OPEN = 1), a basic version for friends to try.
- Discord off switch: no Discord sign-in, Herald's Discord bot stopped, launcher sign-in without Discord.
- Yes.
- Boss Fights: the bots fight Onyxia (mangos 0059), a softer setting for bot-heavy raids (off), a daily real-fight self-test.
- Boss Fights: a bot-filled raid pops (0058: combat in the hangout no longer cancels it; a cancelled pop logs who and why); the addon asks the realm's hello again if it was missed (window and Queue up).
- Desktop game on the official realm through its website (realm 0039 + launcher bridge).

## New in 1.49.0
- Bots never talk in chat channels (mangos 0057: World, General, Trade, LocalDefense, LFG, any account); bot fill sets every bot broadcast chance to 0. Boss Fights bot-fill login fix renumbered 0056 (0055 is Herald's).
- Boss Fights 0055: new fill bots log in once they are saved (they were made but never came: "did not come within a minute").

## New in 1.48.0
- README: how to run Vanilla Forge (Vanilla Forge.bat, portable zip, installer, from source), in Start here and its own section.

## New in 1.47.0
- A.
- Herald quests straight through and rides his mount (mangos 0055).

## New in 1.46.0
- A.
- Boss Fights 0054: bots fill the raid (off until bossfights_up.sh botfill on).
- Vanilla Forge 0.9.1: a portable zip beside the installer, Vanilla Forge.bat opens it in one double-click; the release build runs again (Model Porter tests no longer load aiohttp's plugin).

## New in 1.45.0
- A.
- Boss Fights: the site's Fight now reaches the game on slow loads (the play page keeps handing it over for ~3 min, not 54 s); no "join Boss Fights first" line on arrival.

## New in 1.44.0
- A.
- Bossfights_up.sh update runs duels_up.sh update first: the client patch with the Boss Fights addon and the play page reach the browser.
- Boss Fights: Fight now opens duels.openvanilla.app (same realm) until bossfights.openvanilla.app has DNS.
- Boss Fights 0053: a leaver who queues again is told about the leaver lock (not "only the leader"); found by the first self-test run.
- Bossfights_up.sh: pull the newest world server image before the restart, so update brings the new Boss Fights code.
- Discord: the new invite (discord.gg/9KGdUDGnv9) everywhere: site, launcher, links, realm play page, in-game welcome (patch-Z for Classic+, Warfront and Duels).

## New in 1.43.0
- A.
- Boss Fights: raiders arrive ready (level 60, raid talents, every gear set, stocked bags, all bars filled).
- Boss Fights self-test: two server-made test accounts run every step on their own.
- Duels: the hangout bots and the bot system off again (about 1 GB, and the bots could not log in: no ai_playerbot tables).
- Duels: the bug report and World chat log tables in its characters database (no more ERROR 1146).
- Boss Fights on the site: its own page first (like Duels), playable in testing.
- Boss Fights: its own address (bossfights.openvanilla.app) and no realm list.

## New in 1.42.0
- Work in progress.
- GM console: a Duels tab (its own copy on 8091, GMDESK console account), Make GM, Send gold, Ban character; duels_up.sh gm NAME.
- Duels: General and World chat in the arena; the hangout's nine player bots on.
- Boss Fights' world server patch is 0050 (0040 and 0041 went to Duels in the meantime).
- Boss Fights (testing, off by default): raids by queue from the Gurubashi hangout, a fresh raid copy per group, five tiers.
- Duels: the dummies never take damage or die; two more, north and south of the pit.
- Duels_up.sh: put back Duels Lite and everything 4e717e7 overwrote; keep only its combos.json mount.
- Duels: offer only the race/class pairs its world server can make.

## New in 1.41.0
- Work in progress.
- Vanilla Forge: the download is live (no longer Coming soon).
- Duels (0039): the realm itself gives the class's spells, every gear set in the bags and a worn set on arrival, no addon needed.
- Duels: no window pops up on arrival (no queue window, no Warfront window or PvP tab on Duels); a labelled ladder preview with 50 example duelists; Move Anything reaches every frame our addons make, and shows the….
- Duels page: no friend link maker; the Duel button goes to sign-in, then the character screen.
- Duels Lite (0038): the bare Gurubashi arena for now: duel anyone; gear, specs, party, chat; no queue, rooms, bets, bots or transmog (all switched off, not removed); the Duels window, intro and page show only that.
- Duels queue: same-network players meet (unrated), 1v1 always solo, 2v2/3v3 need that party size, refusals said in chat (0037); Transmog grid no longer asks for hundreds of items at once (cached list, background item….
- Duels: kits for every race and class pair (0036: the other faction's kit, unwearable pieces swapped for the nearest wearable); Armory gear page like the first gear picker: named slots with their empty-slot pictures,….
- Duels page: the leaderboard right under the top, the how-it-works blocks gone, one Duel button.
- Duels hangout bots (0035): nine player bots, one per class, wander the pit and stands, AFK a few minutes now and then, and two duel in the middle every few minutes.
- Duels arrives ready (0034): every gear set in the bags and worn from them, class consumables, three specs (one per tree) with template talents, instant switches, own bars and kit per spec; gear changes while queued.
- Duels queue pass: accept window (0031), no auto-queue; cast bars for everyone (0032); practice vs a real player bot (0033); bars at the best rank; Spellbook and Talents apart; Armory minimap button; intro invite….
- Duels: host your own server (rooms) - mangos 0030, Host a server window, ?room= links, Join a server list on the site.
- Transmog art pass: 5 x 4 grid (20 looks a page), quality chips, Quick looks (random, helm, cloak), Free on Duels; Duels' LOOKS tab under ARMORY opens it anywhere.
- Duels page: three ways to fight (queue, friend link maker, servers soon), brackets, a full leaderboard (ladder, by class, streaks, matchups, Duel Gold), Watch and Bet on fights now.
- Sign-in: guest and Google; Discord is a Join our Discord button (realm patch 0038), on both realms.
- Duels: Google and Discord sign-in as on the live realm (the apps copied from live's .env; Discord adds the player to the server).
- Duels: no auto-queue; gear and consumables on arrival; the Armory tab; 2v2/3v3; friend links; the Duels intro; mounts anywhere; the Hero Key saved in the browser.
- Rebuilt generated files: patch-Z (Classic+, Warfront, Duels) with the Duels Armory, bars, betting and the PvP addon; the UI file list; Workshop packages.
- Duels betting in Duel Gold: spectators' pools and the fighters' stakes (compile-checked).
- Mangos 0024: the hangout clears free-for-all with the core's own SetPvPFreeForAll (compile-checked).
- Duels: Gurubashi Arena in Stranglethorn is the hangout (was the Lion's Pride Inn).
- PvP addon (art pass picks): arena card, enemy cooldowns, Big CC rings, DR tracker; Castline's bar big and red when you can't interrupt.
- Duels: the Armory window (paper doll, slot browser worn-first with search and stat change, enchants, kits, saved loadouts, OV1 loadout codes).
- Duels: bars laid out on a new duel body; every transmog look unlocked and free on Duels.
- Realm patch 0036: test that Google stays, between Play now and Discord.
- Phase 0: sign-in puts Play now first, then Google, then Discord (joins the server); Bug | Feedback | Idea tabs.
- Realm: Caddy reaches the live website as ovlive-realm, never the shared name realm.
- Realm: world server memory headroom (3200m), real realm name on the website, memory check.

## New in 1.40.0
- Duels_up.sh: the Duels web service reaches its own database, console and game servers by names only its stack has.
- Duels: a practice bot, the character screen again, a DUELS badge, a 3x larger hangout.
- Duels_up.sh: take the Duels files from the server's checkout, not the stable branch.
- Duels goes live on the website (DUELS_OPEN = 1); duels_up.sh update pulls the new images.
- Duels_up.sh: SQL as the world server's database user; start and update skip db-init.
- Duels: the character screen, every spell on the bars, every weapon skill at max, the inn's ground only.
- Duels_lean.sql: keep gameobject_addon non-empty.
- Duels_up.sh: declare the live game data volume as external in the override.
- Duels_up.sh: SQL as the database container's own root user; update starts realmd and shows the setup token.

## New in 1.39.0
- Realm patch 0035: Duels, straight into the world (?duel=).
- Duels: Gurubashi Arena, the Lion's Pride Inn, spectating, sudden death, Glicko-2.
- Collections: the Mounts tab lists the racial mounts learned as spells.

## New in 1.38.0
- Touch: a game button presses in under the finger and lets out on lift.
- Mangos patch 0023: the racial mount from level 1, the swift one from 40, on every character.
- Hetzner/bots_quiet.sh: the realm's playerbots stop talking in World and every other channel.
- Herald: his refused tries ("Invalid target", "Out of range") stay off the screen while he plays.

## New in 1.37.0
- Players' reports #20-#24: target health number, buff durations, menus on screen, walking over windows, Quest Log button.
- Meters "Window.lua:31: ROW_X (a nil value)": stale addon files on Warfront and Duels, and in the Workshop.

## New in 1.36.0
- Mangos patch 0022: a Star Pouch opened again with its loot all taken is spent, not an empty loot window.
- Herald loots alone; addon files can't be read stale after a deploy; bug reports carry fps and ms.

## New in 1.35.0
- Realm patches 0033-0034: Herald no longer goes AFK or through hills; Alt+Enter full screen.
- Players' reports: the Game Menu button clicks again, one hub at a time, Herald pauses while you shop.
- Server images built ahead on main, so a Release doesn't wait for them.
- Tools/prepush.py: every generated file rebuilt from its sources before a push; devkit/check.py checks it.
- Retire one-time and superseded scripts.

## New in 1.34.0
- A.
- Meters: bare reset and cog glyphs; tabs sized to their labels.
- Meters: the bars reach the inner dark box's right edge.
- Meters: plain bars again, tabs a little right, tools tucked in, centred title, Fight time.
- Meters: a weathered iron frame round each bar.
- Meters: tabs as drawn - rounder, a gold rim and glowing line on the chosen one, a larger title.
- Meters: tabs, reset and cog in their places; Damage shows the total alone.
- Meters: tabs in the frame's header band, rounded; the portrait follows the mode.
- UI pictures: status bars draw their fill (as long as the value, in the bar's colour).
- Meters 1.16: a normal window, readable at a glance.
- Realm patch 0032: a guest's Hero Key is made at "Play now" and shown in game; .txt key files; /key drop fixed and behind ?debug=1.
- Swing timer under the character; the chat sits higher by default.

## New in 1.33.0
- Make every player a realm host: federated architecture, toolkit, identity and realm directory.
- Hero Key v2: Ed25519 keypair authentication (ovk2), backward-compatible seed derivation from legacy ovk1 via HKDF-SHA256, public Hero IDs (ovh1), challenge-response login, and cryptographic key rotation.
- Open Vanilla Passport: signed portable character records (passport.json) with tamper-evident prestige event hash chains (level 60, first kills, titles) and GDPR Art. 20 export compliance.
- Trust tiers and import modes: Tier 0 (Official), Tier 1 (Verified), Tier 2 (Community), Tier 3 (Unverified); Legacy display, Cosmetic import, and capped Full import.
- Realm Recipe & Composer: deterministic realm.json recipes, pack conflict linter (creatures, items, DBC rows, ADT tiles) with explicit 'which wins' resolution, realm cloning, and 'Pass the torch' succession bundles.
- Host API: unified REST contract for realm control, sleep-and-wake, player moderation, GM console, and rollback previews.
- Browser Host Console (www/host.html): Simple and Advanced modes, live realm status, separate human/bot player counts, GM console, backup previews, and one-time realm wizard.
- Launcher Host un-redirection: HOST tab reinstated in main navigation with Host for Friends and Dedicated Server tabs active.
- Armory Card & oEmbed: server-rendered SVG cards with class accents and verification badges, OpenGraph unfurls, and compliant embed generator.
- Realm directory fit-and-depth ranking: sorts by trust, curator picks, 14-day new realm slots, and uptime streaks; bots counted apart from human Hero Key sessions.
- Realm Covenant & Will (docs/REALM_COVENANT.md, www/covenant.html): non-commercial pledge, bring-your-own data, 30-90 days notice, and multi-party backup escrow.
- Workshop provenance & licence allowlist: workshop.json schema and validator enforcing CC0/CC-BY/MIT and rejecting ND/Sketchfab.
- Cloud-init configs (Hetzner CX23, Oracle arm64) and Pocket Realm 4-week spike specification.
- Forge MCP expansions: added forge_host_api, forge_test_realm, and forge_drive_bot tools to Vanilla Forge.

## New in 1.32.0
- Realm patch 0031: Hero IDs, the public half of a Hero Key.
- Meters tabs in the Quests tracker's type: Friz, its gold-yellow when chosen, its parchment ink otherwise.
- Duels: on the website (DUELS_OPEN, Duels and Legend links), its patch-Z on today's Warfront one, the Duels addon in patch-Z.
- A.
- Meters: clean tab edges (pixel-drawn 3-slice tabs, crisp reset and cog frames).
- Meters: rounded Nunito text, drop shadows, cleaner tabs.
- Meters polish: no bar borders, rows touching, Arial Narrow text with a soft shadow.
- Mangos 0020 after review: groups through the world thread, unstuck only when travelling, player groups left alone.
- Meters: built from the owner's art kit (stone window, gold border and corners, kit tabs and buttons, scrollbar with arrows, rimmed fills).
- Site: Discord is for the community, not for signing in.
- GM console: Herald's last 24 hours (fights, deaths per 100 fights, close calls, fights in a group, by class, stuck hot spots with .go).
- Mangos 0020: Herald's brain.
- Meters: flat, flush rows like the reference (fill behind icon and name, outlined text, stone frame).
- Meters: matched to the reference window (bar art, row text, header, tabs, fonts).
- Realm_up: apply classicplus_herald_rotations.sql with the other Classic+ SQL.
- Herald: class rotations by level band (27 custom combat strategies, 171 lines).
- Warfront: a TESTING state in the realm list and a mode screen before you go.
- Herald: his choices in the panel, invites from friends, class rotation by level band, fight and stuck logs.
- Meters: the bronze window (header with title menu, reset, settings and close; Damage, DPS, Healing and Deaths tabs; textured class-colour bars; gold scrollbar).
- Discord Herald speaks only when commanded: no unasked #arrivals post (HERALD_ANNOUNCE=1 brings it back).
- Manual: Host on a Mac or Linux (chapter 12), built into ovhost too.
- Host a realm on macOS and Linux: host/ovhost (Docker), portable realm_up, launcher fixes.
- UI Studio: tune every window by hand (drag, size, colour, fonts, theme, tunables, art pipeline, /move import).
- Realm patch 0030: Hero Keys, and Discord sign-in ready to retire in phases.
- Herald_selfbot.sh on: no bot-AI broadcasts (loot, kills, quests, level-ups to say, yell, guild, channels) and no AI chat on the realm.
- Herald doesn't talk.
- Loot: the auto-loot recap opens beside the cursor and out of the middle of the screen, never over your character.

## New in 1.31.0
- Bug reports also open a public GitHub issue (Herald), for suggested fixes.
- Realm patch 0028 compiles: player.rs re-exports SETTLE_HARD_CAP.
- Realm patch 0029: buffs no longer turn red when a far enemy is selected.
- Loot: the auto loot recap always shows, and stays a few seconds before it fades.

## New in 1.30.9
- Community rules page (www/rules.html), linked from the site, Terms and Privacy.
- Staff wear a small blue <GM> in chat.
- Herald: the server owner and Administrators count as staff (their #world messages reached nobody).
- Work in progress.
- Realm-image: compile Rust on the runner with a kept build cache (minutes, not ~45).
- Sign-in page: Google button right under Discord (realm patch 0027).
- Console: a hidden in-game GM window (/ovgm, /gmc), game masters only.
- GM console redesign: badges, class icons, HP bars, parchment map, server sparklines, tickets.
- Mangos 0019: GM console feed, clean names, a quiet World channel.
- Realm patch 0028: no falling through the world on load.
- Mangos 0018: falling through the world puts the player back where they last stood (bind point the second time) instead of killing them.
- Herald Lite: the scenario parse test gives HL_PLAY a duration.
- Sign in with Google (realm patch 0027).
- Everything in the browser: Workshop addons in browser play (Lua-only packages, checked by SHA-256, kept in the browser), Forge Lite (items, creatures, quests and an addon as a Forge project), and the browser.html hub.
- Bot/staff_audit.py: find and close every way a non-staff member sees the staff channels.
- Herald: no unasked Discord DMs unless HERALD_DMS=1.
- Guest sign-up limits lifted: 20 per network per hour, 50 a day, no realm-wide daily cap by default.
- GM console: every player on one page (Server.bat option G).
- Fixes from the code review of 19-20 Oct.
- Restart countdown: 'a minute or two' (the world server came back in 57 s on 20 Oct).
- Portal.html matches index.html again (one blank line); the Studio test expects the realm's name, Vanilla Remastered.
- Hetzner/bug_digest.sh: a bug digest three times a day.
- Patch-Z: Social opens only when asked, /bug <text>.
- Social opens only when asked; /bug <text> sends a report straight from chat.
- Ov_gm.sh make-admin: the game account behind a Discord sign-in gets a GM level (3 admin, 2 game master, 1 moderator, 0 player), by Discord name; in the GM menu as 10.
- GM tools and a 5-minute restart countdown in chat.
- Patch-Z: the Herald addon (rest, fight orders, status) and Chat 1.16 as committed.
- Mangos 0016: Herald picks fights he can win alone.
- Herald eats on to 90% when he has food (eating is quick); sits only below 70%.
- Herald bridge: Discord -> game failures are visible (console answers checked, warning reaction, /bridge status, start-up check, a lock reaction for members without the role); herald_up.sh re-creates the HELPDESK….
- Chat 1.16: one tab strip for docked, World, Guild and whisper tabs: nothing covers another tab or the buttons, tabs narrow then fold into rows, relaid on resize; Show World/Guild tab in the chat menu.
- Herald's panel says what he is doing: fighting, resting (health or mana %), on his way back, or playing.
- Herald rests before the next pull; the Herald check becomes a scorecard.
- Herald fights it out and loots every kill (community feedback).
- Realm telemetry, and XP x1.5 from kills as well as quests.
- Herald: a leveling profile, a stuck watchdog, and the panel on screen.
- Hetzner/playerbots_db.sh: install the bot AI's database tables on the live realm.
- World server image: link aiplayerbot.conf where the bot AI reads it.
- Hetzner/herald_check.sh: smoke-test Herald on the live realm.
- Herald_selfbot.sh on: also switch the bot AI on when it was off, with no realm bots.
- Vanilla Agents browser access: the relay at agents.openvanilla.app (agents_relay_up.sh) and the pairing page at /agents/live/.
- Herald on a player's character: also switch off the bot AI's maintenance.
- Herald Autopilot takes over a player's own character from the server.
- Herald Autopilot on the live realm: drive the character with .rndbot cmd.
- Patch-Z: tonight's addon fixes for browser players (chat tab menu, expanded chat, welcome, bug box).
- Page bridge: no-op fullscreen where the browser has none (iPhone Safari).
- Manual: the changelog link points at the home page's What's next.
- Chat: expanded view of the whole history (tab bar button, chat menu, /cpchat expand): search, live new lines, clickable links, Maximize.
- Site: launch polish - one What's next section (Warfront + realm templates), Discord numbers and LIVE chip hidden until real, no made-up player counts, unused forum modals out, trailer label, engine named benilla.
- Herald: world_chat scenario and hetzner/world_chat_check.sh - checks World chat, the Discord bridge and the bug button after a realm update.
- Addons: a one-time welcome after the first login (World chat and its Discord link, the bug button and /bug, the Discord invite; /welcome shows it again; waits for the setup window), and a new-player simulator pass.
- Launch queue: on, 80 players in the world at once (PlayerLimit 100 above it), and a While you wait grid in the queue window (desktop app, Discord #world, Agents, Forge, addons).
- Realm: World chat and its Discord bridge go live (patch 0007 and classicplus_world.sql out of pending; realm_up runs the SQL).
- Addons: the bug report box takes typing (multi-line note in a scroll frame, click to focus, Enter sends), same for the player report note; Guild and World chat tabs open a menu on right-click instead of vanishing,….
- Site: the Forge section shows Forge's in-game 3D view.
- Site: the Agents section shows the inn GIF.
- Site: Vanilla Forge (coming soon) and Vanilla Agents sections on the home page and portal.
- Realm-image: install the faster workflow.
- Vanilla Agents: the inn at work as a looping GIF, the header of the Agents page and a new README section.
- Site: Get Vanilla Data replaces the client download.
- Realm-image: build only images whose inputs changed; ccache for mangosd.
- Mangos 0014: BugCommand in namespace Wnl, where Wnl.cpp declares it.
- Mobile taps: a thumb that rolls while down still taps.
- Discord_doctor: test the sign-in page at /login (/ is the play page: 401 until signed in).
- Hetzner/discord_doctor.sh: checks the Discord sign-in settings (bot token, client secret, server, role order, redirect) without printing secrets, restarts Herald, smoke-tests Sign in with Discord, lists….
- Site: Orion's 'Made by Orion' sprite moves up to the top of the footer, centred under the Support/Discord buttons; the 'Enjoying Open Vanilla?' card fades away after 8 s (not while the mouse is on it).
- Site: the last '#' Discord links go to discord.gg/r6nj5p8U4; Server download links point at the GitHub release (downloads/ only had the old OpenWoW zip).
- Docs: READMEs say Vanilla instead of World of Warcraft / WoW / 1.12.
- Open Vanilla.

## New in 1.30.8 (Vanilla Remastered pace, and Vanilla Forge)
- Vanilla Remastered levels at a friendlier pace: quest items always drop and every group member on the quest gets their own, quest XP is 1.5x, rested XP builds five times faster at inns and capitals (and slowly by any cooking fire), and each new area explored gives at least 1% of a level.
- Flights are twice as fast and you learn your faction's flight paths as you level, the Hearthstone and single-target Blessings run on 15 minutes, weapon skills train four times faster, and abandoning an item-started quest gives the item back.
- Veteran Mentor: +20% quest XP for each other level-60 character on your account, up to +60%.
- A quest board inside every dungeon entrance takes and gives that dungeon's quests, and training dummies that whisper your DPS stand by each capital's weapon master.
- The Hearthstone, Blessing and Quests addon tooltips show the realm's real timers and XP, mentor bonus included.
- Open Vanilla's name everywhere: launcher, server window, realm and website. Your install, characters and settings stay as they are.
- New on the website: Vanilla Forge, the free creator app (make maps, creatures, quests and addons, and test them on your own PC), with a guide to running your own test server, and Vanilla Agents, your AI helpers at work in a cosy inn.
- Ko-fi link on the site, in the launcher and in the manual, for anyone who wants to chip in. Nothing that affects play is ever sold.

## New in 1.30.6
- Fixes and polish.

## New in 1.30.5
- Fixes and polish.

## New in 1.30.4
- Fixes and polish.

## New in 1.30.3
- Fixes and polish.

## New in 1.30.2 (the new logo on the website)
- The website opens with the new Open Vanilla book logo, big and sharp on every screen size.
- Releases never stop for missing patch notes again: if a version has none yet, the release writes them from what changed.

## New in 1.30.1 (a new look for Open Vanilla Server)
- Open Vanilla Server has a new look: every button matches the launcher's, with clear colours (gold to start, violet to play in your browser, red to halt everything), icons, and rounded lettering.
- The HTTPS tools sit in one tidy grid, and both address boxes have their own Save button.
- The new Open Vanilla book logo everywhere, big and front and centre on the website: launcher, realm pages, favicon and Discord too.
- Open Vanilla's name is now used everywhere you read it: the launcher, Herald Autopilot, the loading-screen tips, the website, the manual and the docs. Your install, characters and settings stay exactly as they are.
- Herald Autopilot's window shows the Open Vanilla wordmark.
- Fresh screenshots on the website and the GitHub page, taken from the current launcher, server and Herald.
- Server owners can write settings as OpenVanilla.Transmog, OpenVanilla.Warfront and so on in mangosd.conf; the old names keep working.

## New in 1.30.0 (Open Vanilla, Warfront live counts)
- Open Vanilla is now Open Vanilla: the website, launcher, addons and docs use the new name. Your install, realms, characters and settings stay exactly as they are.
- The launcher is now OpenVanilla.exe, with "Open Vanilla" shortcuts in the Start menu and on the desktop. It updates itself as usual; the launcher file under its old name stays next to it for one release so older launchers can update too.
- Warfront's arena window shows who is waiting: live queue counts for each arena mode, matches being played, and players queued for battlegrounds. The website shows Warfront's live numbers too.
- When realm bots fill empty spots in a Warfront battle, you're told as you enter. Bots never count for streaks or bounties.
- Phone sign-in with Discord opens the Discord app on Android, and finishes in the browser you started in, even when Discord comes back in a different one: match the 4-digit code and you're in.
- A new animated "Signing in" screen in the browser game.
- Phone taps on the character screens land where your finger is on any phone, with a debug view (?touchdebug=1) to help find taps a browser drops.
- Assistant, Herald and Warfront are in the Workshop with the rest of the suite.
- Transmog: collect every look you bind, save outfits and switch them anywhere, with hidden slots, weapon illusions and outfits that change by situation. It works on realms that turn it on (Warfront first), at a Transmogrifier in each capital.
- The game manual is on the website: 18 chapters, from your first login to Warfront, linked from the pages that need them.

## New in 1.20.5 (Herald Autopilot, play on your phone)
- Herald Autopilot: a new program (Herald Autopilot.bat) where Herald plays for you on realms that allow it. Pick a goal (Level up, Quest, Gather, Follow me, Dungeon), press START, and watch the live log, map and bags.
- Rules are plain sentences you change with one click ("Rest when health is below 35%"), with sensible defaults for every class.
- Sim compares two sets of stats for your class and shows what each stat is worth.
- Watch Herald play your own character, any race and any class: click Herald by the minimap (or /herald) and press Let Herald play. He runs on the realm's own bot AI; you keep your camera, chat and UI, and take back control any time. Works on Open Vanilla Server and Play Solo, and on any realm whose owner turns it on.
- Herald on your own server: Open Vanilla Server has a HERALD button. Herald logs in an account you pick on your server and plays it (a fresh Human character in Northshire for now).
- Help Herald learn: if you say yes, Herald shares anonymous run numbers (never names, chat or positions) and everyone's default rules get better. Settings shows exactly what's sent.
- Play on your phone: browser play has touch controls. A stick to move, drag to look, four action keys around the Attack button, and a tray for bags, quests, chat and the menu. The Attack button shows what a tap will do with the game's own icons: a sword for an enemy, a loot bag, a quest ! or ?, an anvil at a repair vendor.
- On a phone, the character list and character creation answer taps again, so Create New Character, Enter World and Back all work.
- Touch settings: pick how the camera and buttons work (Classic, Simple or PC), auto loot, and the interface size.
- Nameplates: out of combat only your target has a plate; the rest appear when a fight starts (Plates setting "Hide idle plates").
- The website has a new realm list, a Discord community panel with live member and online counts, and a details window for each upcoming realm (Warfront, Moonguard with player housing coming, Ascension Resurrected).
- Guest play is better protected against abuse, and linking Discord to a guest signs out any old guest logins.

- Quests has a new look: the objective tracker is a parchment page in an iron frame, with gold lettering, red seals to fold each quest (a shield once it is done) and a close seal in the corner.
- A new Vanilla Remastered loading screen.
- The website's support window and Support button have new art, and Vanilla Remastered has its own details window with an Enter Realm button.
## New in 1.17.4 (Vanilla Remastered)
- The official realm is now called Vanilla Remastered on the website, in the launcher and in Herald.
- The website's realm list shows how many players are online right now (Herald counts them every minute) and the realm's live status. The filter tabs, the ping column and the "LAN server / this PC" row are gone.
- Herald's #server-status card shows players online too.

## New in 1.17.3 (faster loading, fixed windows)
- Browser play loads much faster from far away: game data, the interface and every addon are fetched in parallel before you need them, instead of one file at a time.
- Big buildings and cities (Stormwind, Darnassus, Northshire Abbey) download all their pieces at once: no more loading bar stuck near the end.
- Persona, Social, Friends, the Guild Hub and the Guilds board open again in the browser.
- The mouse keeps working after you click the menu or another window: clicking the game takes it back.
- The chat sits a little higher, clear of the action bars, and the zone name above the minimap no longer hides behind the close button.

## New in 1.17.2 (Open Vanilla Server is back)
- Running your own realm is its own download again: OpenVanilla-Server.zip, beside the launcher on every release and on openvanilla.app/host.html.
- The launcher is for playing: the HOST tab is gone. Join any realm from REALMS, or with an invite link.
- Open Vanilla Server finds your SPP Classics install by itself (or asks once), installs what it needs on first start, sets the realm address players connect to, and removes the Play Solo login before anyone can reach it.

## New in 1.17.1 (new home)
- Open Vanilla has a new home: github.com/orionopenwow/OpenVanilla and openvanilla.app. Your launcher follows by itself.
- The client button and the client list are back on HOME, and Workshop has a new CLIENTS tab for finding and adding game clients.
- HOME is cleaner: the welcome and Herald cards are gone.
- The website introduces Herald, Open Vanilla's self-learning ranger.

## New in 1.17.0 (one launcher)
- One thing to launch: OpenVanilla.exe. It starts the game for you, keeps itself up to date in the background and shows UPDATE READY when a new version is waiting.
- One PLAY button with Online, Solo and Browser.
- Play Solo: one click downloads SPP Classics, one guided setup, then PLAY. Your own offline world with playerbots.
- Host for friends is built in: host a realm from the launcher and share an invite link. The launcher explains what your friends can see before anything starts.
- Dedicated server tools are in the launcher too (HOST, Advanced), so there's no separate server download.
- Tidy folders: AddOns (Enabled and Disabled), Realms, Screenshots, Logs and Backups, each one click away in Settings.
- News, cards and links in the launcher update live from the website.
- Meet Herald, Open Vanilla's self-learning test ranger, on the website's new Herald page.
- Activate your AI (optional): a starter kit and prompts for using your own AI coding agent to make addons and run your own realm, plus an in-game Assistant window.
- Become a Node (preview, off until the network opens): help carry the network, with privacy explained up front.

## New in 1.16.1 (sign-in)
- A new sign-in page in Open Vanilla's look, on phones and computers: the Open Vanilla logo and art, one big Sign in with Discord button, and the password form tucked away.
- Signed in once, signed in for good: no more Discord login screen on your phone when the realm already knows you. Your sign-in lasts 60 days from your last visit.
- On a phone, the Discord button can open the Discord app to approve, and a returning player gets "Continue as <name>".
- After signing in you land back on the page you were going to, and a sign-in that timed out quietly tries again once.
- Add Open Vanilla to your home screen: it has an icon and opens full screen. Browsers that can't run the game say what to use instead.
- Play free as a guest: no sign-up, no Discord needed. Your heroes stay on that device, and "Continue as guest" brings you back to them.
- Link Discord any time (the gold link at the top of the game) and your guest heroes become a full account you can use anywhere.
- For creators: the Model Porter (Model_Porter.bat). Drop a rigged, animated .glb and it becomes a 1.12 creature or a rideable mount, with its bones, animations and textures, a live preview, and a one-click "Add to Open Vanilla".

## New in 1.16.0 (community)
- Report players from any right-click menu, chat name, Social, Persona, Dungeons or Guilds. Reports carry the chat around them and go to a moderation desk; people decide every kick and ban.
- Guild Hub (/gh): roster with ranks and notes, recruitment, an events calendar with sign-ups and reminders, a bank log, DKP and loot council, and an MOTD composer.
- World chat: a new World channel bridged to the Open Vanilla Discord, with its own chat tab.
- A ● LIVE mark next to players who are streaming, and "now playing" on Persona (off unless you turn it on).
- Website: the Armory (every character and guild, public unless you choose friends-only or hidden), Streamers and Creators pages with a monthly leaderboard, and the Workshop for finding, rating and installing addons.

## New in 1.15 (addons and site: live with this update)
- Plain addon names everywhere: Meters, Quests, Bags, Prices, Vendor, Plates, Casting, Threat, Raid, Guilds, Persona.
- The Addons window has real on/off switches, room for every addon, and settings that scroll.
- Meters tracks what Details! does: damage, healing, overhealing, damage taken, deaths with a recap, interrupts, dispels, crowd control, uptime and more, with 25 past fights, boss fights kept, tabs, extra windows, a breakdown window, reports and a settings sheet behind the gear.
- Quests: the Wildwood ring is back as the minimap frame. Repair and vendor icons on the minimap, a tracking menu on the compass rose, a corpse arrow, a quest tracker, quest pins on the world map and a new quest log on L with search, filters, sorting, abandon-with-undo and history.
- Social (O): friends, guild, group, who, ignore and recent players in one window, with online and level-up toasts.
- Dungeons: a group finder board. List yourself, browse, ask to join. Nobody is teleported or pulled into a group.
- Chat: five themes (Slate by default), opaque and raised, with timestamps, short channel names, copy chat, history, mentions and spam control.
- Achievements: 388 real vanilla achievements on Y. They start counting once the realm update lands.
- Mail (Open All, Return All), a new loot window, gear sets in Bags, and Talents with a planner.
- Essentials: cooldown numbers, out-of-range colours, reagent counts, auto dismount, smarter /cast, keybind mode, aura timers and accessibility options.
- Defaults that stick: auto loot, instant quest text, auto-accept, names over heads, nameplates off (V turns them on). Nameplates end in a grey level cap and can be clicked.
- Right-click menus work again on the player, target and party frames, names and nameplates.
- Vendor sell prices on every item tooltip.
- Play Solo: a new page on the site.
- Persona, redesigned: the Character-frame look with your picture in the portrait, four guided steps (Basics, Picture, Story, Extras) with Back and Next, and a profile picture: your character, any race and sex, or a hero or creature face.
- Dungeons, Essentials, the Quest Log, Raid, the Meters breakdown and the chat copy windows now use the classic WoW dialog look (switch with /skin).
- The loading box has the Open Vanilla frame, dragon endcaps and an arcane bar.
- A tip jar on the site and in the launcher (Support the realm). Tips never buy power, items or game time.

## Waiting for the realm restart
- Skills learned as you level (no trainer), free respec, dual spec, a starter pet for hunters, AoE looting, fixed level-up silver, a gentler level curve and achievements tracking (realm/mangos/pending, realm/classicplus/pending).
- A WoW-style loading screen, sound that waits until you move, the hero logo on the login screens and a class grid that only offers allowed pairs (realm/patches/pending).

## New in 1.14.2
- Persona: roleplay profiles for every player. Name, title, appearance, bio, shares and an IC / OOC / looking-for-RP status on tooltips, your target's portrait and a player directory. Type /rp.
- Better defaults on first login: instant quest text, auto-accept quests (hold Shift to read), full camera distance and auto loot. /cpdefaults to change them.
- Weapon skills fixed for the new race and class pairs (Human, Undead and Gnome Hunters; Troll Druids).
- Character creation: the class row is 5 across with room for every class.
- The account menu folds into a small tab at the top, and the loading and login screens have new art.

## Under the hood
- Page and addon updates go live about a minute after a push, with no rebuild or restart.
- Herald, the test bot, signs in every night as a Human Hunter and reports what works.
