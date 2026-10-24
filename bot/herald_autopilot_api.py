"""Herald Autopilot's realm side: the autopilot API and the learning loop, as one small web service.

    python herald_autopilot_api.py            (hetzner/herald_up.sh runs it as openvanilla-herald-autopilot)

Routes (the realm's Caddy sends /api/autopilot/* and /api/herald/* here):
  GET  /api/autopilot/realm        is autoplay allowed here, and the tag autopiloted characters carry
  GET  /api/autopilot/characters   the signed-in account's characters (who is online)
  POST /api/autopilot/start        {character, plan}: hands an ONLINE character to the realm's bot AI
  POST /api/autopilot/stop|pause|resume
  GET  /api/autopilot/poll?since=  what changed (level, XP, money) and where the character is
  POST /api/herald/learn           an opted-in player's anonymous batch (gzip JSON, a few KB)
  GET  /api/herald/profiles.json   learned defaults per class and level band (ETag'd)

Sign-in: the Open Vanilla launcher's token (Authorization: Bearer …), checked with the portal's
/api/launcher/me, so Autopilot never sees a password.

Realm rules: AUTOPILOT_ALLOWED=1 turns autoplay on (off by default), and the world server needs
AiPlayerbot.SelfBotLevel = 2 (hetzner/herald_selfbot.sh). START hands the player's own online
character to the realm's bot AI over the console (SOAP): .wnl autopilot <name> on (realm/mangos
0015), then tells that AI what to do: .rndbot cmd <name> nc <strategies>. STOP gives it back
(.wnl autopilot <name> off). On a world server without 0015 the player hands the character over in
game first (the Herald addon's button, or .bot self), as before.
(.rndbot, not .bot: the playerbots core answers .bot only from a game session, "You may only add
bots from an active session"; .rndbot reaches any character from the console when the console
account is GM 2 or higher, as HELPDESK is.)

Environment (the Herald's /etc/openvanilla-herald.env):
  PORTAL_URL                 the realm portal (token check), default http://127.0.0.1:8090
  AUTOPILOT_ALLOWED          1 = on
  AUTOPILOT_TAG              shown to players, default [Autopilot]
  AUTOPILOT_PORT             default 17890
  AUTOPILOT_CMD_ON           default .rndbot cmd {name} nc {strategies}  (self-bot must be on: the in-game
                             Herald addon or .bot self, with AiPlayerbot.SelfBotLevel = 2)
  AUTOPILOT_CMD_OFF/_PAUSE/_RESUME
  AUTOPILOT_CMD_TAKE/_GIVE    default .wnl autopilot {name} on / off
  SUPPORT_DB_* + CHARACTERS_DATABASE, REALMD_DATABASE (classicrealmd)
  SOAP_URL / SOAP_USER / SOAP_PASS
  HERALD_LEARN_DB            sqlite file for learning batches, default herald_learn.db
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import time
import urllib.request
import zlib

try:
    from aiohttp import web
except ImportError:  # the pure functions (aggregate, validate) stay importable for tests
    web = None

RULE_VALUES = {
    "rest_hp": {20, 25, 30, 35, 40, 50, 60}, "rest_mana": {10, 15, 20, 25, 30, 40, 50},
    "pull": {"one", "two", "any"}, "danger": {10, 15, 20, 25, 30}, "role": {"dps", "tank", "heal"},
    "bags": {"vendor", "stop", "ignore"}, "keep": {"quest", "green", "all"}, "stop": {"30m", "1h", "2h", "ding", "never"},
}
CLASSES = {"Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock", "Druid"}
GOALS = {"level", "quest", "gather", "follow", "dungeon"}
BANDS = {"1-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60"}
# AreaTable.dbc zone ids (tools/gen_achievements.py) plus the capitals, for "where is he".
ZONES = {
    1: "Dun Morogh", 3: "Badlands", 4: "Blasted Lands", 8: "Swamp of Sorrows", 10: "Duskwood", 11: "Wetlands",
    12: "Elwynn Forest", 14: "Durotar", 15: "Dustwallow Marsh", 16: "Azshara", 17: "The Barrens", 28: "Western Plaguelands",
    33: "Stranglethorn Vale", 36: "Alterac Mountains", 38: "Loch Modan", 40: "Westfall", 41: "Deadwind Pass",
    44: "Redridge Mountains", 45: "Arathi Highlands", 46: "Burning Steppes", 47: "The Hinterlands", 51: "Searing Gorge",
    85: "Tirisfal Glades", 130: "Silverpine Forest", 139: "Eastern Plaguelands", 141: "Teldrassil", 148: "Darkshore",
    215: "Mulgore", 267: "Hillsbrad Foothills", 331: "Ashenvale", 357: "Feralas", 361: "Felwood", 400: "Thousand Needles",
    405: "Desolace", 406: "Stonetalon Mountains", 440: "Tanaris", 490: "Un'Goro Crater", 493: "Moonglade",
    618: "Winterspring", 1377: "Silithus", 1497: "Undercity", 1519: "Stormwind City", 1537: "Ironforge",
    1637: "Orgrimmar", 1638: "Thunder Bluff", 1657: "Darnassus",
}
# The app's map knows one zone so far: Elwynn Forest's WorldMapArea (left, right, top, bottom).
MAP_BOUNDS = {12: (1535.42, -1941.67, -7939.58, -10254.17)}

# Strategies Autopilot always switches off on a player's own character: the bot AI's selling, auction
# house, mail, bank, guild, crafting, battleground, duel and chatter habits (its "rpg vendor" would
# sell even an epic mount), and "maintenance" (it destroys, disenchants and opens items and abandons
# quests). Herald stays out of the economy and PvP (docs/HERALD.md). "-mount": he travels on foot
# for now (owner, 2026-10-24); "+mount" brings riding back.
SAFE = "-rpg vendor,-rpg bank,-rpg guild,-rpg craft,-rpg bg,-rpg player,-maintenance,-guild,-pvp,-bg,-arena,-lfg,-duel,-start duel,-ads,-ai chat,-say,-emote,+silent,-mount"
# Every run: never flee from two mobs (the bot AI's "flee" runs a lone character the moment it is
# outnumbered and drags it into more), potions instead; and the "herald" custom strategy
# (realm/classicplus/classicplus_herald_ai.sql) that loots each kill before the next pull. The
# Herald addon sends the same orders.
HERALD_ORDERS = ("co -flee,+potions", "nc +custom::herald")

# His class rotation for his level band (realm/classicplus/classicplus_herald_rotations.sql): the custom combat
# strategy herald_<class>_<band> on, the other bands of his class off. The Herald addon sends the same.
ROTATION_BANDS = (1, 20, 40)


def rotation_order(cls, level):
    """The combat order for a class (CLASS_IDS name or id) at a level, e.g. 'co +custom::herald_mage_20,...'."""
    name = CLASS_IDS.get(cls, cls) if isinstance(cls, int) else cls
    name = str(name or "Warrior").lower()
    level = int(level or 1)
    band = 40 if level >= 40 else 20 if level >= 20 else 1
    parts = [f"+custom::herald_{name}_{band}"] + [f"-custom::herald_{name}_{b}" for b in ROTATION_BANDS if b != band]
    return "co " + ",".join(parts)


CLASS_IDS = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid"}
MAX_BODY = 64 * 1024
MAX_RECORDS = 400
MIN_SESSIONS = 5           # per rule value before it can win
TIE = 0.03                 # within 3%: the more popular choice wins


def env(key, default=None):
    return os.environ.get(key, default)


# ------------------------------------------------------------------------------- learning: input
def _num(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo <= f <= hi else None


def validate_record(r):
    """A cleaned copy of one record, or None. Unknown fields are dropped; nothing personal fits."""
    if not isinstance(r, dict) or r.get("cls") not in CLASSES or r.get("band") not in BANDS:
        return None
    t = r.get("type")
    out = {"type": t, "cls": r["cls"], "band": r["band"]}
    if t == "session":
        if r.get("goal") not in GOALS:
            return None
        out["goal"] = r["goal"]
        for k, hi in (("minutes", 24 * 60), ("xp_per_hour", 2_000_000), ("kills", 100_000), ("deaths", 10_000),
                      ("rests", 100_000), ("levels", 60), ("quests", 10_000), ("nodes", 100_000)):
            v = _num(r.get(k, 0), 0, hi)
            if v is None:
                return None
            out[k] = v
        if out["minutes"] < 2:
            return None
        rules = r.get("rules") or {}
        out["rules"] = {k: v for k, v in rules.items() if k in RULE_VALUES and v in RULE_VALUES[k]}
        return out
    if t == "death":
        out["goal"] = r.get("goal") if r.get("goal") in GOALS else "level"
        out["rest_hp"] = r.get("rest_hp") if r.get("rest_hp") in RULE_VALUES["rest_hp"] else None
        out["pull"] = r.get("pull") if r.get("pull") in RULE_VALUES["pull"] else None
        out["adds"] = int(_num(r.get("adds", 0), 0, 10) or 0)
        out["gap"] = int(_num(r.get("gap", 0), -20, 20) or 0)
        return out
    if t == "change":
        k = r.get("key")
        if k not in RULE_VALUES or r.get("to") not in RULE_VALUES[k] or r.get("from") not in RULE_VALUES[k]:
            return None
        out.update(key=k, to=r["to"], **{"from": r["from"]}, after_death=bool(r.get("after_death")))
        return out
    return None


def client_ip(request):
    """The caller's address. X-Real-IP only counts when the request came through the local Caddy
    (which overwrites it with the real client address); anyone else could set it to anything."""
    remote = request.remote or "?"
    try:
        a = ipaddress.ip_address(remote)
        via_proxy = a.is_loopback or a.is_private
    except ValueError:
        via_proxy = False
    if via_proxy:
        return request.headers.get("X-Real-IP") or remote
    return remote


def parse_batch(raw, gzipped):
    """(install, [records]) from an upload body, or raises ValueError."""
    if len(raw) > MAX_BODY:
        raise ValueError("too large")
    if raw[:2] == b"\x1f\x8b":  # gzip (aiohttp may already have unpacked a Content-Encoding: gzip body)
        # bounded: a tiny gzip bomb must not expand to hundreds of MB before any check
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = d.decompress(raw, MAX_BODY * 8 + 1)
        except zlib.error:
            raise ValueError("bad gzip")
        if len(raw) > MAX_BODY * 8 or d.unconsumed_tail:
            raise ValueError("too large")
    body = json.loads(raw.decode("utf-8"))
    if not isinstance(body, dict) or body.get("v") != 1 or not isinstance(body.get("records"), list):
        raise ValueError("bad batch")
    install = str(body.get("install", ""))[:32]
    if not re.fullmatch(r"[0-9a-f]{8,32}", install):
        raise ValueError("bad install id")
    recs = [v for v in (validate_record(r) for r in body["records"][:MAX_RECORDS]) if v]
    return install, recs


# ------------------------------------------------------------------------------- learning: store
class LearnStore:
    """Learning records in SQLite. A batch sent twice (a retry after a lost reply) is stored once."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, day TEXT, body TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS batches (hash TEXT PRIMARY KEY, day TEXT)")
        self.db.commit()

    def add(self, install, records):
        day = time.strftime("%Y-%m-%d", time.gmtime())
        bodies = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
        h = hashlib.sha256((install + "\n".join(bodies)).encode()).hexdigest()[:32]
        try:
            self.db.execute("INSERT INTO batches (hash, day) VALUES (?, ?)", (h, day))
        except sqlite3.IntegrityError:
            return 0
        self.db.executemany("INSERT INTO records (day, body) VALUES (?, ?)", [(day, b) for b in bodies])
        self.db.commit()
        return len(bodies)

    def recent(self, days=60):
        since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
        return [json.loads(b) for (b,) in self.db.execute("SELECT body FROM records WHERE day >= ?", (since,))]


