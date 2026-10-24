#!/usr/bin/env python3
"""Touch lab: real touches on an emulated phone, through the play page's own touch layer, into a
stand-in that takes input the way the browser client does (see lab.html).

    python3 devkit/touchlab/run.py                  every phone profile, prints PASS/FAIL per case
    python3 devkit/touchlab/run.py --show           also saves a screenshot per case (_local/touchlab)

Needs Playwright with Chromium (pip install playwright; python -m playwright install chromium),
or CHROMIUM=/path/to/chrome. Exit code 1 when a case fails.
"""
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# phones as they report themselves: css viewport, pixel ratio; the buffer as the client draws it
PROFILES = [
    ("Android 2.625 (Pixel-class)", {"width": 914, "height": 411}, 2.625, "&luams=40"),
    ("iPhone 3x", {"width": 852, "height": 393}, 3, ""),
    ("Tablet 2x", {"width": 1180, "height": 820}, 2, ""),
    ("Page-sized buffer 2x (desktop emulation)", {"width": 914, "height": 411}, 2, "&buffer=page"),
    # a busy phone: the game takes ~70 ms a frame (about 14 fps) on the page's own thread
    ("Slow phone 14 fps", {"width": 914, "height": 411}, 2.625, "&work=70&luams=90"),
    ("Very slow phone 8 fps", {"width": 914, "height": 411}, 2.625, "&work=120&luams=150"),
    # the game's update on its own clock, behind the page's frames (Android Chrome, 2026-10-24)
    ("Game lags the page (an update every 90 ms)", {"width": 914, "height": 411}, 2.625, "&gamelag=90"),
    # in the world: taps go through the world layer (camera drags, targeting, game windows)
    ("In world: Android", {"width": 914, "height": 411}, 2.625, "&state=inworld&luams=40"),
    # (no busy frames here: the lab's synthetic touches would wait on them and turn a tap into a long press;
    #  a phone stamps touches with the hardware's time, so a slow game can't do that to a real tap)
    ("In world: slow bridge (Lua answers in 150 ms)", {"width": 914, "height": 411}, 2.625, "&state=inworld&luams=150"),
    ("In world: game lags the page (an update every 90 ms)", {"width": 914, "height": 411}, 2.625, "&state=inworld&gamelag=90"),
]


