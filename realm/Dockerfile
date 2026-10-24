# Open Vanilla realm image: the stock wenilla-realm image with the service AND the browser client
# rebuilt from the same commit plus Open Vanilla's patches (realm/patches/*.patch):
#   0001  Discord sign-in (service)
#   0002  addon engine fixes G1–G5 (client): realm-patch addons, saved settings on the web,
#         UnitCanAssist / UnitIsTrivial, the chat edit box's input-language script
#   0003  launcher sign-in (service): /auth/launcher loopback flow, one-time codes, launcher tokens
#   0004  login backdrop (client + play page): no 3D gate and a transparent canvas on the login
#         screen, so login-backdrop/ (a looping video, copied in below) shows behind the form
#   0005  character create (client): a nine-slot class grid (five across, 36 px), so Classic+ races
#         with eight or nine classes no longer run into the dials below it
#   0016  sign-in (service): the Open Vanilla sign-in page (art in assets/brand, served at /brand/),
#         Discord straight from the button, no Discord trip when already signed in, back to the
#         page that asked, "Continue as …", 60-day sliding sessions that rotate only on page loads
#   0017  guest accounts (service): "Play free as a guest" (a key cookie on the device), resume on
#         that device, link Discord later to keep the characters; per-IP and daily limits,
#         idle guests removed after 30 days. OPENVANILLA_GUESTS=0 turns it off.
#   0019  dressing room (client): an addon's named DressUpModel (the Transmog window) draws the
#         3D character, turns and empties with it; anonymous model panes can't undress it. Sets
#         OPENVANILLA_ONE_DRESSING_ROOM so addons know one dressing room draws at a time.
#   0020  faster loads (client page + build) and the Open Vanilla name (service pages): the wasm is
#         compiled from the fetched Response so browsers can cache the compiled code, 24 boot
#         downloads at once, brotli -q 11, a build without wasm-opt fails (WEB_REQUIRE_OPT, below)
#   0028  no falling through the world on load (client): when the stream stalls before the tile under the
#         body has ground, the settle hold keeps the body still (up to 45 s) instead of turning gravity on
#   0031  Hero IDs (service): a Hero Key also makes an Ed25519 key pair; its public half (ovh1....) is shown on the
#         key page, proves Legends are yours (opt-in), signs in without sending the key (/auth/hero), and is
#         listed for Legend issuers at /api/heroes.json; /api/hero/verify checks a Hero ID's signature for any site
#   0032  Hero Keys for guests (service): the key is made as a guest presses "Play now" and they go straight into
#         the game; the in-game Hero Key window shows it with how to keep it (download a .txt, copy, or write it
#         down) until it is saved; key files are plain "OpenVanilla Hero Key.txt"; /key reads a dropped or chosen
#         file's whole text (drop anywhere on the page), and its key-file part shows only with ?debug=1 (title "DEBUG ·")
#   0033  Herald presence (client): Herald's server rides count as input for the idle timer (no AFK, no sit,
#         no 30-minute logout while he plays; a taxi flight keeps the 1.12 timer), and a ride whose path
#         runs inside a hill is put on the hill's surface
#   0034  Alt+Enter full screen (play page): toggles full screen like the 1.12 client's Alt+Enter; a loading tip
#   0036  the sign-in page puts Play now first, then Google, then Discord ("also joins you to our Discord")
#   0037  "Save in this browser": the Hero Key kept like a password; "Use the key saved in this browser" signs in
#   0038  Discord is a "Join our Discord" button; sign in as a guest or with Google (a small line for old Discord players)
#   0039  desktop game through the website (service): /ws/3724 and /ws/8085 also take the launcher token
#         (Authorization: Bearer), so the launcher bridges the desktop client without public game ports
#   0040  ground guard (client): a walk is never let off into ground still streaming in; the body holds,
#         gravity off, until its own tile's colliders arrive ("walked five steps, fell through the world")
#   0041  play page: a software GPU adapter (SwiftShader, llvmpipe) warns before loading, with "Play anyway"
#         and ?softgpu=1 to skip it
#   0042  launcher sign-in (service): ?via=google (straight to Google) and ?via=key (the Hero Key page);
#         POST /api/launcher/hero (the launcher signs in with the Hero Key it keeps, no browser) and
#         POST /api/launcher/herokey (a launcher token gets the account's first key, or a new one)
# The workflow (.github/workflows/realm-image.yml) compiles the browser client and the realm
# service on the runner, where their build cache survives between runs, and stages them in out/:
#   out/wenilla-realm   cargo build --release -p wenilla-realm
#   out/www/            scripts/web-build.sh's web/dist (without its index.html)
# This file only lays them onto the upstream image. Never built on the game server.
ARG BASE=ghcr.io/arnesen/wenilla-realm:latest
FROM ${BASE}
LABEL org.opencontainers.image.source="https://github.com/orionopenwow/OpenVanilla" \
      org.opencontainers.image.description="wenilla-realm + Open Vanilla Discord sign-in and addon engine fixes"
COPY out/wenilla-realm /app/wenilla-realm
COPY out/www/ /app/www/
# Open Vanilla login backdrop: the page module, a 1.3 MB looping video (VP9 fallback) and its poster (see 0004).
COPY login-backdrop/ /app/www/