# ------------------------------------------------------------------------------- learning: output
def aggregate(records, min_sessions=MIN_SESSIONS):
    """Learned defaults: for each class, level band and rule, the value whose sessions got the most
    XP per hour once deaths are counted against it. A value needs min_sessions sessions to win, and
    a rule needs two values to compare; within 3% of the best, the value players switch TO most
    often wins (so the crowd's taste breaks near-ties)."""
    sessions = {}
    popularity = {}
    deaths = {}
    for r in records:
        key = (r.get("cls"), r.get("band"))
        if r.get("type") == "session":
            sessions.setdefault(key, []).append(r)
        elif r.get("type") == "change":
            p = popularity.setdefault(key, {}).setdefault(r["key"], {})
            p[r["to"]] = p.get(r["to"], 0) + (2 if r.get("after_death") else 1)
        elif r.get("type") == "death":
            deaths[key] = deaths.get(key, 0) + 1
    classes = {}
    for (cls, band), rows in sessions.items():
        out = {}
        for rule in RULE_VALUES:
            by_value = {}
            for s in rows:
                v = s.get("rules", {}).get(rule)
                if v is None:
                    continue
                hours = max(s["minutes"] / 60, 1 / 30)
                dph = s["deaths"] / hours
                score = s["xp_per_hour"] * max(0.4, 1 - 0.06 * dph)
                by_value.setdefault(v, []).append(score)
            eligible = {v: sum(sc) / len(sc) for v, sc in by_value.items() if len(sc) >= min_sessions}
            if len(eligible) < 2:
                continue
            best = max(eligible.values())
            near = [v for v, sc in eligible.items() if sc >= best * (1 - TIE)]
            pop = popularity.get((cls, band), {}).get(rule, {})
            pick = max(near, key=lambda v: (pop.get(v, 0), eligible[v]))
            out[rule] = {"value": pick, "sessions": len(by_value[pick]), "score": round(eligible[pick]),
                         "compared": len(eligible)}
        if out:
            classes.setdefault(cls, {})[band] = out
    return {"v": 1, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sessions": sum(len(v) for v in sessions.values()), "classes": classes}


# ------------------------------------------------------------------------------- the realm
class Realm:
    """Accounts, characters and the world console. Every query names its columns; CMaNGOS classic."""

    def __init__(self):
        self.db = dict(host=env("SUPPORT_DB_HOST", "127.0.0.1"), port=int(env("SUPPORT_DB_PORT", "13306")),
                       user=env("SUPPORT_DB_USER", "herald"), password=env("SUPPORT_DB_PASS"),
                       connect_timeout=6, autocommit=True)
        self.chars_db = env("CHARACTERS_DATABASE", "classiccharacters")
        self.realmd_db = env("REALMD_DATABASE", "classicrealmd")
        self.soap = (env("SOAP_URL", "http://127.0.0.1:17878/"), env("SOAP_USER"), env("SOAP_PASS"))

    def _q(self, sql, args=()):
        import pymysql
        con = pymysql.connect(**self.db)
        try:
            cur = con.cursor()
            cur.execute(sql, args)
            return cur.fetchall()
        finally:
            con.close()

    def characters(self, username):
        rows = self._q(f"SELECT c.guid, c.name, c.class, c.level, c.zone, c.online, c.money, c.xp "
                       f"FROM `{self.chars_db}`.characters c JOIN `{self.realmd_db}`.account a ON a.id = c.account "
                       f"WHERE a.username = %s ORDER BY c.online DESC, c.level DESC", (username.upper(),))
        return [{"guid": r[0], "name": r[1], "cls": CLASS_IDS.get(r[2], "?"), "level": r[3], "zone_id": r[4],
                 "online": bool(r[5]), "money": r[6], "xp": r[7]} for r in rows]

    def class_level(self, name):
        """(class id, level) of a character by name, or None."""
        rows = self._q(f"SELECT class, level FROM `{self.chars_db}`.characters WHERE name = %s", (name,))
        return (int(rows[0][0]), int(rows[0][1])) if rows else None

    def details(self, guid):
        """Where the character is, its bags and quest log (all read-only, the characters database;
        item and quest names from the world database when the herald login may read them)."""
        guid = int(guid)
        row = self._q(f"SELECT position_x, position_y, map, zone FROM `{self.chars_db}`.characters WHERE guid = %s", (guid,))
        if not row:
            return None
        x, y, m, zone = row[0]
        bags_sql = (f"SELECT ii.itemEntry, ii.count FROM `{self.chars_db}`.character_inventory ci "
                    f"JOIN `{self.chars_db}`.item_instance ii ON ii.guid = ci.item "
                    f"WHERE ci.guid = %s AND ((ci.bag = 0 AND ci.slot BETWEEN 23 AND 38) OR ci.bag IN "
                    f"(SELECT b.item FROM `{self.chars_db}`.character_inventory b WHERE b.guid = %s AND b.bag = 0 "
                    f"AND b.slot BETWEEN 19 AND 22))")
        items = self._q(bags_sql, (guid, guid))
        quests = self._q(f"SELECT quest, status FROM `{self.chars_db}`.character_queststatus "
                         f"WHERE guid = %s AND rewarded = 0 AND status IN (1, 3)", (guid,))
        done = self._q(f"SELECT COUNT(*) FROM `{self.chars_db}`.character_queststatus WHERE guid = %s AND rewarded = 1", (guid,))
        names, titles = {}, {}
        world = env("WORLD_DATABASE", "classicmangos")
        try:
            ids = sorted({int(i[0]) for i in items})
            if ids:
                for e, n, q in self._q(f"SELECT entry, name, Quality FROM `{world}`.item_template WHERE entry IN "
                                        f"({','.join(['%s'] * len(ids))})", tuple(ids)):
                    names[int(e)] = (n, int(q))
            qids = sorted({int(q[0]) for q in quests})
            if qids:
                for e, t in self._q(f"SELECT entry, Title FROM `{world}`.quest_template WHERE entry IN "
                                     f"({','.join(['%s'] * len(qids))})", tuple(qids)):
                    titles[int(e)] = t
        except Exception:
            pass   # no SELECT on the world database for this login: ids only
        return {"x": float(x), "y": float(y), "map": int(m), "zone_id": int(zone),
                "items": [(int(e), int(c)) for e, c in items], "names": names,
                "quests": [(int(q), int(st)) for q, st in quests], "titles": titles,
                "done": int(done[0][0]) if done else 0}

    def console(self, command):
        url, user, pw = self.soap
        if not user:
            raise RuntimeError("SOAP_USER is not set")
        body = ('<?xml version="1.0" encoding="utf-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
                'xmlns:ns1="urn:MaNGOS"><SOAP-ENV:Body><ns1:executeCommand><command>'
                + command.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + "</command></ns1:executeCommand></SOAP-ENV:Body></SOAP-ENV:Envelope>")
        req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
            "Content-Type": "text/xml", "Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()})
        with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 - the realm's own console on localhost
            xml = r.read().decode("utf-8", "replace")
        fault = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.S)
        if fault:
            raise RuntimeError(fault.group(1).strip())
        m = re.search(r"<result>(.*?)</result>", xml, re.S)
        return (m.group(1) if m else "").strip()


