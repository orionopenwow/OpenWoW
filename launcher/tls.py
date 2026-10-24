"""HTTPS trust for the launcher: the roots Windows has installed, plus Mozilla's (certifi).

Python checks a server's certificate against the roots Windows has installed, and Windows installs
roots only when something asks it to, on demand. Let's Encrypt's ECDSA certificates chain through ISRG
Root X2 (cross-signed by ISRG Root X1); on a PC without X2, Python took the cross-sign and
failed: "certificate has expired", no sign-in, no Online mode (2026-10-24), while browsers were fine.
certifi carries the current Mozilla root list (X1 and X2 included), so the launcher trusts what a
browser trusts whatever Windows happens to have. Windows' own roots stay trusted too (a company
proxy's root, say).

install() is called once at start-up: from then on urllib, http.client and anything that asks
ssl.create_default_context() for a client context (aiohttp, the P2P websocket) get both.
"""
import ssl

_create = ssl.create_default_context
_installed = False


def _bundle():
    try:
        import certifi
        return certifi.where()
    except Exception:          # not frozen in, or no data file: Windows' roots alone, as before
        return None


def context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    ctx = _create(purpose, cafile=cafile, capath=capath, cadata=cadata)
    if purpose == ssl.Purpose.SERVER_AUTH and not (cafile or capath or cadata):
        b = _bundle()
        if b:
            try:
                ctx.load_verify_locations(b)
            except (OSError, ssl.SSLError):
                pass
    return ctx


def install():
    global _installed
    if _installed:
        return
    _installed = True
    ssl.create_default_context = context
    ssl._create_default_https_context = context     # what urllib / http.client use with no context
