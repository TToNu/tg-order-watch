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
from lzt_flip import (detect_game_fortnite, detect_game_epicgames,
                      load_seen, save_seen)

BASE = Path(__file__).resolve().parent.parent
FINDS_LOG = BASE / "flip_finds.log"
STATE = BASE / ".flip_state.json"
CMDS = BASE / "cmds.json"
CMDS_RESULT = BASE / "cmds.result.json"

RANGES = [("1", "25"), ("25", "60"), ("60", "75")]
PAGES_PER_RANGE = 2
CYCLE_SECONDS = 5              # turbo: 12 scans/min, well under rate limits
MAX_BUY_PRICE = 130         # absolute ceiling (balance-bound anyway)
MIN_MARGIN = 40             # listing target minus buy price
MARGIN_RATIO = 1.5          # sell price must be >= 1.5x the buy price
FEE_BUFFER = 5              # marketplace fee / repricing safety
BALANCE_FLOOR = 5           # keep at least this much on the balance
# Per-game caps: GTA V without Social Club access is a higher-risk resale
# (buyer disputes), so we limit exposure on the first purchases.
GAME_PRICE_CAPS = {
    "GTA V": 30,
}
RESELL_CATEGORY = 12        # Epic Games
PRICE_DUMP_EVERY = 120       # cycles between full price snapshots (~10 min)


def load_state() -> dict:
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        st = {}
    st.setdefault("day", "")
    st.setdefault("bought", 0)
    st.setdefault("bought_ids", [])
    st.setdefault("my_listings", [])
    st.setdefault("spent", 0.0)
    st.setdefault("earned", 0.0)
    st.setdefault("first_flip_reported", False)
    st.setdefault("pending_discounts", [])
    st.setdefault("pending_relists", [])
    st.setdefault("discounts_sent_hour", 0)
    st.setdefault("discounts_hour_ts", 0)
    return st


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def log(line: str) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"{stamp} {line}", flush=True)
    with FINDS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def notify(text: str, important: bool = True) -> None:
    """Telegram alert + local file backup (alerts.log)."""
    if important:
        alerts = BASE / "alerts.log"
        with alerts.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {text}\n")
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


_stats_cache: dict[str, tuple[float, float, float]] = {}
_stats_cache_ts: dict[str, float] = {}