def slow_ms(extra, fast):
    """How long a case waits for the click to play out: a tap waits for the game's own updates."""
    if "work=120" in extra:
        return 3500
    return 2200 if any(k in extra for k in ("work=", "gamelag=", "luams=150")) else max(fast, 900)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    show = "--show" in sys.argv
    srv = serve()
    url = f"http://127.0.0.1:{srv.server_address[1]}/devkit/touchlab/lab.html?touch=1&touchdebug=1"
    exe = os.environ.get("CHROMIUM")
    failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        for name, vp, dpr, extra in PROFILES:
            ctx = browser.new_context(viewport=vp, device_scale_factor=dpr, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url + extra)
            page.wait_for_function("window.lab && window.lab.ready && window.lab.frames > 5", timeout=15000)
            page.wait_for_timeout(1200)                           # the button scan runs every 0.8 s
            # a phone's first tap in landscape goes full screen (touch.js), as on the real page
            page.touchscreen.tap(vp["width"] * 0.2, vp["height"] * 0.2)
            page.wait_for_timeout(900)
            cases = []
            b = page.evaluate("lab.buttonCss()")
            plain = (("tap on the button", 0, 0),) + ((("tap 12 px below it (snap)", 0, 12),) if "inworld" not in extra else ())
            for label, dx, dy in plain:   # snapping is for the glue screens; game windows in the world take the tap as is
                before = page.evaluate("lab.clicks")
                page.touchscreen.tap(b["x"] + dx, b["y"] + dy)
                page.wait_for_timeout(slow_ms(extra, 500))
                after = page.evaluate("lab.clicks")
                cases.append((label, after - before == 1))
            # a real thumb: it lands, rolls a few pixels while down, and lifts (raw CDP touches)
            cdp = ctx.new_cdp_session(page)
            def touch(kind, x, y):
                cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})
            for label, roll, hold in (("tap with a 6 px roll", 6, 60), ("tap with a 14 px roll", 14, 60),
                                      ("tap with a 16 px roll, quick lift", 16, 20), ("slow tap (0.3 s) with a 9 px roll", 9, 300)):
                before = page.evaluate("lab.clicks")
                x, y = b["x"], b["y"]
                touch("touchStart", x, y)
                for k in range(1, 4):
                    page.wait_for_timeout(hold // 3)
                    touch("touchMove", x + roll * k / 3, y + roll * k / 6)
                touch("touchEnd", 0, 0)
                page.wait_for_timeout(slow_ms(extra, 600))   # a slow phone finishes the click a few frames later
                cases.append((label, page.evaluate("lab.clicks") - before == 1))
            if "inworld" not in extra:
                # Android Chrome: the address bar moves while the finger is down, and the page's
                # height changes by a few px under the tap; the tap must still click
                x, y = b["x"], b["y"]
                before = page.evaluate("lab.clicks")
                touch("touchStart", x, y)
                page.wait_for_timeout(60)
                page.set_viewport_size({"width": vp["width"], "height": vp["height"] - 6})
                page.wait_for_timeout(60)
                touch("touchEnd", 0, 0)
                page.wait_for_timeout(slow_ms(extra, 800))
                cases.append(("tap while the address bar resizes the page by 6 px", page.evaluate("lab.clicks") - before == 1))
                page.set_viewport_size(vp)
                page.wait_for_timeout(1000)
                b = page.evaluate("lab.buttonCss()")
                # a quick tap the browser ends with pointercancel instead of pointerup
                before = page.evaluate("lab.clicks")
                page.evaluate("""([x, y]) => new Promise((done) => {
                  const el = document.elementFromPoint(x, y);
                  const o = { bubbles: true, cancelable: true, pointerId: 77, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y };
                  el.dispatchEvent(new PointerEvent('pointerdown', { ...o, button: 0, buttons: 1 }));
                  setTimeout(() => { el.dispatchEvent(new PointerEvent('pointercancel', { ...o, button: 0, buttons: 0 })); done(); }, 70);
                })""", [b["x"], b["y"]])
                page.wait_for_timeout(slow_ms(extra, 800))
                cases.append(("a quick tap the browser cancels still clicks", page.evaluate("lab.clicks") - before == 1))
            if "inworld" in extra:
                # a game window's button: pushed in while the finger is on it, out (the click) on lift
                x, y = b["x"], b["y"]
                before = page.evaluate("lab.clicks")
                touch("touchStart", x, y)
                page.wait_for_timeout(250 if slow_ms(extra, 0) < 2000 else 450)   # under LONG_MS (500): still a tap
                held_down = page.evaluate("lab.down")
                touch("touchEnd", 0, 0)
                page.wait_for_timeout(slow_ms(extra, 600))
                cases.append(("a button shows pushed while the finger is on it, and clicks on lift",
                              held_down and page.evaluate("lab.clicks") - before == 1 and not page.evaluate("lab.down")))
                # held past a long press: the tooltip, no click, and nothing left pushed
                page.wait_for_timeout(400)
                before = page.evaluate("lab.clicks")
                touch("touchStart", x, y)
                page.wait_for_timeout(800)
                touch("touchEnd", 0, 0)
                page.wait_for_timeout(slow_ms(extra, 700))
                cases.append(("a long press on a button: no click, and it pops back out",
                              page.evaluate("lab.clicks") == before and not page.evaluate("lab.down")))
                # two quick taps on a window's button are two clicks (paging, +/-, Next), never a right-click
                page.wait_for_timeout(500)
                before, rbefore = page.evaluate("lab.clicks"), page.evaluate("lab.rclicks")
                page.touchscreen.tap(x, y)
                page.wait_for_timeout(150)
                page.touchscreen.tap(x, y)
                page.wait_for_timeout(slow_ms(extra, 900))
                cases.append(("two quick taps on a window's button: two clicks, no right-click",
                              page.evaluate("lab.clicks") - before == 2 and page.evaluate("lab.rclicks") == rbefore))
                # in the world a double-tap is still a right-click (talk, loot, open)
                page.wait_for_timeout(500)
                wx, wy = vp["width"] * 0.62, vp["height"] * 0.3
                rp = page.evaluate("lab.rpresses || 0")
                page.touchscreen.tap(wx, wy)
                page.wait_for_timeout(150)
                page.touchscreen.tap(wx, wy)
                page.wait_for_timeout(slow_ms(extra, 900))
                cases.append(("a double-tap in the world is a right-click",
                              page.evaluate("lab.rpresses || 0") - rp == 1))
            cdp.detach()
            info = page.evaluate("({ ignored: lab.ignored, debug: document.querySelector('#ow-touch .tdebug')?.textContent || '', "
                                 "moves: lab.events.filter(e => e.t === 'moved').length })")
            for label, ok in cases:
                failed += 0 if ok else 1
                print(f"{'PASS' if ok else 'FAIL'}  {name}: {label}")
            if errors:
                failed += 1
                print(f"FAIL  {name}: page errors: {errors[:2]}")
            if any(not ok for _, ok in cases) or "-v" in sys.argv:
                print("      presses ignored:", info["ignored"], " cursor moves the game saw:", info["moves"])
                print("      " + info["debug"].replace("\n", "\n      "))
            if show:
                os.makedirs(os.path.join(ROOT, "_local", "touchlab"), exist_ok=True)
                page.screenshot(path=os.path.join(ROOT, "_local", "touchlab", name.split(" ")[0] + ".png"))
            ctx.close()
        browser.close()
    srv.shutdown()
    print("all passed" if not failed else f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
