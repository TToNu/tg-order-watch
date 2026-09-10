"""Batch: harvest cookies + relist for ALL pending items.
Run once, processes each item sequentially."""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent

sys.path.insert(0, str(HERE))
from relist_direct import curl_json, API

def get_pending():
    st = json.loads((BASE / ".flip_state.json").read_text(encoding="utf-8"))
    return st.get("pending_relists", [])

def remove_pending(iid):
    st = json.loads((BASE / ".flip_state.json").read_text(encoding="utf-8"))
    st["pending_relists"] = [r for r in st.get("pending_relists", [])
                              if r["item_id"] != iid]
    (BASE / ".flip_state.json").write_text(
        json.dumps(st, ensure_ascii=False), encoding="utf-8")

def harvest(iid):
    """Run the cookie harvester, return True if cookies file exists."""
    result = subprocess.run(
        [sys.executable, str(HERE / "epic_login_browser.py"), str(iid)],
        capture_output=True, text=True, timeout=300,
        cwd=str(HERE))
    return (HERE / f"epic_cookies_{iid}.json").exists()

def relist(iid, game, price):
    """Relist with harvested cookies."""
    cookies_file = HERE / f"epic_cookies_{iid}.json"
    cookies = cookies_file.read_text(encoding="utf-8").strip() \
        if cookies_file.exists() else ""
    item = curl_json("GET", f"{API}/{iid}").get("item", {})
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    body = {
        "title": game,
        "price": max(10, price + 10),  # +10₽ margin
        "category_id": 12, "currency": "rub",
        "item_origin": "resale", "resell_item_id": iid,
        "allow_ask_discount": True,
        "extra": {"cookies": cookies, "close_item": False},
    }
    if login.get("login"):
        body["login_password"] = f"{login['login']}:{login['password']}"
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email['login']}:{email['password']}"
        body["email_type"] = "native"
    res = curl_json("POST", f"{API}/item/fast-sell", body)
    return res.get("itemLink", ""), res.get("errors", [])

def main():
    pending = get_pending()
    print(f"BATCH: {len(pending)} items to process", flush=True)
    success = 0
    for row in pending:
        iid = row["item_id"]
        game = row.get("game", "Epic Games")
        price = row.get("price", 20)
        print(f"\n[{iid}] {game} (bought {price}₽)", flush=True)

        # Step 1: harvest cookies
        print(f"  harvesting...", flush=True)
        ok = harvest(iid)
        if not ok:
            print(f"  harvest FAILED, skipping", flush=True)
            continue

        # Step 2: relist
        print(f"  relisting...", flush=True)
        try:
            link, errors = relist(iid, game, price)
            if link:
                print(f"  ✅ LISTED: {link}", flush=True)
                remove_pending(iid)
                success += 1
            else:
                print(f"  ❌ {errors[:1]}", flush=True)
        except Exception as e:
            print(f"  ❌ {e}", flush=True)

        # Brief pause between accounts
        time.sleep(3)

    print(f"\nDONE: {success}/{len(pending)} listed", flush=True)

if __name__ == "__main__":
    main()
