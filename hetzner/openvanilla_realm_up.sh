#!/usr/bin/env bash
# Open Vanilla on the realm server, in one command (safe to re-run):
#   · Discord sign-in (players click "Sign in with Discord": account made, joined to the server,
#     Player role, straight into the game) — via the Open Vanilla realm image
#   · Classic+ addon suite in the browser client (patch-Z.MPQ + the addon loader)
#   · modern WoW's race/class combos, 58 of 72 (server data + starting gear on client and server)
#   · the world server's WNL hook for the addon suite (via the Open Vanilla mangos image)
#   · every class's weapon skills from level 1, no intro cinematics, a Star Pouch every level
#   · the Herald's public sign-up feed at https://<realm>/community/feed.json (for the website)
#
# Who may create an account (SIGNUP_MODE in .env, default open; the Herald must use the same value):
#   open    anyone who passed the Discord gate (Recruit) signs in and gets an account straight away
#   waves   only players a staff /wave invited (Alpha Tester), plus existing Adventurers and staff
#
#   curl -fsSL https://raw.githubusercontent.com/orionopenwow/OpenVanilla/stable/hetzner/openvanilla_realm_up.sh -o openvanilla_realm_up.sh
#   bash openvanilla_realm_up.sh
#
# The staging realm (devkit/staging/staging_up.sh) runs this same script with
# OW_REALM_DIR=/opt/wenilla-staging OW_CP=/opt/openvanilla-staging OW_STAGING=1: no Discord, no Caddy.
# A community realm (host/ovhost on macOS or Linux) runs it with OW_COMMUNITY=1: no root needed, any
# folder, Discord sign-in only if its keys are already in .env, no login queue unless .env turns it on.
set -euo pipefail
REALM_DIR=${OW_REALM_DIR:-/opt/wenilla-realm}
CP=${OW_CP:-/opt/openvanilla-classicplus}
STAGING=${OW_STAGING:-0}
COMMUNITY=${OW_COMMUNITY:-0}
RAW=https://raw.githubusercontent.com/orionopenwow/OpenVanilla/stable
IMAGE=ghcr.io/orionopenwow/openvanilla-realm:latest
DEFAULT_GUILD=1559122162898567200
HERALD_PUBLIC=/opt/openvanilla-herald/public   # herald.py writes feed.json here; Caddy serves it
[ "$COMMUNITY" = 1 ] && HERALD_PUBLIC="$CP/community-public"
say() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }   # macOS has shasum
# root on the realm server; a community realm in the user's own folder doesn't need it
[ "$(id -u)" -eq 0 ] || [ -w "$REALM_DIR" ] || { echo "Run as root (or as the owner of $REALM_DIR)"; exit 1; }
cd "$REALM_DIR"
set -a; . ./.env; set +a
# This stack's own volumes (a staging stack on the same machine has its own; never mix them up).
PROJECT=${COMPOSE_PROJECT_NAME:-$(basename "$REALM_DIR")}
vol() { docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.volume=$1" | head -1; }
setenv() {  # setenv KEY VALUE  -> .env (replace or append), never echoed
  local k=$1 v=$2
  if grep -q "^$k=" .env; then python3 - "$k" "$v" <<'PY'
import sys
k, v = sys.argv[1], sys.argv[2]
lines = open(".env").read().splitlines()
open(".env", "w").write("\n".join(f"{k}={v}" if l.startswith(k + "=") else l for l in lines) + "\n")
PY
  else printf '%s=%s\n' "$k" "$v" >> .env; fi
  export "$k=$v"
}

say "1/6 Downloading the Open Vanilla files"
mkdir -p "$CP"
for f in patch-Z.MPQ bridge.js bridge.js.br bridge.js.gz addons-loader.js classicplus_races.sql classicplus_weapons.sql classicplus_starpouch.sql classicplus_retired_vendor_cleanup.sql classicplus_combo_census.sql classicplus_characters.sql classicplus_classquests.sql classicplus_starpouch_money.sql classicplus_xp_rollback.sql classicplus_trainers.sql classicplus_achievements.sql classicplus_pace.sql classicplus_bugs.sql classicplus_herald_ai.sql classicplus_herald_rotations.sql classicplus_world.sql classicplus_world_models.sql classicplus_world_models.json apply_models_dbc.py openvanilla_gameplay_conf.sh gen_outfits.py fix_skillraceclassinfo.py; do
  curl -fsSL "$RAW/realm/classicplus/$f" -o "$CP/$f.new" && mv "$CP/$f.new" "$CP/$f"
done
# page layer (account dock, login backdrop, owdiag), bind-mounted into the realm at /app/www/ow
mkdir -p "$CP/www"
for f in openvanilla.js workshop.js touch.js owdiag.js owdiag-checks.js owdiag-capture.js owdiag-load.js sw.js sw-register.js prefetch.js stages.js syncread.js ahead.js wmo.js input.js warmup.js combos.json ow-corner-logo.webp ow-corner-logo@2x.webp login-backdrop.js login-backdrop.webp login-backdrop.webm login-backdrop.mp4 ow-signin.webp ow-signin.mp4 ow-signin.webm Cinzel-SemiBold.woff2 Cinzel-SemiBold.ttf Cinzel-OFL.txt ow-corner-tl.png ow-corner-tr.png ow-corner-bl.png ow-corner-br.png ow-divider.png ow-dragon-l.webp ow-dragon-r.webp nowplaying.js nowplaying.json nowplaying-callback.html creator-link.html; do
  curl -fsSL "$RAW/realm/www/$f" -o "$CP/www/$f.new" && mv "$CP/www/$f.new" "$CP/www/$f"
done
mkdir -p "$CP/www/manifests"
curl -fsSL "$RAW/realm/www/manifests/_ui.json" -o "$CP/www/manifests/_ui.json" || true   # warmup.js
if curl -fsSL "$RAW/realm/www/manifests/index.json" -o "$CP/www/manifests/index.json"; then
  for z in $(python3 -c "import json;print(' '.join(json.load(open('$CP/www/manifests/index.json'))))"); do
    curl -fsSL "$RAW/realm/www/manifests/$z.json" -o "$CP/www/manifests/$z.json" || true
  done
fi
find "$CP/www" -type f -exec chmod 644 {} +; find "$CP/www" -type d -exec chmod 755 {} +
# helper scripts: server weapon-skill DBC fix and push-to-deploy hot updates
for f in openvanilla_server_dbc.sh openvanilla_server_models.sh openvanilla_hotpatch.sh openvanilla_rename_tables.sh ov_gm.sh; do
  curl -fsSL "$RAW/hetzner/$f" -o "$CP/$f.new" && mv "$CP/$f.new" "$CP/$f"
done
find "$CP" -maxdepth 1 -type f -exec chmod 644 {} +; chmod 755 "$CP"/*.sh; ls -la "$CP"

say "2/6 Classic+ client files (addons, art, modern race/class combos)"
# copy then rename: a staging stack hard-links the live client data, so never write into the old file
cp "$CP/patch-Z.MPQ" "$CLIENT_DATA/patch-Z.MPQ.new" && mv -f "$CLIENT_DATA/patch-Z.MPQ.new" "$CLIENT_DATA/patch-Z.MPQ"
ls -la "$CLIENT_DATA" | grep -i patch

say "3/6 Server: starting gear, race/class data and every class's weapon skills"
VOL=$(vol gamedata)
[ -n "$VOL" ] || { echo "No gamedata volume found (was 'realmctl extract' run?)"; exit 1; }
# starting gear for the new combos, generated from this server's own CharStartOutfit.dbc
mkdir -p "$CP/dbc"
docker run --rm -v "$VOL":/data -v "$CP/dbc":/out debian:bookworm-slim sh -c '
  f=$(ls /data/dbc | grep -i "^charstartoutfit.dbc$" | head -1); f=${f:-CharStartOutfit.dbc}
  [ -f "/data/dbc/$f.orig" ] || cp "/data/dbc/$f" "/data/dbc/$f.orig"
  cp "/data/dbc/$f.orig" /out/stock.dbc && echo "$f" > /out/name'
python3 "$CP/gen_outfits.py" "$CP/dbc/stock.dbc" "$CP/dbc/CharStartOutfit.dbc"
docker run --rm -v "$VOL":/data -v "$CP/dbc":/in:ro debian:bookworm-slim sh -c '
  cp /in/CharStartOutfit.dbc "/data/dbc/$(cat /in/name)" && echo "server dbc/$(cat /in/name) updated (original kept as .orig)"'
# tables made under the project's old name move to the Open Vanilla names first (once); the world
# server and the realm service stay stopped until steps 5 and 6 start them on the new images
KEEP_STOPPED=1 bash "$CP/openvanilla_rename_tables.sh" "$REALM_DIR"
# if anything below stops this update early, start them again so the site and the world don't stay
# down (a 502 on the play page) until the next run
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo "!! The update stopped early (exit $rc): starting the realm and the world server again on their current images."; (cd "$REALM_DIR" && docker compose up -d realm mangosd) || true; fi' EXIT
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_races.sql"
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_weapons.sql"
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_starpouch.sql"
# the retired vendor NPC 990001 leaves the world (safe to run again; item 990101 stays for its owners)
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_retired_vendor_cleanup.sql"
# ported models: their creatures, mount spells and reins
[ ! -s "$CP/classicplus_world_models.sql" ] || MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_world_models.sql"
# 1.15 gameplay (the world server image built with realm/mangos/0002-0004 reads all of this at
# start-up): who still plays a retired race/class pair, then the new tables and data. Every file is
# safe to run twice; each has an undo file next to it (realm/classicplus/*_rollback.sql).
echo "Retired race/class pairs still in use (kept, never deleted):"
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/classicplus_combo_census.sql" || true
# The XP curve stays stock (classicplus_xp_rollback.sql undoes the gentler curve this once ran):
# the pace comes from XP x1.5 (kills and quests), rested and classicplus_pace.sql (realm/mangos/0013).
for f in classicplus_characters.sql classicplus_classquests.sql classicplus_starpouch_money.sql \
         classicplus_xp_rollback.sql classicplus_trainers.sql classicplus_achievements.sql classicplus_pace.sql \
         classicplus_bugs.sql classicplus_herald_ai.sql classicplus_herald_rotations.sql classicplus_world.sql; do
  echo "applying $f"
  MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos < "$CP/$f"
done
# the pace (XP x1.5 from kills and quests, rested x5 at inns and capitals, weapon skill x4, OpenVanilla.Pace.*) and
# the OpenVanilla.* switches in mangosd.conf (rollback: bash ... rollback)
OW_REALM_DIR="$REALM_DIR" bash "$CP/openvanilla_gameplay_conf.sh"
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicmangos \
  -e "SELECT COUNT(*) AS race_class_combos FROM playercreateinfo"

# Cinematics off: no intro movie at a new character's first login (SkipCinematics = 2).
CFGVOL=$(vol config)
[ -n "$CFGVOL" ] && docker run --rm -v "$CFGVOL":/config debian:bookworm-slim sh -c '
  sed -i "s/^SkipCinematics *=.*/SkipCinematics = 2/" /config/mangosd.conf && grep "^SkipCinematics" /config/mangosd.conf'

# Realm type Normal (PvE rules; "PvE" in the realm list). mangosd writes realmlist.icon from GameType at
# every start (World.cpp), so the config is the source; the UPDATE shows it before the restart.
[ -n "$CFGVOL" ] && docker run --rm -v "$CFGVOL":/config debian:bookworm-slim sh -c '
  sed -i "s/^GameType *=.*/GameType = 0/" /config/mangosd.conf && grep "^GameType" /config/mangosd.conf'
MYSQL_PWD="$DB_ROOT_PASSWORD" docker compose exec -T -e MYSQL_PWD mariadb mariadb -uroot classicrealmd \
  -e "UPDATE realmlist SET icon = 0 WHERE id = 1"

say "4/6 Discord sign-in settings"
# The Discord invite everywhere the realm shows one (the sign-in page's Join our Discord, the footer).
# An old or missing one becomes the current invite; set OV_DISCORD_INVITE to use another.
case "${DISCORD_INVITE_URL:-}" in ""|*9KGdUDGnv9*|*r6nj5p8U4*|*discord.gg/openvanilla*)
  setenv DISCORD_INVITE_URL "${OV_DISCORD_INVITE:-https://discord.gg/hVeUxYwbkr}" ;; esac
