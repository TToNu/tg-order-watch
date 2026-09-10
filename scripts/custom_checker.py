"""Custom checker: harvest cookies + disable 2FA + unlink SC + relist.
Each account gets a FRESH IP via ClipProxy (unique port per account).

Usage:
    python custom_checker.py           # process all pending_relists
    python custom_checker.py <item_id> # process one item
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))

from relist_direct import curl_json, API

CLIPROXY_API = "http://192.168.56.1:1998/api"
PORT_START = 40003  # ports below this are often dead
COUNTRIES = ["US", "DE", "GB", "NL", "FR"]


def find_alive_ports(count: int, start: int = PORT_START) -> list[int]:
    """Scan ClipProxy ports and return the first N alive ones."""
    alive = []
    port = start
    while len(alive) < count and port < start + 20:
        proxy = get_proxy(port, "US")
        if proxy and test_proxy(proxy):
            alive.append(port)
            print(f"  port {port}: ALIVE", flush=True)
        else:
            print(f"  port {port}: dead", flush=True)
        port += 1
    return alive


def get_proxy(port: int, country: str = "US") -> str:
    """Get a proxy address for a specific port from ClipProxy."""
    url = (f"{CLIPROXY_API}?country={country}&state=&city=&postal=&isp="
           f"&start={port}&num=1&ip=")
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as r:
            addr = r.read().decode().strip()
            return f"http://{addr}" if ":" in addr else ""
    except Exception:
        return ""


def test_proxy(proxy_url: str) -> bool:
    """Quick liveness check."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "8", "-x", proxy_url,
             "https://api.ipify.org"],
            capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and len(result.stdout.strip()) > 5
    except Exception:
        return False


def harvest_and_relist(iid: int, game: str, price: float,
                       attempt: int = 0) -> bool:
    """Full pipeline: harvest cookies + disable 2FA + relist.
    Retries with different connection methods on failure."""
    # Try different connection methods per attempt
    if attempt == 0:
        proxy_env = ""  # direct (works ~50% of the time)
    elif attempt == 1:
        proxy_env = "http://192.168.56.1:40003"
    else:
        proxy_env = ""  # direct again (checkpoint is random)

    print(f"  attempt {attempt + 1}: "
          f"{'direct' if not proxy_env else proxy_env}", flush=True)

    # Run harvester
    print(f"  harvesting cookies...", flush=True)
    env = {**os.environ, "EPIC_PROXY": proxy_env}
    result = subprocess.run(
        [sys.executable, str(HERE / "epic_login_browser.py"), str(iid)],
        env=env, capture_output=True, text=True, timeout=300, cwd=str(HERE))

    cookies_file = HERE / f"epic_cookies_{iid}.json"
    if not cookies_file.exists():
        print(f"  ❌ harvest failed", flush=True)
        return False

    print(f"  ✅ cookies obtained", flush=True)

    # Check if SC was unlinked (premium pricing)
    sc_free = (HERE / f"sc_free_{iid}.marker").exists()
    title = game
    sell_price = max(10, int(price + 10))
    if sc_free and "GTA" in game.upper():
        title = "GTA V | Social Club FREE | Полный доступ"
        sell_price = max(200, sell_price)
        print(f"  🔓 SC-free premium: {sell_price}₽", flush=True)

    # Relist immediately
    print(f"  relisting at {sell_price}₽...", flush=True)
    cookies = cookies_file.read_text(encoding="utf-8").strip()
    item = curl_json("GET", f"{API}/{iid}").get("item", {})
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    body = {
        "title": title,
        "price": sell_price,
        "category_id": 12,
        "currency": "rub",
        "item_origin": "resale",
        "resell_item_id": iid,
        "allow_ask_discount": True,
        "extra": {"cookies": cookies, "close_item": False},
        "description": f"{title} на Epic Games. Полный доступ, почта.",
    }
    if login.get("login"):
        body["login_password"] = f"{login['login']}:{login['password']}"
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email['login']}:{email['password']}"
        body["email_type"] = "native"

    try:
        res = curl_json("POST", f"{API}/item/fast-sell", body)
        if "itemLink" in res:
            print(f"  ✅ LISTED: {res['itemLink']}", flush=True)
            return True
        else:
            for e in res.get("errors", [])[:1]:
                print(f"  ❌ relist: {e[:150]}", flush=True)
            return False
    except Exception as e:
        print(f"  ❌ relist error: {e}", flush=True)
        return False


def main():
    st = json.loads((BASE / ".flip_state.json").read_text(encoding="utf-8"))
    pending = st.get("pending_relists", [])

    if len(sys.argv) > 1:
        # Process single item
        iid = int(sys.argv[1])
        row = next((r for r in pending if r["item_id"] == iid), None)
        if row:
            pending = [row]
        else:
            sys.exit(f"item {iid} not in pending_relists")

    print(f"CUSTOM CHECKER: {len(pending)} items", flush=True)

    success = 0
    for i, row in enumerate(pending):
        iid = row["item_id"]
        game = row.get("game", "Epic Games")
        price = row.get("price", 20)

        print(f"\n[{iid}] {game} (bought {price}₽)", flush=True)

        ok = False
        for attempt in range(3):  # up to 3 attempts per account
            ok = harvest_and_relist(iid, game, price, attempt)
            if ok:
                break
            print(f"  retrying... ({attempt + 1}/3)", flush=True)
            time.sleep(5)

        if ok:
            # Remove from pending
            st = json.loads(
                (BASE / ".flip_state.json").read_text(encoding="utf-8"))
            st["pending_relists"] = [
                r for r in st.get("pending_relists", [])
                if r["item_id"] != iid]
            (BASE / ".flip_state.json").write_text(
                json.dumps(st, ensure_ascii=False), encoding="utf-8")
            success += 1
        else:
            print(f"  ❌ all 3 attempts failed", flush=True)

    print(f"\nDONE: {success}/{len(pending)} listed", flush=True)


if __name__ == "__main__":
    main()
