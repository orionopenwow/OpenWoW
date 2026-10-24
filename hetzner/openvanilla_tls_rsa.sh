#!/usr/bin/env bash
# Moves the realm's HTTPS certificates to RSA, so their chain ends at ISRG Root X1.
#
#   bash /opt/openvanilla-classicplus/repo/hetzner/openvanilla_tls_rsa.sh
#
# Why: Let's Encrypt's ECDSA certificates (intermediates YE1/YE2) chain by default through ISRG Root
# X2's cross-sign by ISRG Root X1. Browsers find another path, but the launcher is Python: it trusts only
# the roots Windows has installed, and where X2 isn't one of them it took the cross-sign and failed with
# "certificate has expired" (sign-in and Online mode, 2026-10-24). RSA certificates (YR1/YR2) chain to
# X1 alone, which every trust store has.
# What it does: adds "key_type rsa2048" to the live Caddyfile (openvanilla_realm_up.sh writes it there
# too), checks the config, sets the ECDSA certificates aside, restarts Caddy (HTTPS is down a few
# seconds while it gets new ones), then shows each site's chain. Safe to run again.
set -euo pipefail
CP=${OW_CP:-/opt/openvanilla-classicplus}
REALM_DIR=${OW_REALM_DIR:-/opt/wenilla-realm}
CF="$CP/Caddyfile"
cd "$REALM_DIR"
[ -f "$CF" ] || { echo "No Caddyfile at $CF"; exit 1; }

if grep -q 'key_type rsa2048' "$CF"; then
  echo "Caddyfile: already asks for RSA certificates."
else
  cp "$CF" "$CF.before-rsa-$(date +%Y%m%d-%H%M%S)"
  python3 - "$CF" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
block = ("{\n\t# RSA certificates: chained to ISRG Root X1, which every trust store has (openvanilla_tls_rsa.sh)\n"
         "\tkey_type rsa2048\n}\n")
lines = s.split("\n")
# after the comment lines at the top; a global-options block already there gets the line instead
i = 0
while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
    i += 1
if i < len(lines) and lines[i].strip() == "{":
    lines.insert(i + 1, "\tkey_type rsa2048")
    s = "\n".join(lines)
else:
    s = "\n".join(lines[:i]) + ("\n" if i else "") + block + "\n".join(lines[i:])
open(p, "w").write(s)
PY
  echo "Caddyfile: now asks for RSA certificates."
fi
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 \
  || { echo "Caddy rejects the new Caddyfile; nothing restarted. The old one is $CF.before-rsa-*"; docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | tail -5; exit 1; }

# ECDSA certificates in Caddy's storage are kept until they near expiry, whatever the config says:
# move them aside (inside the volume), so Caddy gets RSA ones on its restart.
# (the site names come from storage: the live Caddyfile names the realm by {$REALM_DOMAIN})
names=$(docker compose exec -T caddy sh -c 'ls -d /data/caddy/certificates/*/* 2>/dev/null | xargs -n1 basename' | tr -d '\r' | grep -v '^wildcard_' | sort -u)
moved=$(docker compose exec -T caddy sh -c '
  keep=/data/caddy/ecdsa-set-aside-$(date +%s); for d in /data/caddy/certificates/*/*; do
    [ -d "$d" ] || continue; k=$(ls "$d"/*.key 2>/dev/null | head -1); [ -n "$k" ] || continue
    if grep -q "BEGIN EC PRIVATE KEY" "$k"; then mkdir -p "$keep"; mv "$d" "$keep/"; basename "$d"; fi
  done' | tr -d '\r')
echo "ECDSA certificates set aside: $(echo $moved)"
[ -n "$names" ] || names=$(docker compose exec -T caddy printenv REALM_DOMAIN | tr -d '\r')
docker compose restart caddy >/dev/null
echo "Caddy restarted; waiting for the new certificates..."

for i in $(seq 1 24); do
  ok=1
  for h in $names; do
    echo | timeout 10 openssl s_client -connect 127.0.0.1:443 -servername "$h" 2>/dev/null | grep -q 'i:.*YR[0-9]' || ok=0
  done
  [ $ok = 1 ] && break; sleep 5
done
for h in $names; do
  chain=$(echo | timeout 10 openssl s_client -connect 127.0.0.1:443 -servername "$h" -showcerts 2>/dev/null | grep -E '^ *[0-9]+ s:|^ *i:' | sed -E 's/.*CN ?= ?//' | paste -sd'>' -)
  case "$chain" in *YR*) echo "  OK   $h  ($chain)";; *) echo "  OLD  $h  ($chain): Caddy may still be getting it; run this again in a minute";; esac
done