if [ "${DISCORD_SIGNIN:-on}" = off ]; then
  # hetzner/discord_off.sh: no Discord sign-in (guest, Google and password stay); the settings stay in .env
  echo "Discord sign-in is OFF (DISCORD_SIGNIN=off; bash discord_off.sh on turns it back on)"
  grep -q '^SIGNUP_MODE=' .env || setenv SIGNUP_MODE open
  grep -q '^QUEUE_ENABLED=' .env || setenv QUEUE_ENABLED 1
  grep -q '^QUEUE_WORLD=' .env || setenv QUEUE_WORLD 80
  grep -q '^MANGOSD_MEM=' .env || setenv MANGOSD_MEM 3200m
elif [ "$COMMUNITY" = 1 ] && [ -z "${DISCORD_CLIENT_SECRET:-}" ]; then
  echo "community realm: sign in with a password or play as a guest (Discord sign-in: put its keys in .env and re-run)"
  grep -q '^QUEUE_ENABLED=' .env || setenv QUEUE_ENABLED 0
  grep -q '^SIGNUP_MODE=' .env || setenv SIGNUP_MODE open
elif [ "$STAGING" = 1 ]; then echo "staging: no Discord sign-in (log in with a password)"; else
if [ -z "${DISCORD_CLIENT_SECRET:-}" ] || [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
  echo "From discord.com/developers/applications -> Open Vanilla Herald (the same app as the bot):"
  read -rsp "  Bot token (Bot -> Reset Token; hidden): " BOT; echo
  read -rsp "  Client secret (OAuth2 -> Reset Secret; hidden): " SECRET; echo
  read -rp  "  Discord server ID [$DEFAULT_GUILD]: " GUILD; GUILD=${GUILD:-$DEFAULT_GUILD}
  read -rp  "  Permanent invite link (https://discord.gg/...): " INVITE
  APPID=$(python3 -c "import base64,sys;s=sys.argv[1].split('.')[0];print(base64.b64decode(s+'='*(-len(s)%4)).decode())" "$BOT")
  setenv DISCORD_BOT_TOKEN "$BOT"; setenv DISCORD_CLIENT_SECRET "$SECRET"
  setenv DISCORD_CLIENT_ID "$APPID"; setenv DISCORD_GUILD_ID "$GUILD"; setenv DISCORD_INVITE_URL "$INVITE"
fi
# A refused token must not stop the update: keep the Discord settings already in .env and go on.
if ! ROLES=$(curl -fsS -H "Authorization: Bot $DISCORD_BOT_TOKEN" "https://discord.com/api/v10/guilds/$DISCORD_GUILD_ID/roles"); then
  echo "!! Discord refused the bot token or server ID: keeping the current Discord settings."
  echo "   Fix DISCORD_BOT_TOKEN in $REALM_DIR/.env (and /etc/openvanilla-herald.env), then re-run this script."
  ROLES='[]'
fi
setenv SIGNUP_MODE "${SIGNUP_MODE:-open}"
# The login queue (realm patch 0022), on for launch: at most QUEUE_WORLD players in the world (80); everyone
# else waits in line on the play page, which shows what to do meanwhile (realm/www/openvanilla.js queueExtras).
# A value already in .env wins; QUEUE_ENABLED=0 there turns the line off. mangosd's PlayerLimit stays above it.
grep -q '^QUEUE_ENABLED=' .env || setenv QUEUE_ENABLED 1
grep -q '^QUEUE_WORLD=' .env || setenv QUEUE_WORLD 80
# World server memory (Oct 22 fix): the upstream default (2500m) left mangosd at 97% of its limit with nobody
# online on the 8 GB host. 3200m gives headroom; a value already in .env wins (Duels/Warfront set their own).
grep -q '^MANGOSD_MEM=' .env || setenv MANGOSD_MEM 3200m
echo "Login queue: QUEUE_ENABLED=$(sed -n 's/^QUEUE_ENABLED=//p' .env), QUEUE_WORLD=$(sed -n 's/^QUEUE_WORLD=//p' .env) in the world at once"
# open sign-up: a new player signs in on the website and plays at once (patch 0021); waves keep the role gate
if [ "$SIGNUP_MODE" = open ]; then setenv DISCORD_OPEN_SIGNUP 1; else setenv DISCORD_OPEN_SIGNUP 0; fi
read -r REQ GRANT <<<"$(python3 - "$ROLES" "$SIGNUP_MODE" <<'PY'
import json, sys
roles = {r["name"]: r["id"] for r in json.loads(sys.argv[1])}
# Adventurer was called Player before the gate; the role id is the same either way.
allowed = ["Adventurer", "Player", "Alpha Tester", "Beta Tester", "Founder", "Admin", "Developer", "Game Master",
           "Moderator"] + (["Recruit"] if sys.argv[2] == "open" else [])
print(",".join(roles[n] for n in allowed if n in roles) or "-", roles.get("Adventurer", roles.get("Player", "-")))
PY
)"
[ "$REQ" != "-" ] && setenv DISCORD_REQUIRE_ROLE_IDS "$REQ"
[ "$GRANT" != "-" ] && setenv DISCORD_GRANT_ROLE_ID "$GRANT"
chmod 600 .env
echo "Discord app $DISCORD_CLIENT_ID · server $DISCORD_GUILD_ID · sign-ups: $SIGNUP_MODE · role gate: $([ "$REQ" != "-" ] && echo on || echo 'off (anyone in the server can sign in)')"
fi

