"""Harvest epicgames.com session cookies for a market item — fully in the
background (headless Chrome) through the US Texas mobile SOCKS5 proxy.

The proxy is dynamic-IP per connection, which Epic trusts; Chromium cannot
authenticate SOCKS inline, so pproxy bridges a local unauthenticated port.

Usage:
    python epic_login_browser.py [item_id]

Credentials: item loginData via the market API (or bought_item.json when no
item_id given). Writes epic_cookies_<item_id>.json (Cookie-Editor format).
"""

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lzt import api_call

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
BRIDGE_PORT = 9340
PROXY_UPSTREAM = "http://10.6.7.1:40000"
# Epic throws a hard security checkpoint at datacenter IPs — direct home
# connection passes Turnstile silently. Set EPIC_NOPROXY=1 to skip the proxy.
import os
USE_PROXY = os.environ.get("EPIC_NOPROXY", "").strip() != "1" and bool(
    PROXY_UPSTREAM)


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.n = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method,
                                 "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval_js(self, expr: str, await_promise: bool = False) -> object:
        r = self.call("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": await_promise})
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:200])
        return r.get("result", {}).get("value")

    def close(self):
        self.ws.close()


def page_ws() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json",
                                timeout=10) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page" and "epicgames" in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page target")


SET_INPUTS = """
(async () => {
  const setVal = (el, v) => {
    const proto = el.tagName === 'INPUT' ? HTMLInputElement.prototype
                                         : HTMLTextAreaElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const email = document.querySelector('input[name=email], input[type=email], #email');
  const pass = document.querySelector('input[name=password], input[type=password], #password');
  if (!email && !pass) return 'no-inputs';
  if (email) setVal(email, EMAIL);
  if (pass) setVal(pass, PASSWORD);
  await new Promise(r => setTimeout(r, 400));
  const btns = [...document.querySelectorAll('button')];
  const btn = btns.find(b => /войти|sign in|log ?in|далее|next/i.test(b.innerText))
             || document.querySelector('button[type=submit]');
  if (!btn) {
    const f = document.querySelector('form');
    if (f) { f.requestSubmit(); return 'form-submitted'; }
    return 'no-button';
  }
  btn.click();
  return 'clicked:' + btn.innerText.trim().slice(0, 20);
})()
"""


def get_creds(item_id: int | None) -> tuple[str, str, int | None]:
    if item_id:
        item = api_call("GET", f"/{item_id}").get("item")
        raw = (item.get("loginData") or {}).get("raw") or ""
        email, _, password = raw.partition(":")
        return email, password, item_id
    item = json.loads((HERE / "bought_item.json").read_text(encoding="utf-8"))
    raw = (item.get("loginData") or {}).get("raw") or ""
    email, _, password = raw.partition(":")
    return email, password, None


def login_steps(cdp, email: str, password: str) -> bool:
    js = SET_INPUTS.replace("EMAIL", json.dumps(email)) \
                   .replace("PASSWORD", json.dumps(password))
    for step in range(6):
        result = str(cdp.eval_js(js, await_promise=True))
        url = str(cdp.eval_js("location.href"))
        print(f"  step {step}: {result} | {url}", flush=True)
        if "/id/login" not in url:
            return True
        if "no-inputs" in result:
            body = str(cdp.eval_js("document.body.innerText.slice(0,300)"))
            print("  body:", body.replace("\n", " ")[:200])
        time.sleep(4)
    return False


def run(headless: bool = True) -> tuple[list[dict], bool]:
    """Launch bridge+chrome, log in, return (cookies, ok)."""
    email, password, _ = get_creds(CURRENT_ITEM)
    if not password:
        raise SystemExit("no credentials")

    profile = tempfile.mkdtemp(prefix="epic_")
    flags = [CHROME, f"--remote-debugging-port={PORT}",
             "--remote-allow-origins=*",
             f"--user-data-dir={profile}", "--no-first-run",
             "--window-size=1100,800"]
    if USE_PROXY:
        if PROXY_UPSTREAM.startswith("http"):
            flags.append(f"--proxy-server={PROXY_UPSTREAM}")
        else:
            from http_socks_bridge import HttpToSocksBridge
            scheme, rest = PROXY_UPSTREAM.split("://", 1)
            creds, _, hostport = rest.rpartition("@")
            user, _, pwd = creds.partition(":")
            host, _, port = hostport.rpartition(":")
            bridge = HttpToSocksBridge(host, int(port), user, pwd, BRIDGE_PORT)
            bridge.start()
            time.sleep(1)
            flags.append(f"--proxy-server=http://127.0.0.1:{BRIDGE_PORT}")
    if headless:
        flags.append("--headless=new")
    else:
        flags.append("--start-minimized")
    flags.append("https://www.epicgames.com/id/login")
    proc = subprocess.Popen(flags, creationflags=subprocess.CREATE_NO_WINDOW)

    try:
        time.sleep(6)
        cdp = CDP(page_ws())
        cdp.call("Page.navigate", {"url": "https://www.epicgames.com/id/login"})
        ok = False
        for _ in range(40):
            if str(cdp.eval_js(
                    "!!document.querySelector('input[type=password],"
                    "input[type=email]')")) == "True":
                break
            time.sleep(1)
        ok = login_steps(cdp, email, password)
        raw = []
        for _ in range(10):
            time.sleep(2)
            res = cdp.call("Storage.getCookies")
            raw = res.get("cookies", [])
            names = {c["name"] for c in raw}
            if {"EPIC_SSO", "EPIC_BEARER_TOKEN"} & names:
                break
        cdp.close()
        return raw, ok
    finally:
        proc.terminate()


def main() -> None:
    global CURRENT_ITEM
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    CURRENT_ITEM = int(arg) if arg and arg.isdigit() else None
    email, _, iid = get_creds(CURRENT_ITEM)

    raw, ok = run(headless=True)
    names = {c["name"] for c in raw}
    if "EPIC_BEARER_TOKEN" not in names:
        print("[harvest] headless failed (no bearer), headed fallback",
              flush=True)
        raw, ok = run(headless=False)
        names = {c["name"] for c in raw}

    if "EPIC_BEARER_TOKEN" not in names:
        raise SystemExit(f"harvest FAILED for {email}: cookies {sorted(names)}")

    out = HERE / f"epic_cookies_{iid}.json" if iid else HERE / "epic_cookies.json"
    json_export = [{"name": c["name"], "value": c["value"],
                    "domain": c.get("domain", ""), "path": c.get("path", "/")}
                   for c in raw]
    out.write_text(json.dumps(json_export, ensure_ascii=False),
                   encoding="utf-8")
    print(f"HARVESTED {len(raw)} cookies for {email} -> {out.name}")


if __name__ == "__main__":
    main()
