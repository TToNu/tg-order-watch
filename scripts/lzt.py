"""lzt.market API client through the static India SOCKS5 proxy (curl transport).

PySocks handshake stalls against this proxy, while curl works flawlessly, so
HTTP goes through curl. The DDoS-Guard "_dfjs" challenge (lzt.market pages) is
solved by executing their script in a sandboxed JS engine.

Usage:
    python lzt.py me
    python lzt.py search <game> [pmin pmax] [limit]
    python lzt.py item <item_id>
    python lzt.py raw <path> [k=v ...]

Credentials: lzt_token.json {"token": "..."}; proxy from ../config.json.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOKEN_FILE = Path(__file__).with_name("lzt_token.json")
DFJS_CACHE = Path(__file__).with_name("dfjs_b.js")
COOKIE_JAR = Path(__file__).with_name("lzt_cookies.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

API = "https://api.lzt.market"


def _proxy_args() -> list[str]:
    """Market transport proxy: dedicated lzt_proxy.json ({url}) if present,
    else the socks5 block from config.json."""
    dedicated = Path(__file__).with_name("lzt_proxy.json")
    if dedicated.exists():
        url = json.loads(dedicated.read_text(encoding="utf-8")).get("url", "")
        if url.startswith("http"):
            return ["-x", url]
        if url.startswith("socks5"):
            return ["--socks5-hostname", url[len("socks5://"):]]
        return []
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    p = cfg.get("proxy", {})
    if p.get("proto") != "socks5" and not p.get("host"):
        return []
    return ["--socks5-hostname", f"{p['user']}:{p['pass']}@{p['host']}:{p['port']}"]


_proxy_fails = 0
_proxy_skip_until = 0.0


def http(method: str, url: str, params: dict | None = None,
         data: str | None = None, proxy: bool = True) -> tuple[int, str]:
    """One HTTP round-trip via curl. Adaptive transport: the India SOCKS5
    stalls in waves; after 3 consecutive stalls it is skipped for 10 minutes
    so cycles stay fast on the direct fallback."""
    global _proxy_fails, _proxy_skip_until
    import time as _time
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]
    base = ["curl", "-s", "-m", "12", "-X", method,
            "-H", f"Authorization: Bearer {token}",
            "-H", f"User-Agent: {UA}",
            "-b", str(COOKIE_JAR), "-c", str(COOKIE_JAR),
            "-w", "\n__HTTP__%{http_code}"]
    if data is not None:
        base += ["-H", "Content-Type: application/json", "-d", data]

    def run(extra: list[str]) -> tuple[int, str]:
        out = subprocess.run(base + extra + [url], capture_output=True,
                             text=True, encoding="utf-8",
                             errors="replace").stdout
        if "__HTTP__" not in out:
            return 0, ""
        body, _, code = out.rpartition("__HTTP__")
        return int(code.strip()), body.strip()

    if proxy and _time.time() >= _proxy_skip_until:
        code, body = run(_proxy_args())
        if code > 0:
            _proxy_fails = 0
            return code, body
        _proxy_fails += 1
        print(f"[transport] proxy stalled ({_proxy_fails})", file=sys.stderr)
        if _proxy_fails >= 3:
            _proxy_skip_until = _time.time() + 600
            _proxy_fails = 0
            print("[transport] proxy disabled for 10 min, direct mode",
                  file=sys.stderr)
    for attempt in range(3):
        code, body = run([])
        if code > 0:
            return code, body
        import time
        time.sleep(3 + attempt * 3)
    return 0, ""


def solve_challenge(html: str) -> None:
    """Run the DDoS-Guard JS in a sandbox and store its cookie."""
    import re
    m = re.search(r'main\("([0-9a-f]{32})",\s*"([0-9a-f]{32})",\s*"([0-9a-f]{32})"\)', html)
    if not m:
        raise RuntimeError("no challenge params in page")
    a, b, c = m.groups()

    if DFJS_CACHE.exists():
        js = DFJS_CACHE.read_text(encoding="utf-8")
    else:
        code, text = http("GET", "https://lzt.market/_dfjs/b.js")
        js = text
        DFJS_CACHE.write_text(js, encoding="utf-8")

    from py_mini_racer import py_mini_racer
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(
        "var __cookies=[];"
        "var document={};"
        "Object.defineProperty(document,'cookie',{"
        "set:function(v){__cookies.push(v);},"
        "get:function(){return __cookies.join('; ');}});"
        "var location={reload:function(){},href:''};"
        "var navigator={userAgent:'" + UA + "',platform:'Win32',"
        "language:'en-US',languages:['en-US','en'],cookieEnabled:true,"
        "hardwareConcurrency:8};"
        "var screen={width:1920,height:1080,colorDepth:24};"
        "var window={screen:screen,navigator:navigator,location:location};"
        "var fetch=function(url,opts){return Promise.resolve({ok:true,"
        "status:200,text:function(){return Promise.resolve('');},"
        "json:function(){return Promise.resolve({});}});};"
    )
    ctx.eval(js)
    ctx.eval(f'main("{a}", "{b}", "{c}")')
    pairs = json.loads(ctx.eval("JSON.stringify(__cookies)"))
    with COOKIE_JAR.open("a", encoding="utf-8") as fh:
        for pair in pairs:
            kv = pair.split(";")[0]
            name, _, value = kv.partition("=")
            fh.write(f".lzt.market\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
            print(f"[challenge] cookie {name} set")


def api_call(method: str, path: str, params: dict | None = None,
             data: dict | None = None, raw: bool = False):
    code, body = http(method, API + path, params,
                      json.dumps(data) if data else None)
    if "_dfjs" in body and "<html" in body[:200]:
        solve_challenge(body)
        code, body = http(method, API + path, params,
                          json.dumps(data) if data else None)
    if code == 403:
        raise RuntimeError(f"403: {body[:300]}")
    if code >= 400:
        raise RuntimeError(f"HTTP {code}: {body[:300]}")
    if code == 0:
        raise RuntimeError("transport failed after retries")
    if raw:
        return body
    return json.loads(body)


def make_session():  # compat shim for older callers
    return None


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "me"

    if cmd == "me":
        res = api_call("GET", "/me")
        u = res.get("user", res)
        print(json.dumps({
            "username": u.get("username"),
            "user_id": u.get("user_id"),
            "balance": u.get("balance"),
            "balances": u.get("balances"),
            "hold": u.get("hold"),
            "active_items": u.get("active_items_count"),
            "sold_items": u.get("sold_items_count"),
            "rate_limit": res.get("system_info", {}).get("rate_limit"),
        }, ensure_ascii=False, indent=1))
        return

    if cmd == "search":
        game = sys.argv[2]
        pmin = sys.argv[3] if len(sys.argv) > 3 else None
        pmax = sys.argv[4] if len(sys.argv) > 4 else None
        limit = int(sys.argv[5]) if len(sys.argv) > 5 else 10
        params = {"order_by": "price_to_up"}
        if pmin:
            params["pmin"] = pmin
        if pmax:
            params["pmax"] = pmax
        res = api_call("GET", f"/{game}", params)
        items = res.get("items", [])
        print(f"total: {res.get('total')}")
        for it in items[:limit]:
            print(f"{it.get('item_id')}  {it.get('price')}₽  "
                  f"{(it.get('title') or '')[:60]}  "
                  f"seller={it.get('seller', {}).get('username')}")
        return

    if cmd == "item":
        data = api_call("GET", f"/{sys.argv[2]}")
        print(json.dumps(data, ensure_ascii=False, indent=1)[:5000])
        return

    if cmd == "raw":
        path = sys.argv[2]
        params = dict(a.split("=", 1) for a in sys.argv[3:])
        print(json.dumps(api_call("GET", path, params),
                         ensure_ascii=False, indent=1)[:8000])
        return

    sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