# The first step that disconnects anyone is next (the realm service carries browser players, then
# the world server restarts): warn the players in chat and on screen first, 5 minutes by default
# (OW_WARN_MIN=10 for ten, 0 for none; skipped when nobody is online). "bash ov_gm.sh cancel" in
# another window calls it off, and the update stops here with nobody disconnected.
if [ "$STAGING" != 1 ] && [ "${OW_WARN_MIN:-5}" != 0 ] && { [ "$COMMUNITY" != 1 ] || [ -r /etc/openvanilla-herald.env ]; }; then
  say "Warning the players: restart in ${OW_WARN_MIN:-5} minute(s)"
  if ! OW_REALM_DIR="$REALM_DIR" bash "$CP/ov_gm.sh" warn "${OW_WARN_MIN:-5}" "an update"; then
    echo "The countdown was called off (or the GM tool failed): the update stops here and nobody was disconnected. Run it again when ready."
    # the realm and the world server are still running: leave them be (the EXIT trap would recreate
    # the realm service on this run's .env and drop every browser player)
    trap - EXIT
    exit 1
  fi
fi
say "5/6 Realm service: Open Vanilla image + addon loader"
[ -f compose.override.yaml ] && cp compose.override.yaml "compose.override.yaml.bak.$(date +%s)"
if docker pull -q "$IMAGE" >/dev/null 2>&1; then REALM_IMAGE="$IMAGE"; else
  echo "!! $IMAGE isn't published yet (GitHub Actions: realm-image). Using the stock image: no Discord button until it is."
  REALM_IMAGE="ghcr.io/arnesen/wenilla-realm:\${REALM_TAG:-latest}"
