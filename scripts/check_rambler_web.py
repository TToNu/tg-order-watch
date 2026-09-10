"""Check rambler.ru webmail via CDP Chrome for Epic 2FA codes."""

import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
HERE = Path(__file__).resolve().parent

EMAIL = "osipov-ai4p6@rambler.ru"
PASSWORD = "ffeaCb9BYPVx"


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.n = 0
    def call(self, method, params=None):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method,
                                 "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})
    def eval_js(self, expr, await_promise=False):
        r = self.call("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": await_promise})
        return r.get("result", {}).get("value")
    def close(self):
        self.ws.close()


def page_ws():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json",
                                timeout=10) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page")


def main():
    profile = tempfile.mkdtemp(prefix="rambler_")
    proc = subprocess.Popen([
        CHROME, f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}", "--no-first-run",
        "--window-size=1100,800", "--start-minimized",
        "https://mail.rambler.ru/"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(8)
        cdp = CDP(page_ws())

        # Wait for login form
        for _ in range(20):
            ready = cdp.eval_js(
                "!!document.querySelector("
                "'input[name=login],input[type=email],#login')")
            if ready:
                break
            time.sleep(1)
        print("form ready:", ready)

        # Fill login
        cdp.eval_js("""
            (() => {
                const proto = HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(
                    proto, 'value').set;
                const login = document.querySelector(
                    'input[name=login],input[type=email],#login');
                if (login) {
                    setter.call(login, '""" + EMAIL + """');
                    login.dispatchEvent(new Event('input', {bubbles:true}));
                }
            })()""")
        time.sleep(0.5)

        # Click next if there's a multi-step login
        cdp.eval_js("""
            (() => {
                const btns = [...document.querySelectorAll('button')];
                const next = btns.find(b => /далее|войти|next|login/i
                    .test(b.innerText || ''));
                if (next) next.click();
            })()""")
        time.sleep(3)

        # Fill password
        cdp.eval_js("""
            (() => {
                const proto = HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(
                    proto, 'value').set;
                const pwd = document.querySelector(
                    'input[type=password]');
                if (pwd) {
                    setter.call(pwd, '""" + PASSWORD + """');
                    pwd.dispatchEvent(new Event('input', {bubbles:true}));
                }
            })()""")
        time.sleep(0.5)

        # Click login
        cdp.eval_js("""
            (() => {
                const btns = [...document.querySelectorAll('button');
                const submit = btns.find(b => /войти|вход|login|sign in/i
                    .test(b.innerText || ''))
                    || document.querySelector('button[type=submit]');
                if (submit) submit.click();
                else {
                    const form = document.querySelector('form');
                    if (form) form.requestSubmit();
                }
            })()""")
        print("submitted, waiting for inbox...")
        time.sleep(8)

        # Check if we're in the inbox
        url = cdp.eval_js("location.href")
        print("url:", url)

        # Look for Epic emails
        body = str(cdp.eval_js("document.body.innerText.slice(0, 3000)"))
        print("inbox preview:", body[:500])

        # Look for 6-digit codes in email list
        import re
        codes = re.findall(r"\b(\d{6})\b", body)
        if codes:
            print(f"\nFOUND CODES: {codes}")
        else:
            print("\nNo codes visible in inbox list")

        # Take screenshot for debugging
        shot = cdp.call("Page.captureScreenshot",
                        {"format": "jpeg", "quality": 70})
        (HERE / "rambler_inbox.jpg").write_bytes(
            __import__("base64").b64decode(shot["data"]))
        print("screenshot -> rambler_inbox.jpg")
        cdp.close()
    finally:
        time.sleep(2)
        proc.terminate()


if __name__ == "__main__":
    main()
