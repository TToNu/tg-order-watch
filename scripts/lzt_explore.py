"""Explore fortnite/epicgames item JSON structure via the market API."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call


def main() -> None:
    cat = sys.argv[1] if len(sys.argv) > 1 else "fortnite"
    pmin = sys.argv[2] if len(sys.argv) > 2 else "1"
    pmax = sys.argv[3] if len(sys.argv) > 3 else "20"
    res = api_call("GET", f"/{cat}",
                   {"pmin": pmin, "pmax": pmax, "order_by": "price_to_up"})
    items = res.get("items", [])
    print(f"keys of response: {list(res.keys())}")
    print(f"items: {len(items)}")
    if items:
        it = items[0]
        print("\n=== first item full JSON ===")
        print(json.dumps(it, ensure_ascii=False, indent=1)[:6000])
        print("\n=== all items short ===")
        for it in items[:15]:
            print(f"{it.get('item_id')}  {it.get('price')}₽  "
                  f"{(it.get('title') or '')[:50]}")


if __name__ == "__main__":
    main()
