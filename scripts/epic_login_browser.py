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
import os
# Default proxy — can be overridden per-run via EPIC_PROXY env var.
# Each ClipProxy port = different exit IP, giving every account a fresh
# identity (no accumulated security flags from previous attempts).
DEFAULT_PROXY = "http://192.168.56.1:40000"
PROXY_UPSTREAM = os.environ.get("EPIC_PROXY", DEFAULT_PROXY).strip()
# Epic throws a hard security checkpoint at datacenter IPs — direct home
# connection passes Turnstile silently. Set EPIC_NOPROXY=1 to skip the proxy.
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
    raw = ""
    if item_id:
        item = api_call("GET", f"/{item_id}").get("item")
        raw = (item.get("loginData") or {}).get("raw") or ""
        if not raw:
            # discount auto-buys hide loginData even from the buyer; the
            # paid-orders export holds email creds (email pass == account
            # pass for these autoregs)
            cache = HERE / "item_emails.json"
            if cache.exists():
                creds = json.loads(
                    cache.read_text(encoding="utf-8")).get(str(item_id), "")
                if creds:
                    raw = creds
    else:
        item = json.loads((HERE / "bought_item.json")
                          .read_text(encoding="utf-8"))
        raw = (item.get("loginData") or {}).get("raw") or ""
    email, _, password = raw.partition(":")
    return email, password, item_id


def login_steps(cdp, email: str, password: str,
                email_pass: str = "") -> bool:
    """Login + handle 2FA via IMAP code retrieval."""
    js = SET_INPUTS.replace("EMAIL", json.dumps(email)) \
                   .replace("PASSWORD", json.dumps(password))
    for step in range(15):
        body = str(cdp.eval_js("document.body.innerText.slice(0,300)"))
        url = str(cdp.eval_js("location.href"))

        # 2FA page: check both /mfa/ and /mfa? (no trailing slash)
        if "/mfa" in url or "двухфакторн" in body.lower() \
                or "2fa" in body.lower():
            print(f"  [2FA] detected at {url}", flush=True)
            if email_pass:
                ok = handle_2fa_flow(cdp, email, email_pass)
                if ok:
                    continue  # re-check URL after 2FA
            # Fallback: try to skip
            skip = str(cdp.eval_js(
                "(() => { const b = [...document.querySelectorAll("
                "'button,a')].find(x => /позже|пропустить|skip|later|"
                "не сейчас/i.test(x.innerText||''));"
                "if (b) { b.click(); return 'skipped'; }"
                "return 'no-skip'; })()"))
            print(f"  [2FA] skip attempt: {skip}", flush=True)
            if "skipped" in skip:
                time.sleep(3)
                continue
            time.sleep(4)
            continue

        result = str(cdp.eval_js(js, await_promise=True))
        print(f"  step {step}: {result} | {url}", flush=True)
        if "/id/login" not in url and "/mfa/" not in url:
            return True
        if "no-inputs" in result:
            print("  body:", body.replace("\n", " ")[:200])
        time.sleep(4)
    return False


def unlink_social_club(cdp) -> tuple[bool, str]:
    """Navigate to Epic connections and unlink Rockstar Social Club.
    Returns (was_unlinked, status). Increases GTA V resale value by ~50₽."""
    print("  [SC] checking connections...", flush=True)
    cdp.call("Page.navigate",
             {"url": "https://www.epicgames.com/account/connections"})
    time.sleep(8)
    body = str(cdp.eval_js("document.body.innerText"))

    if "rockstar" not in body.lower() and "social club" not in body.lower():
        return False, "not-linked"

    # Find Disconnect button in the Rockstar section
    result = str(cdp.eval_js("""
        (() => {
            const sections = [...document.querySelectorAll(
                'div,section,article,li')];
            const rs = sections.find(el => {
                const t = (el.innerText || '').toLowerCase();
                return (t.includes('rockstar') || t.includes('social club'))
                    && t.includes('disconnect');
            });
            if (!rs) return 'no-disconnect-visible';
            const btn = [...rs.querySelectorAll('button,a')].find(b =>
                /disconnect|отключить/i.test(b.innerText || ''));
            if (btn) { btn.click(); return 'clicked'; }
            return 'no-btn';
        })()"""))
    print(f"  [SC] {result}", flush=True)

    if "clicked" not in result:
        return False, result

    # Handle confirmation dialog
    time.sleep(3)
    confirm = str(cdp.eval_js("""
        (() => {
            const btns = [...document.querySelectorAll(
                'button,[role=button],a.btn')];
            const yes = btns.find(b =>
                /yes|да|confirm|подтвердить|unlink|отвязать|remove/i
                .test(b.innerText || ''));
            if (yes) { yes.click(); return 'confirmed'; }
            return 'no-confirm-needed';
        })()"""))
    print(f"  [SC] confirm: {confirm}", flush=True)
    time.sleep(3)
    return True, f"unlinked ({result}, {confirm})"


