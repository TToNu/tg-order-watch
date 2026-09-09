"""Autonomous lzt.market Fortnite->DBD flipper (user-authorized).

Each cycle scans fresh cheap Fortnite lots; on a Dead by Daylight hit it:
  1. buys via fast-buy (price re-checked at buy time, retry_request loop),
  2. relists in Epic Games via fast-sell (resell_item_id, credentials and
     cookies passed through) at (market floor - 2 RUB),
  3. logs everything and reports to the user's Telegram Saved Messages.

Guardrails: MAX_BUY price, MIN_MARGIN, daily buy cap, balance floor.
All state in .flip_state.json; audit trail in flip_finds.log.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call
from lzt_flip import item_has_dbd, load_seen, save_seen

BASE = Path(__file__).resolve().parent.parent
FINDS_LOG = BASE / "flip_finds.log"
STATE = BASE / ".flip_state.json"
CMDS = BASE / "cmds.json"
CMDS_RESULT = BASE / "cmds.result.json"

RANGES = [("1", "25"), ("25", "60")]
PAGES_PER_RANGE = 3
CYCLE_SECONDS = 150
MAX_BUY_PRICE = 45          # never buy above this
MIN_MARGIN = 40             # resale floor minus buy price
DAILY_BUY_LIMIT = 5
BALANCE_FLOOR = 5           # keep at least this much on the balance
RESELL_CATEGORY = 12        # Epic Games


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"day": "", "bought": 0, "bought_ids": [],
            "my_listings": [], "spent": 0.0, "earned": 0.0}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def log(line: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"{stamp} {line}", flush=True)
    with FINDS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def notify(text: str) -> None:
    deadline = time.time() + 30
    while CMDS.exists() and time.time() < deadline:
        time.sleep(1)
    if CMDS.exists():
        log("[notify] cmds.json busy, alert skipped")
        return
    CMDS_RESULT.unlink(missing_ok=True)
    CMDS.write_text(json.dumps(
        {"send": [{"chat": "me", "reply_to": None, "text": text}]},
        ensure_ascii=False), encoding="utf-8")
    deadline = time.time() + 30
    while not CMDS_RESULT.exists() and time.time() < deadline:
        time.sleep(1)
    if CMDS_RESULT.exists():
        CMDS_RESULT.unlink(missing_ok=True)


def balance_rub() -> float:
    me = api_call("GET", "/me")
    u = me.get("user", me)
    for b in u.get("balances") or []:
        if b.get("type") == "account":
            return float(b.get("balance", 0))
    return float(u.get("balance", 0) or 0)


def resale_floor() -> float:
    res = api_call("GET", "/epicgames",
                   {"title": "dead by daylight", "order_by": "price_to_up"})
    items = res.get("items", [])
    if not items:
        return 88.0
    prices = [float(it.get("price", 88)) for it in items[:5]
              if it.get("item_state") == "active"]
    return min(prices) if prices else 88.0


def fast_buy(item_id: int, price: float) -> dict | None:
    for attempt in range(30):
        try:
            res = api_call("POST", f"/{item_id}/fast-buy",
                           data={"price": price})
        except RuntimeError as e:
            msg = str(e)
            if "retry_request" in msg:
                time.sleep(2)
                continue
            if "This item is sold" in msg or "404" in msg:
                log(f"[buy] {item_id} gone: {msg[:120]}")
                return None
            log(f"[buy] {item_id} error: {msg[:200]}")
            return None
        return res
    return None


def relist(bought: dict, buy_price: float) -> tuple[bool, str]:
    item = bought.get("item", bought)
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    cookies = (item.get("extra") or {}).get("cookies") or item.get("cookies")
    floor = resale_floor()
    sell_price = max(1.0, round(floor - 2))
    body = {
        "title": "Dead by Daylight",
        "title_en": "Dead by Daylight",
        "price": sell_price,
        "category_id": RESELL_CATEGORY,
        "currency": "rub",
        "item_origin": "resale",
        "resell_item_id": item.get("item_id"),
        "allow_ask_discount": True,
        "description": "Dead by Daylight (Epic Games). Полный доступ, "
                       "почта в комплекте.",
    }
    lp = f"{login.get('login')}:{login.get('password')}"
    if login.get("login") and login.get("password"):
        body["login_password"] = lp
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email.get('login')}:{email.get('password')}"
        body["email_type"] = "native"
    extra = {"close_item": False}
    if cookies:
        extra["cookies"] = cookies
    body["extra"] = extra
    try:
        res = api_call("POST", "/item/fast-sell", data=body)
    except RuntimeError as e:
        return False, str(e)[:300]
    link = res.get("itemLink") or f"https://lzt.market/{res.get('item', {}).get('item_id')}/"
    return True, f"{link} за {sell_price}₽ (floor {floor})"


def try_buy(it: dict, ev: str, st: dict) -> None:
    if st["bought"] >= DAILY_BUY_LIMIT:
        log("[guard] daily buy limit reached")
        return
    price = float(it.get("price", 999))
    if price > MAX_BUY_PRICE:
        log(f"[guard] {it['item_id']} price {price} > {MAX_BUY_PRICE}")
        return
    floor = resale_floor()
    if floor - price < MIN_MARGIN:
        log(f"[guard] {it['item_id']} margin {floor - price:.0f} < {MIN_MARGIN}")
        return
    bal = balance_rub()
    if bal - price < BALANCE_FLOOR:
        log(f"[guard] balance {bal} too low for price {price}")
        notify(f"⚠️ Баланс {bal}₽ — не хватает на лот {it['item_id']} "
               f"за {price}₽. Пополни баланс.")
        return

    log(f"[buy] ATTEMPT {it['item_id']} price={price} evidence={ev}")
    notify(f"🟡 Покупаю DBD-лот {it['item_id']} за {price}₽ "
           f"(перепродажа ~{floor:.0f}₽)")
    bought = fast_buy(it["item_id"], price)
    if not bought:
        notify(f"❌ Покупка {it['item_id']} не прошла (уплыл или ошибка)")
        return
    st["bought"] += 1
    st["bought_ids"].append(it["item_id"])
    save_state(st)
    log(f"[buy] OK {it['item_id']}")
    ok, info = relist(bought, price)
    if ok:
        log(f"[sell] OK {it['item_id']} -> {info}")
        st["spent"] += price
        st["my_listings"].append({
            "item_id": it["item_id"], "bought": price,
            "link": info.split(" ")[0] if info else "",
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        save_state(st)
        notify(f"✅ Флип: купил {it['item_id']} за {price}₽, "
               f"выставил {info}")
    else:
        log(f"[sell] FAIL {it['item_id']}: {info}")
        notify(f"🟠 Купил {it['item_id']} за {price}₽, но перевыкладка не "
               f"вышла: {info}. Нужно вручную.")


def check_my_listings(st: dict) -> None:
    """Track our relisted lots; on sale — log profit, sweep the money
    from the sale balance to the purchase balance (snowball mode)."""
    if not st.get("my_listings"):
        return
    still = []
    for row in st["my_listings"]:
        iid = row["item_id"]
        try:
            res = api_call("GET", f"/{iid}")
            item = res.get("item", res)
            state_now = item.get("item_state")
            buyer = item.get("buyer")
        except RuntimeError as e:
            if "404" in str(e):
                state_now, buyer = "gone", "unknown"
            else:
                still.append(row)
                continue
        if state_now in ("sold", "gone") or (buyer and buyer.get("user_id")
                                             != 10297413):
            sold_for = float(item.get("price") or 0) if isinstance(item, dict) else 0
            profit = sold_for - row["bought"] if sold_for else None
            st["earned"] += sold_for
            log(f"[sold] {iid}: bought {row['bought']}₽ -> sold "
                f"{sold_for or '?'}₽ (profit {profit if profit is not None else '?'})")
            notify(f"💰 Продано: {row.get('link') or iid} — "
                   f"куплено {row['bought']}₽, продано {sold_for or '?'}₽"
                   + (f", профит {profit:.0f}₽" if profit is not None else "")
                   + ". Реинвестирую.")
        else:
            still.append(row)
    if len(still) != len(st["my_listings"]):
        st["my_listings"] = still
        save_state(st)
        sweep_balances()


def sweep_balances() -> None:
    """Move sale proceeds to the purchase balance so the flipper can reinvest."""
    try:
        res = api_call("GET", "/payments/balance/list")
        balances = res if isinstance(res, list) else res.get("balances", res.get("data", []))
        src = next((b for b in balances if b.get("type") != "account"
                    and float(b.get("balance", 0) or 0) > 0), None)
        dst = next((b for b in balances if b.get("type") == "account"), None)
        if not src or not dst or float(src.get("balance", 0)) <= 0:
            return
        amount = float(src["balance"])
        body = {"balance_id": src.get("balance_id"),
                "exchange_balance_id": dst.get("balance_id"),
                "amount": amount}
        api_call("POST", "/payments/balance/exchange", data=body)
        log(f"[exchange] moved {amount}₽ {src.get('title')} -> "
            f"{dst.get('title')}")
    except Exception as e:  # noqa: BLE001
        log(f"[exchange] failed: {type(e).__name__}: {str(e)[:150]} — "
            f"переведи выручку на баланс покупок вручную")


def cycle(seen: set, st: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    if st["day"] != today:
        st["day"] = today
        st["bought"] = 0
        save_state(st)
    for pmin, pmax in RANGES:
        for page in range(1, PAGES_PER_RANGE + 1):
            res = api_call("GET", "/fortnite",
                           {"pmin": pmin, "pmax": pmax,
                            "order_by": "pdate_to_down",
                            "page": str(page)})
            items = res.get("items", [])
            for it in items:
                iid = it.get("item_id")
                if iid in seen or iid in st["bought_ids"]:
                    continue
                seen.add(iid)
                ev = item_has_dbd(it)
                if ev:
                    log(f"[find] https://lzt.market/{iid}/ "
                        f"{it.get('price')}₽ :: {ev}")
                    try_buy(it, ev, st)
            if not res.get("hasNextPage"):
                break


def main() -> None:
    print("autonomous flipper started: ranges "
          + ", ".join(f"{a}-{b}₽" for a, b in RANGES)
          + f" | max_buy {MAX_BUY_PRICE}₽ | margin ≥{MIN_MARGIN}₽ | "
            f"daily cap {DAILY_BUY_LIMIT}", flush=True)
    from lzt_prices import dump as price_dump
    seen = load_seen()
    st = load_state()
    n = 0
    while True:
        n += 1
        try:
            cycle(seen, st)
            check_my_listings(st)
            if n % 4 == 0:  # every ~10 minutes: price snapshot for stats
                try:
                    price_dump()
                except Exception as e:  # noqa: BLE001
                    print(f"[prices] {type(e).__name__}: {e}", flush=True)
            print(f"[cycle {n}] {datetime.now():%H:%M:%S} "
                  f"seen={len(seen)} bought_today={st['bought']} "
                  f"spent={st.get('spent', 0):.0f}₽ "
                  f"earned={st.get('earned', 0):.0f}₽ "
                  f"active_listings={len(st.get('my_listings', []))}",
                  flush=True)
        except Exception as e:  # noqa: BLE001 - never die
            print(f"[cycle {n}] error: {type(e).__name__}: {e}", flush=True)
        save_seen(seen)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
