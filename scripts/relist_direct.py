"""Relist items with cookies — direct connection (no proxy)."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = json.loads((HERE / "lzt_token.json").read_text(encoding="utf-8"))["token"]
API = "https://api.lzt.market"


def curl_json(method: str, url: str, data: dict | None = None) -> dict:
    cmd = ["curl", "-s", "-m", "60", "-X", method, url,
           "-H", f"Authorization: Bearer {TOKEN}",
           "-H", "Content-Type: application/json"]
    if data:
        cmd += ["-d", json.dumps(data)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    return json.loads(out.stdout)


def main() -> None:
    iid = int(sys.argv[1]) if len(sys.argv) > 1 else 258553032
    price = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    title = sys.argv[3] if len(sys.argv) > 3 else "EA SPORTS FC 26"

    # Get item data
    item = curl_json("GET", f"{API}/{iid}").get("item", {})
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}

    # Load cookies
    cookies_file = HERE / f"epic_cookies_{iid}.json"
    cookies = cookies_file.read_text(encoding="utf-8").strip() \
        if cookies_file.exists() else ""

    body = {
        "title": title,
        "price": price,
        "category_id": 12,
        "currency": "rub",
        "item_origin": "resale",
        "resell_item_id": iid,
        "allow_ask_discount": True,
        "description": f"{title} на Epic Games. Полный доступ, почта.",
    }
    if login.get("login"):
        body["login_password"] = f"{login['login']}:{login['password']}"
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email['login']}:{email['password']}"
        body["email_type"] = "native"
    if cookies:
        body["extra"] = {"cookies": cookies, "close_item": False}

    res = curl_json("POST", f"{API}/item/fast-sell", body)
    if "itemLink" in res:
        print(f"RELISTED: {res['itemLink']}")
    else:
        print(f"ERROR: {json.dumps(res, ensure_ascii=False)[:300]}")


if __name__ == "__main__":
    main()