def disable_2fa(cdp) -> bool:
    """Navigate to account security settings and disable 2FA if enabled."""
    print("  [2FA-off] navigating to security settings...", flush=True)
    cdp.call("Page.navigate",
             {"url": "https://www.epicgames.com/account/security"})
    time.sleep(5)
    body = str(cdp.eval_js("document.body.innerText.slice(0,500)"))
    print(f"  [2FA-off] page: {body[:200]}", flush=True)

    # Look for 2FA toggle/disable buttons
    result = str(cdp.eval_js("""
        (() => {
            const btns = [...document.querySelectorAll('button,a,[role=switch]')];
            // Find disable button for email 2FA
            const disable = btns.find(b =>
                /отключить|disable|выключить|deactivate/i
                .test(b.innerText || b.getAttribute('aria-label') || ''));
            if (disable) {
                disable.click();
                return 'clicked:' + (disable.innerText ||
                    disable.getAttribute('aria-label')).slice(0,30);
            }
            // Check if 2FA is already off
            const txt = document.body.innerText.toLowerCase();
            if (txt.includes('не включена') || txt.includes('not enabled') ||
                txt.includes('disabled')) {
                return 'already-off';
            }
            return 'no-button';
        })()"""))
    print(f"  [2FA-off] {result}", flush=True)
    return "off" in result or "already" in result


def handle_2fa_flow(cdp, email_addr: str, email_pass: str) -> bool:
    """Request 2FA code, fetch from IMAP, enter in browser."""
    # Mark ALL old emails as seen so IMAP only finds the fresh code
    try:
        from imap_clear import mark_all_seen
        old = mark_all_seen(email_addr, email_pass)
        print(f"  [2FA] marked {old} old emails as seen", flush=True)
    except Exception as e:
        print(f"  [2FA] clear failed: {e}", flush=True)

    print("  [2FA] requesting code...", flush=True)

    # Click send code button
    cdp.eval_js("""
        (() => { const b = [...document.querySelectorAll('button')]
            .find(x => /отправить|send|получить код/i.test(x.innerText||''));
            if (b) b.click(); })()""")
    time.sleep(5)

    # Fetch code from IMAP
    from imap_fetch import get_epic_code
    code = None
    for attempt in range(3):
        code = get_epic_code(email_addr, email_pass, wait_seconds=5)
        if code:
            break
        print(f"  [2FA] waiting for code (attempt {attempt+1})...", flush=True)
        time.sleep(8)

    if not code:
        # Check for manually provided code (EPIC_2FA_CODE env var)
        import os
        manual = os.environ.get("EPIC_2FA_CODE", "").strip()
        if manual:
            code = manual
            print(f"  [2FA] using manual code: {code}", flush=True)

    if not code:
        print("  [2FA] FAILED: no code in email or env", flush=True)
        return False

    print(f"  [2FA] got code: {code}", flush=True)

    # Enter code into 6 digit boxes — simple, no concatenation issues
    enter_js = "document.querySelectorAll('input').length"
    n_inputs = cdp.eval_js(enter_js)
    print(f"  [2FA] inputs on page: {n_inputs}", flush=True)

    if n_inputs and int(n_inputs) >= 6:
        # 6 individual digit boxes
        for idx in range(min(6, int(n_inputs))):
            digit = code[idx] if idx < len(code) else ""
            cdp.eval_js(
                f"(() => {{ const i = document.querySelectorAll('input')[{idx}];"
                f" const proto = HTMLInputElement.prototype;"
                f" Object.getOwnPropertyDescriptor(proto, 'value')"
                f".set.call(i, '{digit}');"
                f" i.dispatchEvent(new Event('input', {{bubbles: true}}));"
                f" i.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"
            )
            time.sleep(0.2)
        print(f"  [2FA] entered {code} digit-by-digit", flush=True)
    else:
        # Single text field
        cdp.eval_js(
            f"(() => {{ const i = document.querySelector('input');"
            f" if (!i) return 'no-input';"
            f" const proto = HTMLInputElement.prototype;"
            f" Object.getOwnPropertyDescriptor(proto, 'value')"
            f".set.call(i, '{code}');"
            f" i.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f" i.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"
        )
        print(f"  [2FA] entered {code} in single field", flush=True)

    # Submit
    time.sleep(1)
    cdp.eval_js("""
        (() => { const b = [...document.querySelectorAll('button')]
            .find(x => /продолжить|continue|далее|подтвердить|verify/i
            .test(x.innerText||''));
            if (b) b.click();
            else { const f = document.querySelector('form');
                   if (f) f.requestSubmit(); } })()""")
    print("  [2FA] submitted, waiting...", flush=True)
    time.sleep(5)
    return True


