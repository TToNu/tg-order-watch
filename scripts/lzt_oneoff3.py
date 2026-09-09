"""Relist the bought item using freshly exported Epic cookies."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call
from lzt_flip_loop import load_state, log, resale_stats, save_state

IID = 258545447
PRICE = 39.0
GAME = "Dead by Daylight"


def main() -> None:
    item = api_call("GET", f"/{IID}").get("item")
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    cookies = Path(__file__).with_name("epic_cookies.json").read_text(
        encoding="utf-8").strip()
    floor, target, med = resale_stats(GAME)
    body = {
        "title": GAME,
        "title_en": GAME,
        "price": target,
        "category_id": 12,
        "currency": "rub",
        "item_origin": "resale",
        "resell_item_id": IID,
        "allow_ask_discount": True,
        "description": f"{GAME} (Epic Games). Полный доступ, "
                       f"почта в комплекте.",
        "extra": {"cookies": cookies, "close_item": False},
    }
    if login.get("login"):
        body["login_password"] = f"{login['login']}:{login['password']}"
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email['login']}:{email['password']}"
        body["email_type"] = "native"
    res = api_call("POST", "/item/fast-sell", data=body)
    link = res.get("itemLink") or f"https://lzt.market/" \
           f"{res.get('item', {}).get('item_id')}/"
    print(f"RELISTED: {link} за {target}₽ (floor {floor})")

    st = load_state()
    st["spent"] += PRICE
    st["my_listings"].append({
        "item_id": IID, "bought": PRICE, "game": GAME, "link": link,
        "ts": datetime.now().isoformat(timespec="seconds")})
    st["pending_relists"] = [r for r in st["pending_relists"]
                             if r["item_id"] != IID]
    save_state(st)


if __name__ == "__main__":
    main()
