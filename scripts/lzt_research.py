"""Market research: which games hide in cheap Fortnite lots and what they
resell for in the Epic Games section.

Steps:
  1. Pull N pages of cheap Fortnite lots (<= 60 RUB), parse
     fortniteTransactions -> game titles, paid amounts, frequencies.
  2. For the top paid games, query the Epic Games section price distribution.
  3. Print an attractiveness table (frequency x resale price x market depth).

Usage: python lzt_research.py [pages]
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

JUNK = re.compile(r"v[- ]?bucks|vbucks|pack|battle pass|fortnite|"
                  r"rocket league|fall guys|discord nitro|"
                  r"deep silver bundle", re.I)


def norm_title(t: str) -> str:
    t = re.sub(r"[®™]", "", t or "").strip()
    return t


def main() -> None:
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    freq = Counter()
    paid = defaultdict(float)
    examples = defaultdict(list)
    lots_scanned = 0
    with_tx = 0

    for page in range(1, pages + 1):
        try:
            res = api_call("GET", "/fortnite",
                           {"pmin": "1", "pmax": "60",
                            "order_by": "pdate_to_down",
                            "page": str(page)})
        except Exception as e:  # noqa: BLE001
            print(f"[scan] page {page}: {e}", file=sys.stderr)
            continue
        items = res.get("items", [])
        if not items:
            break
        for it in items:
            lots_scanned += 1
            txs = it.get("fortniteTransactions") or []
            if not txs:
                continue
            with_tx += 1
            for tr in txs:
                title = norm_title(tr.get("title") or "")
                if not title or JUNK.search(title):
                    continue
                freq[title] += 1
                amount = 0.0
                raw = str(tr.get("presentmentTotal") or "0")
                m = re.search(r"([\d.]+)", raw)
                if m:
                    amount = float(m.group(1))
                paid[title] = max(paid[title], amount)
                if len(examples[title]) < 2:
                    examples[title].append(it.get("item_id"))
        if not res.get("hasNextPage"):
            break

    print(f"scanned {lots_scanned} cheap lots; {with_tx} have purchases")
    top = freq.most_common(25)
    if not top:
        print("no candidate games found")
        return

    print(f"\n{'game':38} {'freq':>4} {'paid>0':>6} | "
          f"{'lots':>4} {'floor':>6} {'p25':>6} {'median':>7}")
    print("-" * 90)
    rows = []
    for title, cnt in top:
        try:
            res = api_call("GET", "/epicgames",
                           {"title": title, "order_by": "price_to_up"})
            items = [i for i in res.get("items", [])
                     if i.get("item_state") == "active"][:30]
            if not items:
                continue
            prices = sorted(float(i["price"]) for i in items)
            floor, p25 = prices[0], prices[len(prices) // 4]
            med = median(prices)
            total = res.get("totalItems")
            rows.append((title, cnt, paid[title] > 0, total, floor, p25, med))
            print(f"{title[:38]:38} {cnt:>4} {str(paid[title] > 0):>6} | "
                  f"{total:>4} {floor:>6.0f} {p25:>6.0f} {med:>7.0f}")
        except Exception:  # noqa: BLE001
            continue

    print("\nПриоритет (частота в дешёвых лотах × медиана перепродажи):")
    for title, cnt, is_paid, total, floor, p25, med in sorted(
            rows, key=lambda r: -r[1] * (r[6] or 0))[:10]:
        print(f"  {title}: встреч {cnt}, перепродажа медиана {med:.0f}₽, "
              f"рынок {total} лотов")


if __name__ == "__main__":
    main()