def run(headless: bool = True) -> tuple[list[dict], bool]:
    """Launch bridge+chrome, log in, return (cookies, ok)."""
    email, password, iid = get_creds(CURRENT_ITEM)
    if not password:
        raise SystemExit("no credentials")

    # Email password for 2FA code retrieval (may differ from account pass)
    email_pass = password  # default: same
    if iid:
        item = api_call("GET", f"/{iid}").get("item", {})
        el = item.get("emailLoginData") or {}
        if el.get("password"):
            email_pass = el["password"]
        else:
            # Try the paid-orders cache
            cache = HERE / "item_emails.json"
            if cache.exists():
                try:
                    creds = json.loads(
                        cache.read_text(encoding="utf-8")).get(str(iid), "")
                    if creds and ":" in creds:
                        email_pass = creds.split(":", 1)[1]
                except ValueError:
                    pass

    # Shared profile: Cloudflare/security checkpoint trust persists across
    # runs, so subsequent logins skip the interstitial page
    profile = str(HERE / ".chrome_epic_persist")
    Path(profile).mkdir(exist_ok=True)
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
        # CRITICAL: Clear stale Epic session cookies from the persistent
        # profile. Old cookies make the harvest "succeed" without actually
        # logging in, skipping the 2FA-disable and SC-unlink steps.
        cdp.call("Network.enable", {})
        cdp.call("Storage.clearCookies", {})
        print("  [session] cookies cleared for fresh login", flush=True)
        time.sleep(2)
        cdp.call("Page.navigate", {"url": "https://www.epicgames.com/id/login"})
        ok = False
        for _ in range(40):
            if str(cdp.eval_js(
                    "!!document.querySelector('input[type=password],"
                    "input[type=email]')")) == "True":
                break
            time.sleep(1)
        ok = login_steps(cdp, email, password, email_pass)

        # Post-login actions: disable 2FA + unlink SC.
        # Run even if login_steps returned False — persistent profile
        # cookies may still give us an active session.
        sc_unlinked = False
        if ok or "epicgames.com/account" in str(
                cdp.eval_js("location.href")):
            disable_2fa(cdp)
            sc_unlinked, sc_status = unlink_social_club(cdp)
            if sc_unlinked:
                print(f"  [SC] SUCCESS: {sc_status}", flush=True)
                (HERE / f"sc_free_{iid}.marker").write_text(
                    "unlinked", encoding="utf-8")

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
    except Exception as e:  # noqa: BLE001 - browser died mid-way
        print(f"  [harvest] {type(e).__name__}: {e}", flush=True)
        return [], False
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
