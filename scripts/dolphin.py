"""Dolphin Anty local API helper + background CDP driver.

All browser work happens through the Chrome DevTools Protocol — the profile
window is not focused, not raised, the user keeps working undisturbed.

Setup: put the local API token into dolphin_token.json next to this file:
    {"token": "<session token from Dolphin Settings -> API>"}

Usage:
    python dolphin.py profiles
    python dolphin.py start <profile_id>
    python dolphin.py stop <profile_id>
    python dolphin.py tabs <profile_id>
    python dolphin.py open <profile_id> <url>
    python dolphin.py eval <profile_id> "<js expression>"
    python dolphin.py shot <profile_id> <out.png>
    python dolphin.py setproxy <profile_id> socks5://user:pass@host:port
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import websocket

BASE = "http://127.0.0.1:3001"
TOKEN_FILE = Path(__file__).with_name("dolphin_token.json")


def token() -> str:
    if not TOKEN_FILE.exists():
        sys.exit("no dolphin_token.json — put {\"token\": \"...\"} next to dolphin.py")
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["token"]


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"session-token": token(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"API {method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def start_profile(profile_id: str) -> dict:
    res = api("POST", f"/browser_profiles/{profile_id}/start", {})
    if not res.get("success", True):
        sys.exit(f"start failed: {res}")
    return res.get("data", res)


def cdp_ws(profile_id: str, start_if_needed: bool = True) -> str:
    """Return the browser-level CDP websocket URL for a running profile."""
    status = api("GET", f"/browser_profiles/{profile_id}/status")
    ws = (status.get("data") or {}).get("ws") if status.get("success") else None
    if not ws:
        if not start_if_needed:
            sys.exit(f"profile {profile_id} is not running")
        start_profile(profile_id)
        time.sleep(2)
        status = api("GET", f"/browser_profiles/{profile_id}/status")
        ws = (status.get("data") or {}).get("ws")
    if not ws:
        sys.exit("no ws endpoint in status response: " + json.dumps(status)[:300])
    return ws


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.msg_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.msg_id += 1
        self.ws.send(json.dumps({"id": self.msg_id, "method": method,
                                 "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method}: {msg['error']}")
                return msg.get("result", {})

    def close(self):
        self.ws.close()


def targets(ws_url: str) -> list[dict]:
    """Page targets via the HTTP endpoint derived from the ws url."""
    http = ws_url.split("/devtools/")[0]
    with urllib.request.urlopen(http + "/json", timeout=10) as r:
        return json.loads(r.read().decode())


def with_page_cdp(profile_id: str):
    """Connect to the first non-devtools page target and yield the CDP."""
    ws = cdp_ws(profile_id)
    for t in targets(ws):
        if t.get("type") == "page" and t.get("url", "") and "devtools" not in t.get("url", ""):
            cdp = CDP(t["webSocketDebuggerUrl"])
            try:
                yield cdp
            finally:
                cdp.close()
            return
    sys.exit("no page target found in profile")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "profiles":
        res = api("GET", "/browser_profiles?page=1&limit=50")
        for p in res.get("data", {}).get("browser_profiles", []):
            proxy = p.get("proxy") or {}
            print(f"{p['id']}  {p.get('name','?')!r}  "
                  f"proxy={proxy.get('type','')}/{proxy.get('host','')}")
        return

    if cmd == "start":
        print(json.dumps(start_profile(sys.argv[2]), ensure_ascii=False))
        return
    if cmd == "stop":
        print(json.dumps(api("POST", f"/browser_profiles/{sys.argv[2]}/stop", {}),
                         ensure_ascii=False))
        return
    if cmd == "setproxy":
        pid, proxy_str = sys.argv[2], sys.argv[3]
        # "socks5://user:pass@host:port" -> structured body
        scheme, rest = proxy_str.split("://", 1)
        creds, _, hostport = rest.rpartition("@")
        host, port = hostport.rsplit(":", 1)
        user, _, pwd = creds.partition(":")
        body = {"proxy": {"type": scheme, "host": host, "port": int(port),
                          "user": user or None, "pass": pwd or None}}
        print(json.dumps(api("PUT", f"/browser_profiles/{pid}", body),
                         ensure_ascii=False))
        return

    if cmd == "tabs":
        for t in targets(cdp_ws(sys.argv[2])):
            if t.get("type") == "page":
                print(f"{t['id'][:12]}  {t.get('title','')[:60]}  {t.get('url','')[:80]}")
        return

    if cmd == "open":
        pid, url = sys.argv[2], sys.argv[3]
        for cdp in with_page_cdp(pid):
            print(json.dumps(cdp.call("Page.navigate", {"url": url})))
        return

    if cmd == "eval":
        pid, expr = sys.argv[2], sys.argv[3]
        for cdp in with_page_cdp(pid):
            r = cdp.call("Runtime.evaluate", {"expression": expr,
                                              "returnByValue": True})
            print(json.dumps(r.get("result", {}).get("value"), ensure_ascii=False))
        return

    if cmd == "shot":
        pid, out = sys.argv[2], sys.argv[3]
        for cdp in with_page_cdp(pid):
            r = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 70})
            Path(out).write_bytes(base64.b64decode(r["data"]))
            print(f"saved {out}")
        return

    sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
