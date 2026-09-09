"""Log into epicgames.com in a real browser (CDP-driven Chrome) and export
session cookies for lzt.market fast-sell.

Pure-HTTP login is captcha-blocked; a genuine Chromium passes Turnstile.

Usage: python epic_login_browser.py
Reads credentials from bought_item.json; writes epic_cookies.txt.
"""

import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
PROFILE = str(Path(__file__).with_name(".chrome_epic_profile"))
HERE = Path(__file__).resolve().parent


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
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10) as r:
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


def login_steps(cdp, email: str, password: str) -> None:
    js = SET_INPUTS.replace("EMAIL", json.dumps(email)) \
                   .replace("PASSWORD", json.dumps(password))
    for step in range(5):
        result = str(cdp.eval_js(js, await_promise=True))
        print(f"step {step}: {result}")
        time.sleep(4)
        url = str(cdp.eval_js("location.href"))
        print("  url:", url)
        if "/id/login" not in url:
            print("  left the login page — success")
            return
        err = str(cdp.eval_js(
            "document.body.innerText.match(/неверный|incorrect|ошибк|error|"
            "капч|captcha|верифик|verif/i)"))
        if "None" not in err:
            print("  page mentions:", err)


def main() -> None:
    item = json.loads((HERE / "bought_item.json").read_text(encoding="utf-8"))
    raw = (item.get("loginData") or {}).get("raw") or ""
    email, _, password = raw.partition(":")
    if not password:
        raise SystemExit("no creds")

    proc = subprocess.Popen([
        CHROME, f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}", "--no-first-run",
        "--window-size=1100,800",
        "https://www.epicgames.com/id/login"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

    time.sleep(8)
    cdp = CDP(page_ws())
    try:
        # wait for the login form
        status = ""
        for _ in range(20):
            status = str(cdp.eval_js(
                "!!document.querySelector('input[type=password]')"))
            if status == "True":
                break
            time.sleep(1)
        print("form ready:", status)

        js = ""
        login_steps(cdp, email, password)

        time.sleep(4)
        text = str(cdp.eval_js("document.body.innerText.slice(0, 400)"))
        print("--- page text ---")
        print(text)
        shot = cdp.call("Page.captureScreenshot", {"format": "jpeg",
                                                   "quality": 70})
        (HERE / "epic_login_shot.jpg").write_bytes(
            base64.b64decode(shot["data"]))
        print("screenshot -> epic_login_shot.jpg")

        # wait for session cookies
        cookies = {}
        raw_cookies = []
        for _ in range(15):
            time.sleep(2)
            res = cdp.call("Storage.getCookies")
            raw_cookies = res.get("cookies", [])
            cookies = {c["name"]: c["value"] for c in raw_cookies}
            names = [c["name"] for c in res.get("cookies", [])]
            print("cookies:", names)
            if "EPIC_SSO" in cookies or "EPIC_BEARER_TOKEN" in cookies \
                    or "sid" in cookies:
                break
            url = str(cdp.eval_js("location.href"))
            print("url:", url)

        header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        (HERE / "epic_cookies.txt").write_text(header, encoding="utf-8")
        # lzt.market expects the Cookie-Editor JSON export format
        json_export = [{"name": c["name"], "value": c["value"],
                        "domain": c.get("domain", ""),
                        "path": c.get("path", "/")}
                       for c in raw_cookies]
        (HERE / "epic_cookies.json").write_text(
            json.dumps(json_export, ensure_ascii=False), encoding="utf-8")
        print(f"saved {len(cookies)} cookies -> epic_cookies.txt/.json")
    finally:
        cdp.close()
        time.sleep(2)
        proc.terminate()


if __name__ == "__main__":
    main()