def strategies_text(plan):
    """'+grind,+quest,+loot' from a plan; only the bot AI's own strategy words get through."""
    words = list(plan.get("noncombat", [])) + list(plan.get("combat", []))
    ok = [w for w in words if re.fullmatch(r"[+-][a-z]+( [a-z]+)?", str(w))]
    return ",".join(ok)[:200]


def money(copper):
    g, rest = divmod(int(copper), 10000)
    sv, c = divmod(rest, 100)
    parts = [f"{g}g"] * bool(g) + [f"{sv}s"] * bool(sv) + [f"{c}c"] * bool(c or not (g or sv))
    return " ".join(parts)


def events_between(prev, cur, now):
    """Events from two looks at the same character (the characters table)."""
    out = []
    if not prev or not cur:
        return out
    if cur["level"] > prev["level"]:
        out.append({"t": now, "kind": "level", "text": f"Level {cur['level']}!", "data": {"level": cur["level"]}})
    elif cur["xp"] > prev["xp"]:
        out.append({"t": now, "kind": "xp", "text": f"+{cur['xp'] - prev['xp']} XP.", "data": {"xp": cur["xp"] - prev["xp"]}})
    if cur["money"] > prev["money"]:
        gain = cur["money"] - prev["money"]
        out.append({"t": now, "kind": "loot", "text": f"Money +{money(gain)}.",
                    "data": {"copper": gain, "items": 0}})
    if cur["online"] != prev["online"]:
        out.append({"t": now, "kind": "state", "text": "Character is " + ("online." if cur["online"] else "offline: autopilot stopped."),
                    "data": {}})
    return out