def resale_stats(game: str = "dead by daylight") -> tuple[float, float, float]:
    """(floor, listing target, median) for a game in the Epic Games section.

    Deep markets (>=10 lots): undercut p25 but never dump below floor-2.
    Thin markets: price near the median — no point racing 2 competitors.
    Cached for 10 minutes per game.
    """
    now_ts = time.time()
    key = game.lower()
    if key in _stats_cache and now_ts - _stats_cache_ts[key] < 600:
        return _stats_cache[key]
    res = api_call("GET", "/epicgames",
                   {"title": game, "order_by": "price_to_up"})
    items = [it for it in res.get("items", [])
             if it.get("item_state") == "active"][:40]
    if not items:
        stats = (0.0, 0.0, 0.0)  # empty market -> try_buy's cap rejects
    else:
        prices = sorted(float(it["price"]) for it in items)
        floor = prices[0]
        p25 = prices[len(prices) // 4]
        med = prices[len(prices) // 2]
        if len(prices) >= 10:
            target = max(floor - 2, min(p25 - 2, floor + 20))
        else:
            target = max(floor - 2, round(med * 0.9))
        stats = (floor, round(target, 2), med)
    _stats_cache[key] = stats
    _stats_cache_ts[key] = now_ts
    return stats


_balance_id_cache: int | None = None


def purchase_balance_id() -> int | None:
    global _balance_id_cache
    if _balance_id_cache:
        return _balance_id_cache
    me = api_call("GET", "/me")
    u = me.get("user", me)
    for b in u.get("balances") or []:
        if b.get("type") == "account":
            _balance_id_cache = b.get("balance_id")
            return _balance_id_cache
    return None


def fast_buy(item_id: int, price: float) -> dict | None:
    """Buy with aggressive retry: handles retry_request AND the
    'another buyer's auto-purchase queue' race — snipe back in 1s."""
    for attempt in range(50):
        try:
            res = api_call("POST", f"/{item_id}/fast-buy",
                           data={"price": price,
                                 "balance_id": purchase_balance_id()})
        except RuntimeError as e:
            msg = str(e)
            if "retry_request" in msg:
                time.sleep(0.5)
                continue
            # "Аккаунт находится в очереди на автоматическую покупку"
            # -> another bot is buying; retry fast to snipe if they fail
            if "очеред" in msg or "queue" in msg.lower():
                time.sleep(1)
                continue
            if "This item is sold" in msg or "404" in msg:
                log(f"[buy] {item_id} gone: {msg[:120]}")
                return None
            log(f"[buy] {item_id} error: {msg[:200]}")
            return None
        return res
    return None


MAX_PENDING_DISCOUNTS = 8
DISCOUNTS_PER_HOUR = 10
SWEEP_EVERY = 60             # cycles between deep sweeps (~5 min at 5s)
SWEEP_PAGES = 25            # fortnite 1-100 RUB deep sweep depth


def hour_discount_budget(st: dict) -> bool:
    now_ts = time.time()
    if now_ts - st.get("discounts_hour_ts", 0) > 3600:
        st["discounts_hour_ts"] = now_ts
        st["discounts_sent_hour"] = 0
    return st["discounts_sent_hour"] < DISCOUNTS_PER_HOUR


def verify_games(item: dict, expected_game: str) -> tuple[str, bool, str]:
    """Post-purchase audit: read the REAL game list from the item's parsed
    eg_games/fortniteTransactions data and verify the expected game is
    actually present. Prevents hash-substring false positives.

    Returns (verified_game_name, matches_expected, detail_line).
    """
    from lzt_flip import GAME_TARGETS
    titles: set[str] = set()

    def extract(node) -> None:
        if isinstance(node, dict):
            t = node.get("title")
            if isinstance(t, str) and len(t) > 2 and t != "None":
                titles.add(t)
            for v in node.values():
                extract(v)
        elif isinstance(node, list):
            for v in node:
                extract(v)

    extract(item.get("eg_games") or {})
    for tr in item.get("fortniteTransactions") or []:
        t = tr.get("title")
        if isinstance(t, str) and t != "None":
            titles.add(t)

    if not titles:
        return expected_game, True, "no game data to verify (trusted)"

    # Which portfolio games are actually on this account?
    found: list[str] = []
    for game_name, rx in GAME_TARGETS:
        for title in titles:
            if rx.search(title):
                found.append(game_name)
                break

    detail = f"games found: {found or 'none'}; titles sample: {sorted(titles)[:6]}"

    if expected_game in found:
        return expected_game, True, f"VERIFIED {expected_game}: {detail}"

    if found:
        # relist under the most valuable game actually present
        for game_name, _ in GAME_TARGETS:
            if game_name in found:
                return game_name, False, \
                    f"MISMATCH: expected {expected_game}, got {game_name}: {detail}"

    # No portfolio games at all — describe honestly as a bundle
    return f"Epic Games | {len(titles)} игр", False, \
        f"MISMATCH: expected {expected_game}, no portfolio game: {detail}"


def max_payable(target: float, game: str = "") -> float:
    """Highest buy price that keeps both >= MIN_MARGIN profit and >= 1.5x ROI.
    Some games carry extra resale risk (GTA V SC disputes) — capped lower."""
    if target <= 0:
        return 0.0
    cap = GAME_PRICE_CAPS.get(game, MAX_BUY_PRICE)
    return round(min(target - MIN_MARGIN - FEE_BUFFER,
                     target / MARGIN_RATIO, cap), 2)


def try_discount(it: dict, st: dict, game: str, target: float) -> None:
    """Ask the seller for a price we can profit from; auto-buy on accept."""
    if not it.get("allow_ask_discount"):
        return
    if len(st["pending_discounts"]) >= MAX_PENDING_DISCOUNTS:
        return
    if any(p["item_id"] == it["item_id"] for p in st["pending_discounts"]):
        return
    if not hour_discount_budget(st):
        return
    offered = max(1.0, max_payable(target, game))
    if offered < it.get("price", 0) * 0.4:
        return  # unrealistic ask: seller would need a >60% cut
    try:
        api_call("POST", f"/{it['item_id']}/discount",
                 data={"discount_price": offered,
                       "message": f"Готов купить сразу за {offered:.0f}₽",
                       "auto_buy": True})
    except RuntimeError as e:
        log(f"[discount] {it['item_id']} failed: {str(e)[:120]}")
        return
    st["discounts_sent_hour"] += 1
    st["pending_discounts"].append({
        "item_id": it["item_id"], "game": game, "price": it.get("price"),
        "requested": offered,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    save_state(st)
    log(f"[discount] requested {it['item_id']} [{game}]: "
        f"{it.get('price')}₽ -> {offered:.0f}₽ (auto-buy on)")


def check_pending_discounts(st: dict) -> None:
    """auto_buy should purchase accepted items; detect ownership and relist."""
    still = []
    for row in st["pending_discounts"]:
        iid = row["item_id"]
        age_h = (datetime.now()
                 - datetime.fromisoformat(row["ts"])).total_seconds() / 3600
        try:
            res = api_call("GET", f"/{iid}")
        except RuntimeError as e:
            if "404" in str(e):
                continue  # gone: sold to someone else / deleted
            still.append(row)
            continue
        item = res.get("item", res)
        login = item.get("loginData") or {}
        buyer = (item.get("buyer") or {}) or {}
        owned = (item.get("item_state") == "paid"
                 or buyer.get("user_id") == 10297413
                 or bool(login.get("login")))
        if owned:  # we own it (auto-buy fired on accepted discount)
            log(f"[discount] ACCEPTED & bought {iid} [{row['game']}] "
                f"за {row['requested']}₽")
            # POST-PURCHASE AUDIT
            v_game, v_match, v_detail = verify_games(item, row["game"])
            log(f"[audit] {iid}: {v_detail}")
            if not v_match:
                notify(f"⚠️ Аудит: ожидали [{row['game']}], "
                       f"на аккаунте [{v_game}]. Выкладываю честно.")
                row["game"] = v_game
            notify(f"🟢 Куплено со скидкой: {iid} [{row['game']}] "
                   f"за {row['requested']}₽ (просили у {row.get('price')}₽)")
            ok, info = relist({"item": item}, row["requested"], row["game"])
            if ok:
                st["spent"] += row["requested"]
                st["bought_ids"].append(iid)
                st["my_listings"].append({
                    "item_id": iid, "bought": row["requested"],
                    "game": row["game"], "link": info.split(" ")[0],
                    "ts": row["ts"]})
                log(f"[sell] OK {iid} -> {info}")
                notify(f"✅ Выставлено: {info} [{row['game']}] "
                       f"(куплено за {row['requested']}₽)")
            else:
                log(f"[discount] relist FAIL {iid}: {info}")
                st["bought_ids"].append(iid)
                queue_relist(iid, row["requested"], row["game"])
            continue
        if age_h > 24:
            log(f"[discount] expired {iid}")
            continue
        still.append(row)
    if len(still) != len(st["pending_discounts"]):
        st["pending_discounts"] = still
        save_state(st)


def deep_sweep(seen: set, st: dict) -> None:
    """Full pass over existing cheap inventory in BOTH sections: mispriced
    gems sometimes sit for days while the fresh-lot sniper never sees them."""
    found = 0
    for endpoint, detector in (("/fortnite", detect_game_fortnite),
                               ("/epicgames", detect_game_epicgames)):
        for page in range(1, SWEEP_PAGES + 1):
            try:
                res = api_call("GET", endpoint,
                               {"pmin": "1", "pmax": "100",
                                "order_by": "price_to_up",
                                "page": str(page)})
            except Exception as e:  # noqa: BLE001
                log(f"[sweep] {endpoint} page {page}: "
                    f"{type(e).__name__}: {str(e)[:100]}")
                break
            items = res.get("items", [])
            for it in items:
                iid = it.get("item_id")
                if iid in seen or iid in st["bought_ids"]:
                    continue
                seen.add(iid)
                before = found
                handle_find(it, st, detector)
                found = before  # count only below via detector hit logging
            if not res.get("hasNextPage"):
                break
            time.sleep(1)
    log(f"[sweep] done over fortnite+epicgames inventory")


def relist(bought: dict, buy_price: float, game: str) -> tuple[bool, str]:
    item = bought.get("item", bought)
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    cookies = (item.get("extra") or {}).get("cookies") or item.get("cookies")
    floor, target, med = resale_stats(game)
    sell_price = max(1.0, target)
    body = {
        "title": game,
        "title_en": game,
        "price": sell_price,
        "category_id": RESELL_CATEGORY,
        "currency": "rub",
        "item_origin": "resale",
        "resell_item_id": item.get("item_id"),
        "allow_ask_discount": True,
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
    if game == "GTA V":
        # SC linkage is undetectable pre-purchase (Rockstar-side); the market
        # convention is selling such accounts explicitly "no SC access".
        body["title"] = "GTA V (Epic) возможна привязка SC, без доступа к SC"
        body["title_en"] = "GTA V (Epic), SC access not included"
        body["description"] = (
            "GTA V Premium Edition на Epic Games. Полный доступ к Epic и "
            "почте. Внимание: возможна привязка Social Club без передачи "
            "доступа к SC (стандарт для Epic-аккаунтов с GTA).")
    else:
        body["description"] = f"{game} (Epic Games). Полный доступ, " \
                              f"почта в комплекте."
    try:
        res = api_call("POST", "/item/fast-sell", data=body)
    except RuntimeError as e:
        err = str(e).lower()
        if game == "GTA V" and ("social" in err or "rockstar" in err
                                or "sc " in err):
            # Checker demands SC data we don't have — retry as a generic
            # Epic account lot instead of stranding the purchase.
            body["title"] = "Epic Games | GTA V + игры"
            body["title_en"] = "Epic Games | GTA V + games"
            body["description"] = ("Epic Games аккаунт с играми (в т.ч. "
                                   "GTA V). Полный доступ к Epic и почте.")
            try:
                res = api_call("POST", "/item/fast-sell", data=body)
            except RuntimeError as e2:
                return False, str(e2)[:300]
        else:
            return False, str(e)[:300]
    link = res.get("itemLink") or f"https://lzt.market/{res.get('item', {}).get('item_id')}/"
    return True, f"{link} за {sell_price:.0f}₽ (floor {floor:.0f})"


def try_buy(it: dict, ev: str, st: dict, game: str) -> None:
    price = float(it.get("price", 999))
    floor, target, med = resale_stats(game)
    cap = max_payable(target, game)
    if price > cap:
        log(f"[guard] {it['item_id']} [{game}] price {price:.0f} > "
            f"cap {cap:.0f} (target {target:.0f})")
        return
    bal = balance_rub()
    if bal - price < BALANCE_FLOOR:
        log(f"[guard] balance {bal} too low for price {price}")
        notify(f"⚠️ Баланс {bal}₽ — не хватает на лот {it['item_id']} "
               f"[{game}] за {price}₽. Жду продажи своих лотов.")
        return

    log(f"[buy] ATTEMPT {it['item_id']} [{game}] price={price} "
        f"evidence={ev}")
    bought = fast_buy(it["item_id"], price)
    if not bought:
        notify(f"❌ Покупка {it['item_id']} [{game}] не прошла")
        return
    st["bought"] += 1
    st["bought_ids"].append(it["item_id"])
    save_state(st)
    log(f"[buy] OK {it['item_id']} [{game}]")

    # POST-PURCHASE AUDIT: verify the game is actually on the account
    bought_item = bought.get("item", bought)
    verified_game, matches, audit_detail = verify_games(bought_item, game)
    log(f"[audit] {it['item_id']}: {audit_detail}")
    if not matches:
        notify(f"⚠️ Аудит: ожидали [{game}], на аккаунте [{verified_game}]. "
               f"Выкладываю честно.")
        game = verified_game  # relist under the real content
        price = float(bought_item.get("price", price))  # keep original

    notify(f"🟢 Куплено: {it['item_id']} [{game}] за {price}₽")
    ok, info = relist(bought, price, game)
    if ok:
        log(f"[sell] OK {it['item_id']} [{game}] -> {info}")
        st["spent"] += price
        st["my_listings"].append({
            "item_id": it["item_id"], "bought": price, "game": game,
            "link": info.split(" ")[0] if info else "",
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        save_state(st)
        notify(f"✅ Выставлено: {info} [{game}] (куплено за {price}₽)")
    else:
        log(f"[sell] FAIL {it['item_id']}: {info}")
        queue_relist(it["item_id"], price, game)
        notify(f"🟠 Купил {it['item_id']} [{game}] за {price}₽, "
               f"выкладка отложена в очередь: {info[:100]}")


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
            banner = ""
            if not st.get("first_flip_reported"):
                st["first_flip_reported"] = True
                banner = ("🎉 ПЕРВЫЙ ПОЛНЫЙ ЦИКЛ: куплено → продано.\n")
            notify(f"{banner}💰 Продано: {row.get('link') or iid} [{row.get('game','?')}] — "
                   f"куплено {row['bought']}₽, продано {sold_for or '?'}₽"
                   + (f", профит {profit:.0f}₽" if profit is not None else "")
                   + f". Баланс в обороте, продолжаю.")
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


def queue_relist(item_id: int, price: float, game: str) -> None:
    st = load_state()
    if any(r["item_id"] == item_id for r in st["pending_relists"]):
        return
    st["pending_relists"].append({
        "item_id": item_id, "price": price, "game": game,
        "attempts": 0,
        "ts": datetime.now().isoformat(timespec="seconds")})
    save_state(st)
    log(f"[relist-queue] {item_id} [{game}] queued "
        f"(checker/cookies issue, will retry)")


def harvest_epic_cookies(item_id: int) -> bool:
    """Run the background Epic login harvester for an item we own."""
    import os
    import subprocess
    env = {**os.environ, "EPIC_NOPROXY": "1",
           "PYTHONIOENCODING": "utf-8"}
    try:
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name(
                "epic_login_browser.py")), str(item_id)],
            env=env, capture_output=True, text=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        log(f"[harvest] {item_id}: {type(e).__name__}: {e}")
        return False
    return (Path(__file__).with_name(
        f"epic_cookies_{item_id}.json")).exists()


def fetch_paid_emails() -> dict[int, str]:
    """Bulk-download credentials of our paid orders (the discount auto-buy
    path never shows email data on the item card). Returns {item_id:
    'email:password'}."""
    cache_file = Path(__file__).with_name("item_emails.json")
    cache = {}
    if cache_file.exists():
        try:
            cache = {int(k): v for k, v in
                     json.loads(cache_file.read_text(encoding="utf-8")).items()}
        except ValueError:
            cache = {}
    try:
        text = api_call("GET", "/user/orders/download",
                        {"show": "paid", "format": "custom",
                         "custom_format": "{item_id}|{email}|{email_password}"},
                        raw=True)
    except RuntimeError as e:
        log(f"[emails] download failed: {str(e)[:120]}")
        return cache
    for ln in text.splitlines():
        parts = ln.split("|")
        if len(parts) >= 3 and parts[0].strip().isdigit() \
                and parts[2].strip():
            cache[int(parts[0])] = f"{parts[1].strip()}:{parts[2].strip()}"
    cache_file.write_text(
        json.dumps({str(k): v for k, v in cache.items()}), encoding="utf-8")
    return cache


def relist_with_cookies(item_id: int, price: float, game: str) -> tuple[bool, str]:
    """Relist using freshly harvested Epic session cookies."""
    cookies_file = Path(__file__).with_name(f"epic_cookies_{item_id}.json")
    cookies = cookies_file.read_text(encoding="utf-8").strip()
    res = api_call("GET", f"/{item_id}")
    item = res.get("item", res)
    login = item.get("loginData") or {}
    email = item.get("emailLoginData") or {}
    if not email.get("login"):
        creds = fetch_paid_emails().get(item_id, "")
        if creds:
            email = {"login": creds.split(":", 1)[0],
                     "password": creds.split(":", 1)[1]}
    floor, target, med = resale_stats(game)
    body = {
        "title": game, "title_en": game, "price": max(1.0, target),
        "category_id": RESELL_CATEGORY, "currency": "rub",
        "item_origin": "resale", "resell_item_id": item_id,
        "allow_ask_discount": True,
        "description": f"{game} (Epic Games). Полный доступ, "
                       f"почта в комплекте.",
        "extra": {"cookies": cookies, "close_item": False},
    }
    if login.get("login"):
        body["login_password"] = f"{login['login']}:{login['password']}"
    if email.get("login"):
        body["has_email_login_data"] = True
        body["email_login_data"] = f"{email['login']}:{email['password']}"
        body["email_type"] = "native"
    try:
        res = api_call("POST", "/item/fast-sell", data=body)
    except RuntimeError as e:
        return False, str(e)[:300]
    link = res.get("itemLink") or f"https://lzt.market/" \
           f"{res.get('item', {}).get('item_id')}/"
    return True, f"{link} за {target}₽ (floor {floor})"


def check_pending_relists(st: dict) -> None:
    """Retry relisting bought accounts; harvest cookies when demanded."""
    still = []
    for row in st["pending_relists"]:
        iid = row["item_id"]
        row["attempts"] += 1
        try:
            res = api_call("GET", f"/{iid}")
            item = res.get("item", res)
            ok, info = relist({"item": item}, row["price"], row["game"])
        except RuntimeError as e:
            ok, info = False, str(e)[:200]
        if not ok and ("cookie" in info.lower()
                       or "почте" in info or "почт" in info):
            log(f"[relist-queue] {iid}: needs cookies/email -> "
                f"harvest + paid-orders creds")
            if harvest_epic_cookies(iid):
                ok, info = relist_with_cookies(iid, row["price"], row["game"])
                log(f"[relist-queue] cookie relist {iid}: ok={ok} {info}")
            else:
                log(f"[relist-queue] harvest failed for {iid}")
                ok = False
        if ok:
            log(f"[relist-queue] OK {iid} -> {info}")
            st["my_listings"].append({
                "item_id": iid, "bought": row["price"], "game": row["game"],
                "link": info.split(" ")[0], "ts": row["ts"]})
            notify(f"✅ Отложенная выкладка прошла: {iid} [{row['game']}] "
                   f"-> {info}")
            continue
        if row["attempts"] >= 120:  # ~30 min of cycles
            log(f"[relist-queue] giving up {iid}: {info}")
            notify(f"🟠 Не удалось выложить {iid} [{row['game']}]: {info}. "
                   f"Нужно вручную (возможно, требуются cookies).")
            continue
        still.append(row)
    if len(still) != len(st["pending_relists"]):
        st["pending_relists"] = still
        save_state(st)


def handle_find(it: dict, st: dict, detector) -> None:
    """Common buy/discount decision for a candidate lot from any section."""
    hit = detector(it)
    if not hit:
        return
    game, ev = hit
    floor, target, med = resale_stats(game)
    if target <= 0:
        return
    price = float(it.get("price", 999))
    log(f"[find] https://lzt.market/{it.get('item_id')}/ "
        f"{price:.0f}₽ [{game}] :: {ev}")
    if price <= max_payable(target, game):
        try_buy(it, ev, st, game)
    else:
        try_discount(it, st, game, target)


def cycle(seen: set, st: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    if st["day"] != today:
        st["day"] = today
        st["bought"] = 0
        save_state(st)
    # Server-side freshness filter: only lots published since the previous
    # cycle arrive (tiny response, fast even via the narrow proxy). Price
    # history for ALL lots is collected separately by the price dumper.
    now_epoch = int(time.time())
    # Clamp to max 60s lookback: the Georgia proxy truncates large JSON
    # responses; at 5s cycles we only need the last minute at most
    since = max(int(st.get("last_new_scan", now_epoch - 30)) - 10,
                now_epoch - 60)
    for endpoint, detector in (("/fortnite", detect_game_fortnite),
                               ("/epicgames", detect_game_epicgames)):
        res = api_call("GET", endpoint,
                       {"published_after": str(since),
                        "pmin": "1", "pmax": str(MAX_BUY_PRICE),
                        "order_by": "pdate_to_down", "page": "1"})
        for it in res.get("items", []):
            iid = it.get("item_id")
            if iid in seen or iid in st["bought_ids"]:
                continue
            seen.add(iid)
            handle_find(it, st, detector)
    st["last_new_scan"] = now_epoch


def main() -> None:
    print("autonomous flipper started: fresh lots in fortnite+epicgames "
          f"| max_buy {MAX_BUY_PRICE}₽ | margin ≥{MIN_MARGIN}₽ "
          f"(ROI ≥{MARGIN_RATIO}x) | no daily cap", flush=True)
    from lzt_prices import dump as price_dump
    seen = load_seen()
    st = load_state()
    n = 0
    while True:
        n += 1
        try:
            cycle(seen, st)
            check_my_listings(st)
            check_pending_discounts(st)
            check_pending_relists(st)
            if n % SWEEP_EVERY == 0:
                deep_sweep(seen, st)
            if n % PRICE_DUMP_EVERY == 0:
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
        except BaseException:
            import traceback
            tb = traceback.format_exc()
            log(f"[CRASH-RECOVERED] {tb[:800]}")
        save_seen(seen)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
