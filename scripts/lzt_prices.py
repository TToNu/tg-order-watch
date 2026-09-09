"""lzt.market price dumper + sales/pricing statistics.

Dumps snapshots of the Epic Games DBD listings and cheap Fortnite lots to
prices/*.jsonl. Items that vanish between snapshots are treated as sold
(good-enough proxy: deletions are rare vs sales in this niche).

Usage:
    python lzt_prices.py dump              # one snapshot now
    python lzt_prices.py stats             # price stats + sales velocity
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

PRICE_DIR = Path(__file__).resolve().parent.parent / "prices"
FEEDS = {
    "dbd": ("/epicgames", {"title": "dead by daylight",
                           "order_by": "price_to_up"}),
    "gta": ("/epicgames", {"title": "gta", "order_by": "price_to_up"}),
    "chivalry2": ("/epicgames", {"title": "chivalry 2",
                                 "order_by": "price_to_up"}),
    "disco_elysium": ("/epicgames", {"title": "disco elysium",
                                     "order_by": "price_to_up"}),
    "ghostrunner2": ("/epicgames", {"title": "ghostrunner 2",
                                    "order_by": "price_to_up"}),
    "fortnite_cheap": ("/fortnite", {"pmin": "1", "pmax": "60",
                                     "order_by": "pdate_to_down"}),
}
PAGES = 3
GONE_MINUTES = 20   # absent this long => count as sold


def dump() -> int:
    PRICE_DIR.mkdir(exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    path = PRICE_DIR / f"{day}.jsonl"
    ts = datetime.now().isoformat(timespec="seconds")
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for feed, (endpoint, params) in FEEDS.items():
            for page in range(1, PAGES + 1):
                try:
                    res = api_call("GET", endpoint,
                                   {**params, "page": str(page)})
                except Exception as e:  # noqa: BLE001
                    print(f"[dump] {feed} p{page}: {e}", file=sys.stderr)
                    continue
                items = res.get("items", [])
                for it in items:
                    rec = {"ts": ts, "feed": feed,
                           "id": it.get("item_id"),
                           "price": it.get("price"),
                           "title": (it.get("title") or "")[:60]}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
                if not res.get("hasNextPage"):
                    break
    print(f"dumped {n} records -> {path.name}")
    return n


def load_records() -> list[dict]:
    recs = []
    for f in sorted(PRICE_DIR.glob("*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            try:
                recs.append(json.loads(ln))
            except ValueError:
                continue
    return recs


def stats() -> None:
    recs = load_records()
    if not recs:
        print("no data yet — run dump first")
        return
    dbd = [r for r in recs if r["feed"] == "dbd"]
    now = datetime.now()

    # --- price distribution over the last hour of snapshots ---
    seen: dict[int, dict] = {}
    for r in dbd:
        cur = seen.get(r["id"])
        if not cur or r["ts"] > cur["ts"]:
            seen[r["id"]] = r
    prices = sorted(float(r["price"]) for r in seen.values()
                    if r.get("price") is not None)
    if prices:
        q = quantiles(prices, n=4) if len(prices) >= 4 else []
        print(f"DBD active listings now: {len(prices)}")
        print(f"  floor {prices[0]:.0f} | p25 {q[0] if q else 0:.0f} | "
              f"median {median(prices):.0f} | "
              f"p75 {q[2] if q else 0:.0f} | top {prices[-1]:.0f}")

    # --- sales velocity: items that disappeared ---
    first_seen: dict[int, str] = {}
    last_seen: dict[int, tuple[str, float]] = {}
    for r in dbd:
        iid = r["id"]
        if iid not in first_seen:
            first_seen[iid] = r["ts"]
        last_seen[iid] = (r["ts"], float(r.get("price") or 0))
    gone_ids = [i for i, (ts, _) in last_seen.items()
                if (now - datetime.fromisoformat(ts)).total_seconds() / 60
                >= GONE_MINUTES]
    if gone_ids:
        start = min(datetime.fromisoformat(first_seen[i]) for i in gone_ids)
        hours_span = max((now - start).total_seconds() / 3600, 0.5)
        sold_prices = sorted(last_seen[i][1] for i in gone_ids)
        print(f"\nDBD sold (disappeared) in window: {len(gone_ids)} "
              f"≈ {len(gone_ids) / hours_span:.1f} шт/час")
        print(f"  sold price median ≈ {median(sold_prices):.0f}₽ "
              f"(min {sold_prices[0]:.0f}, max {sold_prices[-1]:.0f})")

    # --- cheap fortnite feed overview ---
    fn = [r for r in recs if r["feed"] == "fortnite_cheap"]
    fn_seen: dict[int, tuple[str, float]] = {}
    for r in fn:
        cur = fn_seen.get(r["id"])
        if not cur or r["ts"] > cur[0]:
            fn_seen[r["id"]] = (r["ts"], float(r.get("price") or 0))
    if fn_seen:
        fn_prices = sorted(p for _, p in fn_seen.values())
        print(f"\nFortnite 1-60₽ tracked: {len(fn_prices)} lots, "
              f"median {median(fn_prices):.0f}₽")

    print(f"\nrecords total: {len(recs)} "
          f"(since {recs[0]['ts'] if recs else '-'})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        dump()
    elif cmd == "stats":
        stats()
    else:
        sys.exit(__doc__)