fi
MANGOS_IMAGE=ghcr.io/orionopenwow/openvanilla-mangos:latest
if PULL_ERR=$(docker pull -q "$MANGOS_IMAGE" 2>&1); then
  MANGOS_BLOCK="  mangosd:
    image: $MANGOS_IMAGE"
else
  echo "!! $MANGOS_IMAGE can't be pulled, so the world server stays stock (no Compass pins, Vanguard threat, Ledger prices or Visage timers)."
  case "$PULL_ERR" in
    *denied*|*unauthorized*)
      echo "   The image exists but is private. Make it public: github.com/orionopenwow?tab=packages -> Change visibility -> Public, then re-run this script." ;;
    *)
      echo "   It hasn't been built. Check github.com/orionopenwow/OpenVanilla/actions (workflow realm-image, job mangos): re-run it if it failed, then re-run this script." ;;
  esac
  MANGOS_BLOCK=""
fi
# The realm's web name. A server set up as play.openwow.app moves to play.openvanilla.app once that
# name points here, and keeps answering on the old one (REALM_ALIASES), so old links and bookmarks work.
if [ "$STAGING" != 1 ] && [ "${REALM_DOMAIN:-}" = "play.openwow.app" ]; then
  HERE_IP="$(curl -fsS https://api.ipify.org 2>/dev/null || true)"
  NEW_IP="$(getent ahostsv4 play.openvanilla.app | awk 'NR==1{print $1}')"
  if [ -n "$HERE_IP" ] && [ "$HERE_IP" = "$NEW_IP" ]; then
    setenv REALM_DOMAIN play.openvanilla.app; REALM_DOMAIN=play.openvanilla.app
    case " ${REALM_ALIASES:-} " in *" play.openwow.app "*) ;; *) REALM_ALIASES="${REALM_ALIASES:+$REALM_ALIASES }play.openwow.app"; setenv REALM_ALIASES "$REALM_ALIASES";; esac
    say "Web name: play.openvanilla.app (play.openwow.app still answers)"
    echo "   Discord: add https://play.openvanilla.app/auth/discord/callback to the app's OAuth2 redirects."
  else
    echo "   play.openvanilla.app doesn't point at this server yet ($NEW_IP vs $HERE_IP): staying on play.openwow.app."
  fi
