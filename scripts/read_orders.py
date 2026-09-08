"""Print order matches not yet shown.

Reads orders.log (written by monitor.py, one JSON object per line) and
remembers the line count in scripts/.orders_read, so every run shows only
what appeared since the previous run. No Telegram connection needed.
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "orders.log"
STATE = Path(__file__).with_name(".orders_read")


def main() -> int:
    if not LOG.exists():
        print("no orders.log yet — monitor has not matched anything")
        return 0
    lines = LOG.read_text(encoding="utf-8").splitlines()
    seen = int(STATE.read_text()) if STATE.exists() else 0
    new = lines[seen:]
    STATE.write_text(str(len(lines)), encoding="utf-8")

    if not new:
        print(f"no new orders (total records {len(lines)})")
        return 0

    for ln in new:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        who = rec["who"].lstrip("@")
        print("=" * 60)
        print(f"[{rec['ts']}] {rec['chat']} — from @{who}")
        print(f"link: {rec['link']}")
        print(rec["text"][:1200])
    print("=" * 60)
    print(f"{len(new)} new order(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