def shape_detail(raw):
    """Realm.details() -> what the app shows: zone, map point, bags, quest log."""
    if not raw:
        return None
    zone = ZONES.get(raw.get("zone_id"), "")
    out = {"zone": zone, "zone_id": raw.get("zone_id"), "done": raw.get("done", 0)}
    b = MAP_BOUNDS.get(raw.get("zone_id"))
    if b:
        left, right, top, bottom = b
        u = (left - raw["y"]) / (left - right)
        v = (top - raw["x"]) / (top - bottom)
        if 0 <= u <= 1 and 0 <= v <= 1:
            out["uv"] = (round(u, 4), round(v, 4))
    names = raw.get("names") or {}
    bags = {}
    for entry, count in raw.get("items") or []:
        bags[entry] = bags.get(entry, 0) + count
    out["bags"] = [{"name": names.get(e, (f"Item {e}", 1))[0], "icon": "", "count": c,
                    "quality": names.get(e, ("", 1))[1]} for e, c in sorted(bags.items())]
    out["bag_slots"] = 16
    titles = raw.get("titles") or {}
    out["quests"] = [{"id": q, "title": titles.get(q, f"Quest {q}"), "complete": st == 1}
                     for q, st in raw.get("quests") or []]
    return out


def detail_events(prev, cur, now):
    """Events from two looks at the details: quests taken, ready, turned in; a new zone."""
    out = []
    if not prev or not cur:
        return out
    if cur.get("zone") and cur.get("zone") != prev.get("zone"):
        out.append({"t": now, "kind": "travel", "text": f"Now in {cur['zone']}.", "data": {"zone": cur["zone"]}})
    before = {q["id"]: q for q in prev.get("quests") or []}
    for q in cur.get("quests") or []:
        old = before.get(q["id"])
        if not old:
            out.append({"t": now, "kind": "quest", "text": f"Took the quest {q['title']}.", "data": {"quest": q["id"], "step": "take"}})
        elif q["complete"] and not old["complete"]:
            out.append({"t": now, "kind": "quest", "text": f"{q['title']}: objectives done.", "data": {"quest": q["id"], "step": "done"}})
    turned = cur.get("done", 0) - prev.get("done", 0)
    if turned > 0:
        out.append({"t": now, "kind": "quest", "text": f"Turned in {turned} quest{'s' * (turned > 1)}.", "data": {"turned_in": turned, "step": "turn in"}})
    return out