fi

# Caddy: upstream's site (caddy/Caddyfile) plus the Herald's public feed under /community/.
mkdir -p "$HERALD_PUBLIC"
cat > "$CP/Caddyfile" <<'CADDY'
# Written by openvanilla_realm_up.sh: upstream wenilla-realm's Caddyfile + Open Vanilla's /community/ feed.
{
	# RSA certificates: Let's Encrypt chains them to ISRG Root X1, which every trust store has. Its
	# default ECDSA chain runs through ISRG Root X2's cross-sign by X1, and the launcher (Python, the
	# roots Windows has installed) read that as "certificate has expired" (2026-10-24).
	# hetzner/openvanilla_tls_rsa.sh moves a running realm over.
	key_type rsa2048
}
{$REALM_DOMAIN:localhost} {
	encode zstd gzip
	# Open Vanilla service worker: allowed to control the whole site, not just /ow/.
	@owsw path /ow/sw.js
	header @owsw Service-Worker-Allowed "/"

	# Faster loads. The client and the game data are the same bytes for every player, but upstream
	# marks them "Vary: Cookie", so a browser throws its whole saved copy (15 MB client, 100+ MB
	# data) away whenever the login cookie changes. They still need a sign-in to fetch.
	@shared path /data/* /wenilla_bg.wasm
	header @shared >Vary "Accept-Encoding"
	# Start the 15 MB client download with the play page's first bytes, not four scripts later.
	@playpage path / /play /play/
	header @playpage >Link "</wenilla_bg.wasm>; rel=preload; as=fetch; crossorigin"

	# The Herald's sign-up feed and census (herald.py writes them), read by the website on any domain.
	handle_path /community/* {
		root * /srv/community
		header Access-Control-Allow-Origin *
		header Cache-Control "public, max-age=30"
		# data only: never runs as the realm's page, whatever lands in the folder
		header Content-Security-Policy "default-src 'none'; sandbox"
		file_server
	}

	handle {
		reverse_proxy ovlive-realm:8090 {
			# the client's real address, never one it sent (rate limits key on these)
			header_up X-Real-IP {remote_host}
			header_up X-Forwarded-For {remote_host}
		}
	}

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options nosniff
		Referrer-Policy no-referrer
		# no framing by other sites (clickjacking the dashboard, the play page)
		X-Frame-Options SAMEORIGIN
		Content-Security-Policy "frame-ancestors 'self'"
		-Server
	}
}
CADDY
# The site names: the realm's name plus any old ones it still answers on (REALM_ALIASES, spaces).
if [ -n "${REALM_ALIASES:-}" ]; then
  SITES="${REALM_DOMAIN:-localhost}"
  for a in $REALM_ALIASES; do SITES="$SITES, $a"; done
  SITES="$SITES" python3 - "$CP/Caddyfile" <<'PY'
import os, sys
p = sys.argv[1]
s = open(p).read()
s = s.replace("{$REALM_DOMAIN:localhost} {", os.environ["SITES"] + " {", 1)
open(p, "w").write(s)
PY
fi
# Herald Autopilot + learning (bot/herald_autopilot_api.py, installed by herald_up.sh) runs on this host.
if [ "$STAGING" != 1 ] && [ -e /etc/systemd/system/openvanilla-herald-autopilot.service ]; then
  APPORT=$(sed -n 's/^AUTOPILOT_PORT=//p' /etc/openvanilla-herald.env 2>/dev/null | tail -1)
  python3 - "$CP/Caddyfile" "${APPORT:-17890}" <<'PY'
import sys
path, port = sys.argv[1], sys.argv[2]
s = open(path).read()
block = ("\t# Herald Autopilot + learning (bot/herald_autopilot_api.py) on this host.\n"
         "\t@herald_ap path /api/autopilot/* /api/herald/*\n"
         "\thandle @herald_ap {\n\t\treverse_proxy host.docker.internal:" + port + " {\n\t\t\theader_up X-Real-IP {remote_host}\n\t\t}\n\t}\n\n")
s = s.replace("\thandle {\n\t\treverse_proxy ovlive-realm:8090", block + "\thandle {\n\t\treverse_proxy ovlive-realm:8090", 1)
open(path, "w").write(s)
PY
  HERALD_AP=1
fi
# The staging realm, when installed, is reached through this Caddy at its own name.
if [ "$STAGING" != 1 ] && [ -e /opt/wenilla-staging/.env ]; then
  SDOMAIN=$(grep '^REALM_DOMAIN=' /opt/wenilla-staging/.env | cut -d= -f2)
  cat >> "$CP/Caddyfile" <<CADDY

# The staging realm (devkit/staging): same site layout, its own realm service.
$SDOMAIN {
	encode zstd gzip
	@owsw path /ow/sw.js
	header @owsw Service-Worker-Allowed "/"
	reverse_proxy owstaging-realm:8090
	header -Server
}
CADDY
fi
# The node network's relay (hetzner/relay_up.sh), when installed, is reached through this Caddy too.
if [ "$STAGING" != 1 ] && [ -e /opt/openvanilla-relay/relay.env ] && [ -e /opt/openvanilla-relay/Caddyfile.relay ]; then
  cat /opt/openvanilla-relay/Caddyfile.relay >> "$CP/Caddyfile"
fi
# Vanilla Agents browser access (hetzner/agents_relay_up.sh), when installed, is reached through this Caddy too.
# Realms of their own on this host (hetzner/duels_up.sh, ...) leave their site block in Caddyfile.site.
if [ "$STAGING" != 1 ]; then
  for f in /opt/openvanilla-*/Caddyfile.site; do [ -e "$f" ] && cat "$f" >> "$CP/Caddyfile"; done
fi
if [ "$STAGING" != 1 ] && [ -e /opt/vanilla-agents-relay/Caddyfile.agents ]; then
  cat /opt/vanilla-agents-relay/Caddyfile.agents >> "$CP/Caddyfile"
fi
if [ "$STAGING" = 1 ]; then
  CADDY_BLOCK=""
  LIVEVOL=$(docker volume ls -q --filter "label=com.docker.compose.project=wenilla-realm" --filter "label=com.docker.compose.volume=gamedata" | head -1)
  MANGOS_BLOCK="  mangosd:
    image: $MANGOS_IMAGE
    volumes:
      - $LIVEVOL:/live:ro      # the live realm's maps, shared read-only (see devkit/staging)
networks:
  live:
    external: true
    name: wenilla-realm_default"
  LIVE_NET="    networks:
      default: {}
      live:
        aliases: [owstaging-realm]"
else
  CADDY_BLOCK="  caddy:
    volumes:
      - $CP/Caddyfile:/etc/caddy/Caddyfile:ro
      - $HERALD_PUBLIC:/srv/community:ro"
  [ "${HERALD_AP:-0}" = 1 ] && CADDY_BLOCK="$CADDY_BLOCK
    extra_hosts:
      - host.docker.internal:host-gateway"
  # Caddy reaches the live website by a name only it has (Oct 22 login fix): Duels, Warfront and staging join
  # this network with their own service also called "realm", and Docker then answers "realm" with both, so
  # players landed on the Duels website and its accounts.
  LIVE_NET="    networks:
      default:
        aliases: [ovlive-realm]"
fi
# Discord sign-in off (discord_off.sh): the realm service gets no Discord app id or secret.
if [ "${DISCORD_SIGNIN:-on}" = off ]; then DC_ID='""   # Discord sign-in off (discord_off.sh)'; DC_SECRET='""'
else DC_ID='${DISCORD_CLIENT_ID:-}'; DC_SECRET='${DISCORD_CLIENT_SECRET:-}'; fi
cat > compose.override.yaml <<YAML
# Written by openvanilla_realm_up.sh — re-run it instead of editing by hand.
services:
  realm:
    image: $REALM_IMAGE
    environment:
      DISCORD_CLIENT_ID: $DC_ID
      DISCORD_CLIENT_SECRET: $DC_SECRET
      DISCORD_GUILD_ID: \${DISCORD_GUILD_ID:-}
      DISCORD_BOT_TOKEN: \${DISCORD_BOT_TOKEN:-}
      DISCORD_REQUIRE_ROLE_IDS: \${DISCORD_REQUIRE_ROLE_IDS:-}
      DISCORD_GRANT_ROLE_ID: \${DISCORD_GRANT_ROLE_ID:-}
      DISCORD_INVITE_URL: \${DISCORD_INVITE_URL:-}
      DISCORD_OPEN_SIGNUP: \${DISCORD_OPEN_SIGNUP:-0}
      # Google sign-in (patch 0027): on when both are in .env (hetzner/google_signin.sh)
      GOOGLE_CLIENT_ID: \${GOOGLE_CLIENT_ID:-}
      GOOGLE_CLIENT_SECRET: \${GOOGLE_CLIENT_SECRET:-}
      # login queue (patch 0022): on for launch, 80 in the world at once (set above; .env wins)
      QUEUE_ENABLED: \${QUEUE_ENABLED:-1}
      QUEUE_DOWNLOADS: \${QUEUE_DOWNLOADS:-25}
      QUEUE_WORLD: \${QUEUE_WORLD:-80}
      # guest play (patch 0017): 1 = on even with the Discord role gate (this realm wants guests), 0 = off
      OPENVANILLA_GUESTS: \${OPENVANILLA_GUESTS:-1}
      OPENVANILLA_GUEST_DAILY_MAX: \${OPENVANILLA_GUEST_DAILY_MAX:-}
      OPENVANILLA_GUEST_IDLE_DAYS: \${OPENVANILLA_GUEST_IDLE_DAYS:-}
    volumes:
      - $CP/bridge.js:/app/www/bridge.js:ro
      - $CP/bridge.js.br:/app/www/bridge.js.br:ro
      - $CP/bridge.js.gz:/app/www/bridge.js.gz:ro
      - $CP/addons-loader.js:/app/www/addons-loader.js:ro
      - $CP/www:/app/www/ow:ro
$LIVE_NET
$CADDY_BLOCK
$MANGOS_BLOCK
YAML
# --force-recreate: the web service reads patch-Z's file table once, at start. Step 2 swapped in a
# new patch-Z, so a service left running would read the new file through the old table (every
# addon file after the first changed one fails with a 500).
if [ "$STAGING" = 1 ]; then docker compose up -d --force-recreate realm; else docker compose up -d --force-recreate realm && docker compose up -d caddy; fi
# "up -d" leaves a running Caddy on its old config: load the Caddyfile written above (headers, routes)
# in place, without dropping connections; a restart if the reload is refused.
if [ "$STAGING" != 1 ]; then
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile 2>/dev/null \
    || docker compose restart caddy
fi
# Published after the restart: browsers key their saved patch-Z files on this version, so it must
# not name the new patch-Z while the old one is still being served.
# the data version tells service workers when patch-Z's files changed; "sw" = opt-in | on | off
printf '{"patchZ":"%s","sw":"%s"}\n' "$(sha256 "$CP/patch-Z.MPQ" | cut -c1-16)" "${OW_SW:-on}" > "$CP/www/data-version.json"
chmod 644 "$CP/www/data-version.json"

# server copy of SkillRaceClassInfo.dbc (exit 1 = already up to date); the restart below loads it
bash "$CP/openvanilla_server_dbc.sh" || true
# server copies of the model tables, so mangosd knows every ported model (exit 1 = up to date)
bash "$CP/openvanilla_server_models.sh" || true

say "6/6 Restarting the world server (saves every character; about a minute to come back)"
docker compose up -d --force-recreate mangosd   # one restart, on the new image when there is one
for i in $(seq 1 60); do
  s=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q mangosd)" 2>/dev/null || echo starting)
  [ "$s" = healthy ] && break; sleep 10
