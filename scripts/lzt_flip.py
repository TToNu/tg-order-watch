"""Fortnite -> EpicGames flip scanner for lzt.market.

Concept (user's scheme): buy cheap Fortnite-section accounts (1-20 RUB) that
own Dead by DayLIGHT (visible in fortniteTransactions / title / description),
then relist in the Epic Games section at the DBD market price.

Usage:
    python lzt_flip.py scan [pages]     # find DBD candidates among cheap lots
    python lzt_flip.py price            # current DBD price level in epicgames
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

DBD_RE = re.compile(r"(dead\s*by\s*day\s*light|dbd|\bdaylight\b|дбд)", re.I)
STATE = Path(__file__).with_name(".flip_seen.json")


def load_seen() -> set:
    if STATE.exists():
        return set(json.loads(STATE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    STATE.write_text(json.dumps(list(seen))[-200000:], encoding="utf-8")


def item_has_dbd(it: dict) -> str | None:
    """Return evidence string if the lot mentions/owns Dead by Daylight."""
    text = " ".join(filter(None, [it.get("title"), it.get("title_en"),
                                  it.get("description"),
                                  it.get("description_en")]))
    if DBD_RE.search(text):
        return f"title/description: {text[:80]!r}"
    for tr in it.get("fortniteTransactions") or []:
        label = " ".join(str(v) for v in tr.values())
        if DBD_RE.search(label):
            return f"transaction: {label[:80]!r}"
    return None


def scan(pages: int, pmin: str = "1", pmax: str = "20") -> None:
    seen = load_seen()
    fresh = []
    for page in range(pages):
        params = {"pmin": pmin, "pmax": pmax, "order_by": "price_to_up",
                  "page": str(page + 1)}
        res = api_call("GET", "/fortnite", params)
        items = res.get("items", [])
        if not items:
            break
        for it in items:
            iid = it.get("item_id")
            if iid in seen:
                continue
            seen.add(iid)
            ev = item_has_dbd(it)
            if ev:
                fresh.append((it, ev))
        print(f"page {page + 1}: {len(items)} items, "
              f"hasNextPage={res.get('hasNextPage')}")
        if not res.get("hasNextPage"):
            break
    save_seen(seen)
    print(f"scanned, candidates with DBD mention: {len(fresh)} "
          f"(seen total {len(seen)})")
    for it, ev in fresh:
        print(f"\nhttps://lzt.market/{it['item_id']}/  {it.get('price')}₽  "
              f"seller={it.get('seller', {}).get('username')}")
        print(f"  evidence: {ev}")
        tr_count = len(it.get("fortniteTransactions") or [])
        print(f"  transactions: {tr_count}, "
              f"skins: {it.get('fortnite_skin_count')}, "
              f"vbucks: {it.get('fortnite_balance')}")


def price_level() -> None:
    res = api_call("GET", "/epicgames",
                   {"title": "dead by daylight", "order_by": "price_to_up"})
    items = res.get("items", [])
    print(f"epicgames 'dead by daylight' lots: {res.get('totalItems')}")
    for it in items[:10]:
        print(f"{it.get('item_id')}  {it.get('price')}₽  "
              f"{(it.get('title') or '')[:70]}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        scan(int(sys.argv[2]) if len(sys.argv) > 2 else 5,
             sys.argv[3] if len(sys.argv) > 3 else "1",
             sys.argv[4] if len(sys.argv) > 4 else "20")
    elif cmd == "price":
        price_level()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
