"""lzt.market API client through the static India SOCKS5 proxy.

Handles the DDoS-Guard "_dfjs" JS challenge by executing their own script
in a sandboxed JS engine (py_mini_racer) and replaying the resulting cookie.

Usage:
    python lzt.py me                       # account info + balance
    python lzt.py search <game> [pmin pmax] [limit]
    python lzt.py item <item_id>

Credentials: lzt_token.json {"token": "..."} and proxy from ../config.json.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
TOKEN_FILE = Path(__file__).with_name("lzt_token.json")
DFJS_CACHE = Path(__file__).with_name("dfjs_b.js")

API = "https://api.lzt.market"


def make_session() -> requests.Session:
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    p = cfg["proxy"]
    s = requests.Session()
    s.proxies = {
        "http": f"socks5h://{p['user']}:{p['pass']}@{p['host']}:{p['port']}",
        "https": f"socks5h://{p['user']}:{p['pass']}@{p['host']}:{p['port']}",
    }
    s.headers["Authorization"] = "Bearer " + json.loads(
        TOKEN_FILE.read_text(encoding="utf-8"))["token"]
    s.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/149.0.0.0 Safari/537.36")
    return s


def solve_challenge(html: str, s: requests.Session) -> None:
    """Run the DDoS-Guard JS in a sandbox and store its cookie."""
    m = re.search(r'main\("([0-9a-f]{32})",\s*"([0-9a-f]{32})",\s*"([0-9a-f]{32})"\)', html)
    if not m:
        raise RuntimeError("no challenge params in page")
    a, b, c = m.groups()

    if DFJS_CACHE.exists():
        js = DFJS_CACHE.read_text(encoding="utf-8")
    else:
        r = s.get("https://lzt.market/_dfjs/b.js", timeout=30)
        js = r.text
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
        "var navigator={userAgent:'Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',"
        "platform:'Win32',language:'en-US',languages:['en-US','en'],"
        "cookieEnabled:true,hardwareConcurrency:8};"
        "var screen={width:1920,height:1080,colorDepth:24};"
        "var window={screen:screen,navigator:navigator,location:location};"
        "var fetch=function(url,opts){return Promise.resolve({ok:true,"
        "status:200,text:function(){return Promise.resolve('');},"
        "json:function(){return Promise.resolve({});}});};"
    )
    ctx.eval(js)
    ctx.eval(f'main("{a}", "{b}", "{c}")')
    raw = ctx.eval("JSON.stringify(__cookies)")
    for pair in json.loads(raw):
        name, _, value = pair.partition("=")
        s.cookies.set(name.split(";")[0].strip(), value.split(";")[0])
        print(f"[challenge] cookie {name.split(';')[0]} set")


def api_get(s: requests.Session, path: str, **params) -> dict:
    r = s.get(API + path, params=params or None, timeout=40)
    if "_dfjs" in r.text and "<html" in r.text[:200]:
        solve_challenge(r.text, s)
        r = s.get(API + path, params=params or None, timeout=40)
    if r.status_code == 403:
        sys.exit(f"403: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "me"
    s = make_session()

    if cmd == "me":
        for path in ("/users/me", "/market/me", "/v1/me"):
            try:
                me = api_get(s, path)
            except Exception as e:  # noqa: BLE001
                print(f"{path}: {e}")
                continue
            if isinstance(me, dict) and (me.get("username") or me.get("balance") is not None):
                print(f"[from {path}]")
                print(json.dumps(me, ensure_ascii=False, indent=1)[:2000])
                return
        sys.exit("no working /me path")

    if cmd == "search":
        game = sys.argv[2]
        pmin = sys.argv[3] if len(sys.argv) > 3 else None
        pmax = sys.argv[4] if len(sys.argv) > 4 else None
        limit = int(sys.argv[5]) if len(sys.argv) > 5 else 10
        res = api_get(s, "/items", game=game,
                      **({"pmin": pmin} if pmin else {}),
                      **({"pmax": pmax} if pmax else {}),
                      order_by="price_to_up", limit=limit)
        items = res.get("items", [])
        print(f"total: {res.get('total')}")
        for it in items[:limit]:
            print(f"{it.get('item_id')}  {it.get('price')}₽  "
                  f"{(it.get('title') or '')[:60]}  "
                  f"seller={it.get('seller', {}).get('username')}")
        return

    if cmd == "item":
        data = api_get(s, f"/item/{sys.argv[2]}")
        print(json.dumps(data, ensure_ascii=False, indent=1)[:4000])
        return

    sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