done
echo "world server: $s"
# the sign-in pages' realm name (web meta realm_name) was left at setup's "Our Realm" while realmd says
# "Vanilla Remastered": put the real name in unless someone already chose one (OV_REALM_NAME overrides)
RV=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Source}}{{end}}{{end}}' "$(docker compose ps -q realm)" 2>/dev/null)
if [ -f "$RV/realm.sqlite" ]; then python3 - "$RV/realm.sqlite" "${OV_REALM_NAME:-Vanilla Remastered}" "${OV_REALM_NAME:+force}" <<'PY2' || true
import sqlite3, sys
c = sqlite3.connect(sys.argv[1], timeout=10)
old = (c.execute("SELECT value FROM meta WHERE key='realm_name'").fetchone() or [None])[0]
if sys.argv[3] == "force" or old in (None, "", "Realm", "Our Realm"):
    c.execute("INSERT INTO meta (key, value) VALUES ('realm_name', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (sys.argv[2],))
    c.commit(); print("realm name on the website:", old, "->", sys.argv[2])
PY2
fi
# memory check: warn while there's still time to act (mangosd near its limit, or the host short on memory)
MU=$(docker stats --no-stream --format '{{.MemPerc}}' "$(docker compose ps -q mangosd)" 2>/dev/null | tr -d '%')
HA=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
echo "memory: world server at ${MU:-?}% of its limit, host has ${HA} MB available"
case "${MU%.*}" in 8[5-9]|9[0-9]|1[0-9][0-9]) echo "!! world server is near its memory limit: raise MANGOSD_MEM in .env";; esac
[ "${HA:-9999}" -lt 700 ] && echo "!! host is low on memory: stop the Duels/Warfront realms or resize the server"
if [ "$STAGING" = 1 ]; then
  echo; echo "Staging is up at https://$REALM_DOMAIN (log in with a password; run the live realm_up once so Caddy serves it)."; exit 0
fi
if [ "$COMMUNITY" = 1 ]; then
  echo; echo "DONE. Open Vanilla is on your realm: https://$REALM_DOMAIN/"
  exit 0
fi
if curl -fsS "https://$REALM_DOMAIN/login" | grep -q "/auth/discord/start"; then
  echo; echo "DONE. https://$REALM_DOMAIN/login now has 'Sign in with Discord'."
else
  echo; echo "Classic+ is in. The Discord button isn't showing yet: check 'docker compose logs --tail 50 realm'."
fi
echo "Last step (once): Developer Portal -> OAuth2 -> Redirects -> add https://$REALM_DOMAIN/auth/discord/callback"
echo "Sign-up feed for the website: https://$REALM_DOMAIN/community/feed.json (appears once the Herald runs here)"
