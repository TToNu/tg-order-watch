"""Print order matches and sent auto-replies not yet shown.

Reads orders.log and sent.log (written by monitor.py, one JSON object per
line each) and remembers per-file line counts in scripts/.orders_read and
scripts/.sent_read, so every run shows only what appeared since the previous
run. No Telegram connection needed.
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "orders.log"
SENT = BASE / "sent.log"
STATE_ORDERS = Path(__file__).with_name(".orders_read")
STATE_SENT = Path(__file__).with_name(".sent_read")


def new_lines(path: Path, state: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = int(state.read_text()) if state.exists() else 0
    state.write_text(str(len(lines)), encoding="utf-8")
    return lines[seen:]


def parse(line: str) -> dict | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def main() -> int:
    orders = [rec for ln in new_lines(LOG, STATE_ORDERS) if (rec := parse(ln))]
    sent = [rec for ln in new_lines(SENT, STATE_SENT) if (rec := parse(ln))]

    if orders:
        print(f"### NEW ORDERS ({len(orders)})")
        for rec in orders:
            who = rec["who"].lstrip("@")
            print("=" * 60)
            print(f"[{rec['ts']}] {rec['chat']} — from @{who}")
            print(f"link: {rec['link']}")
            print(rec["text"][:1200])
    else:
        print("### no new orders")

    if sent:
        print()
        print(f"### AUTO-REPLIES SENT SINCE LAST CHECK ({len(sent)})")
        for rec in sent:
            print("=" * 60)
            print(f"[{rec['ts']}] {rec['chat']}")
            print(f"order: {rec['link']}")
            print(f"we sent: {rec['sent']}")
    else:
        print("### no new auto-replies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
