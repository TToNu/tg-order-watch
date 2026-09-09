"""Probe: do search results include transactions, and what filters exist?"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call


def main() -> None:
    res = api_call("GET", "/fortnite",
                   {"pmin": "20", "pmax": "60", "order_by": "price_to_up"})
    items = res.get("items", [])
    with_tr = [it for it in items if it.get("fortniteTransactions")]
    print(f"items: {len(items)}, with transactions in search: {len(with_tr)}")
    for it in with_tr[:3]:
        print(f"\n{it['item_id']} {it.get('price')}₽ "
              f"{(it.get('title') or '')[:40]}")
        print("  transactions:",
              json.dumps(it["fortniteTransactions"], ensure_ascii=False)[:400])

    try:
        params = api_call("GET", "/fortnite/params")
        print("\n=== category search params (keys) ===")
        print(json.dumps(params, ensure_ascii=False, indent=1)[:2500])
    except Exception as e:  # noqa: BLE001
        print("params endpoint failed:", e)


if __name__ == "__main__":
    main()