# ------------------------------------------------------------------------------- the web app
def make_app(realm=None, store=None, who=None, clock=time.time):
    """who(token) -> username or None. Injected in tests; defaults to the portal check."""
    realm = realm or Realm()
    store = store or LearnStore(env("HERALD_LEARN_DB", "herald_learn.db"))
    allowed = env("AUTOPILOT_ALLOWED", "0") == "1"
    tag = env("AUTOPILOT_TAG", "")
    # The realm's bot AI in self-bot mode. "take" puts the character in it from the console (0015's
    # .wnl autopilot); without 0015 the player turns it on in game (the Herald addon, or .bot self).
    idle = "-grind,-rpg,-rpg quest,-quest,-travel,-gather,-explore,+stay"
    cmds = {k: env("AUTOPILOT_CMD_" + k.upper(), d) for k, d in (
        ("on", ".rndbot cmd {name} nc {strategies}," + SAFE), ("off", ".rndbot cmd {name} nc " + idle),
        ("pause", ".rndbot cmd {name} nc " + idle), ("resume", ".rndbot cmd {name} nc {strategies}," + SAFE),
        ("take", ".wnl autopilot {name} on"), ("give", ".wnl autopilot {name} off"))}

    def herald_orders(name):
        """The fight and loot orders after a goal; an older realm that refuses one isn't fatal."""
        orders = list(HERALD_ORDERS)
        try:
            cl = realm.class_level(name)
            if cl:
                orders.append(rotation_order(*cl))
        except Exception:
            pass
        for order in orders:
            try:
                realm.console(f".rndbot cmd {name} {order}")
            except Exception:
                pass
    take_wait = float(env("AUTOPILOT_TAKE_WAIT", "1.5"))   # the bot AI settles before its first order
    tokens = {}       # token -> (username, checked_at)
    runs = {}         # username -> {"name", "seq", "events", "last"}
    hits = {}         # ip -> [times] for /learn
    cache = {"profiles": None, "etag": "", "at": 0.0}

    def portal_who(token):
        url = env("PORTAL_URL", "http://127.0.0.1:8090").rstrip("/") + "/api/launcher/me"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:  # nosec B310 - our own portal
                body = json.loads(r.read().decode() or "{}")
                return body.get("user") or body.get("username")
        except Exception:
            return None

    check = who or portal_who

    def user_of(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:].strip()
        hit = tokens.get(token)
        if hit and clock() - hit[1] < 300:
            return hit[0]
        name = check(token)
        if name:
            tokens[token] = (name, clock())
        return name

    def j(data, status=200):
        return web.json_response(data, status=status)

    async def realm_info(_request):
        return j({"name": env("REALM_NAME", "Vanilla Remastered"), "autoplay_allowed": allowed, "tag": tag,
                  "learning": True, "message": "" if allowed else "Autoplay is off on this realm."})

    async def characters(request):
        user = user_of(request)
        if not user:
            return j({"message": "Sign in with the Open Vanilla launcher first."}, 401)
        try:
            return j({"characters": realm.characters(user)})
        except Exception as e:
            return j({"message": f"The realm's database didn't answer ({type(e).__name__})."}, 503)

    async def start(request):
        user = user_of(request)
        if not user:
            return j({"message": "Sign in first."}, 401)
        if not allowed:
            return j({"message": "Autoplay is off on this realm."}, 403)
        body = await request.json()
        name = str(body.get("character", ""))
        chars = {c["name"]: c for c in realm.characters(user)}
        c = chars.get(name)
        if not c:
            return j({"message": "That character isn't on your account."}, 404)
        if not c["online"]:
            return j({"message": f"Log {name} in first; Autopilot takes over a character that's in the world."}, 409)
        strategies = strategies_text(body.get("plan") or {})
        # 1. Hand the character to the bot AI from here (0015). An older world server answers nothing.
        try:
            took = (realm.console(cmds["take"].format(name=name)) or "").strip()
        except Exception:
            took = ""
        low = took.lower()
        if "refused" in low:
            why = ("Herald is switched off on this realm." if ("disabled" in low or "permission" in low)
                   else f"The realm's bot AI said no: {took}")
            return j({"message": why}, 409)
        if "not online" in low:
            return j({"message": f"Log {name} in first; Autopilot takes over a character that's in the world."}, 409)
        if " - on" in low or "already on" in low:
            await asyncio.sleep(take_wait)
        # 2. Tell the AI what to do.
        try:
            out = realm.console(cmds["on"].format(name=name, strategies=strategies or "+grind"))
        except Exception as e:
            return j({"message": f"The world server refused: {e}"}, 502)
        if "no AI" in (out or "") or "failed" in (out or ""):
            return j({"message": f"Turn Herald on in game first: the Herald button by {name}'s minimap (or type .bot self)."}, 409)
        herald_orders(name)
        runs[user] = {"name": name, "guid": c.get("guid"), "seq": 0, "events": [], "last": c,
                      "strategies": strategies or "+grind", "detail": None}
        return j({"message": f"{name} is playing on the realm's own AI. You can watch in game; "
                             f"Take back control on the Herald panel (or .bot self) ends it any time."})

    async def simple(request, which):
        user = user_of(request)
        if not user:
            return j({"message": "Sign in first."}, 401)
        run = runs.get(user)
        if not run:
            return j({"message": "Nothing is running."}, 409)
        try:
            realm.console(cmds[which].format(name=run["name"], strategies=run.get("strategies", "+grind")))
            if which == "resume":
                herald_orders(run["name"])
            if which == "off":
                realm.console(cmds["give"].format(name=run["name"]))   # back to the player (0015)
        except Exception as e:
            return j({"message": f"The world server refused: {e}"}, 502)
        if which == "off":
            runs.pop(user, None)
        return j({"message": {"off": "Stopped.", "pause": "Paused.", "resume": "Resumed."}[which]})

    async def stop(request):
        return await simple(request, "off")

    async def pause(request):
        return await simple(request, "pause")

    async def resume(request):
        return await simple(request, "resume")

    async def poll(request):
        user = user_of(request)
        if not user:
            return j({"message": "Sign in first."}, 401)
        run = runs.get(user)
        if not run:
            return j({"seq": 0, "events": [], "state": None})
        cur = {c["name"]: c for c in realm.characters(user)}.get(run["name"])
        now = clock()
        for e in events_between(run["last"], cur, now):
            run["seq"] += 1
            e["seq"] = run["seq"]
            run["events"].append(e)
        detail = None
        if cur and hasattr(realm, "details"):
            try:
                detail = shape_detail(realm.details(cur["guid"]))
            except Exception:
                detail = None
        for e in detail_events(run.get("detail"), detail, now):
            run["seq"] += 1
            e["seq"] = run["seq"]
            run["events"].append(e)
        run["detail"] = detail or run.get("detail")
        del run["events"][:-200]
        run["last"] = cur or run["last"]
        since = int(request.query.get("since", "0") or 0)
        events = [e for e in run["events"] if e["seq"] > since]
        c = run["last"]
        state = {"name": c["name"], "cls": c["cls"], "level": c["level"], "xp": c["xp"], "money": c["money"],
                 "status": "travel" if c["online"] else "idle", "pos": None, "path": [], "bags": None}
        d = run.get("detail")
        if d:
            state["zone"] = d.get("zone")
            state["quests"] = d.get("quests")
            if d.get("bags") is not None:
                state["bags"] = d["bags"]
                state["bag_slots"] = d.get("bag_slots", 16)
            uv = d.get("uv")
            if uv:
                state["pos"] = uv
                trail = run.setdefault("path", [])
                if not trail or abs(trail[-1][0] - uv[0]) + abs(trail[-1][1] - uv[1]) > 0.01:
                    trail.append(uv)
                    del trail[:-40]
                state["path"] = list(trail)
        return j({"seq": run["seq"], "events": events, "state": state})

    async def learn(request):
        ip = client_ip(request)
        now = clock()
        if len(hits) > 5000:  # forget quiet addresses so the table can't grow without end
            for k in [k for k, v in hits.items() if not v or now - v[-1] > 3600]:
                hits.pop(k, None)
        recent = [t for t in hits.get(ip, []) if now - t < 3600]
        if len(recent) >= 12:
            return j({"message": "Too many uploads; try later."}, 429)
        hits[ip] = recent + [now]
        raw = await request.content.read(MAX_BODY + 1)
        try:
            install, recs = parse_batch(raw, request.headers.get("Content-Encoding", "") == "gzip")
        except Exception:
            return j({"message": "Not a learning batch."}, 400)
        added = store.add(install, recs)
        cache["at"] = 0  # rebuild profiles on the next read
        return j({"accepted": added, "dropped": len(recs) - added})

    async def profiles(request):
        if not cache["profiles"] or clock() - cache["at"] > 600:
            data = aggregate(store.recent())
            text = json.dumps(data, separators=(",", ":"))
            cache.update(profiles=text, etag='"' + hashlib.sha1(json.dumps(data["classes"], sort_keys=True).encode()).hexdigest()[:16] + '"',
                         at=clock())
        if request.headers.get("If-None-Match") == cache["etag"]:
            return web.Response(status=304)
        return web.Response(text=cache["profiles"], content_type="application/json",
                            headers={"ETag": cache["etag"], "Cache-Control": "public, max-age=300"})

    app = web.Application(client_max_size=MAX_BODY * 2)
    app.add_routes([web.get("/api/autopilot/realm", realm_info), web.get("/api/autopilot/characters", characters),
                    web.post("/api/autopilot/start", start), web.post("/api/autopilot/stop", stop),
                    web.post("/api/autopilot/pause", pause), web.post("/api/autopilot/resume", resume),
                    web.get("/api/autopilot/poll", poll), web.post("/api/herald/learn", learn),
                    web.get("/api/herald/profiles.json", profiles)])
    return app


if __name__ == "__main__":
    if web is None:
        raise SystemExit("pip install aiohttp")
    web.run_app(make_app(), host=env("AUTOPILOT_HOST", "0.0.0.0"), port=int(env("AUTOPILOT_PORT", "17890")))
