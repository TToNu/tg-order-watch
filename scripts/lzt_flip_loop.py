"""Continuous lzt.market Fortnite->DBD flip watcher.

Every cycle scans both cheap ranges (1-20 and 20-60 RUB) of the Fortnite
section, detects Dead by Daylight ownership in parsed transactions/titles,
and on a fresh hit:
  - appends it to flip_finds.log
  - alerts the user's Telegram Saved Messages via the monitor's cmds.json
    protocol (the same one say.py uses).

Resilient: any error is logged and the loop continues; market 5xx storms
just produce empty cycles. Run in its own console window.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call
from lzt_flip import DBD_RE, item_has_dbd, load_seen, save_seen

BASE = Path(__file__).resolve().parent.parent
FINDS_LOG = BASE / "flip_finds.log"
CMDS = BASE / "cmds.json"
CMDS_RESULT = BASE / "cmds.result.json"
RANGES = [("1", "25"), ("25", "60")]
PAGES_PER_RANGE = 3
CYCLE_SECONDS = 150


def notify(text: str) -> None:
    """Send a message to Saved Messages through the running tg monitor."""
    deadline = time.time() + 30
    while CMDS.exists() and time.time() < deadline:
        time.sleep(1)
    if CMDS.exists():
        print("[notify] cmds.json busy, skipping telegram alert")
        return
    CMDS_RESULT.unlink(missing_ok=True)
    CMDS.write_text(json.dumps(
        {"send": [{"chat": "me", "reply_to": None, "text": text}]},
        ensure_ascii=False), encoding="utf-8")
    deadline = time.time() + 30
    while not CMDS_RESULT.exists() and time.time() < deadline:
        time.sleep(1)
    ok = False
    if CMDS_RESULT.exists():
        try:
            res = json.loads(CMDS_RESULT.read_text(encoding="utf-8"))
            ok = (res.get("send") or [{}])[0].get("ok", False)
        except ValueError:
            pass
        CMDS_RESULT.unlink(missing_ok=True)
    print(f"[notify] telegram alert {'sent' if ok else 'FAILED'}")


def cycle(seen: set) -> int:
    found = 0
    for pmin, pmax in RANGES:
        for page in range(1, PAGES_PER_RANGE + 1):
            res = api_call("GET", "/fortnite",
                           {"pmin": pmin, "pmax": pmax,
                            "order_by": "pdate_to_down",
                            "page": str(page)})
            items = res.get("items", [])
            for it in items:
                iid = it.get("item_id")
                if iid in seen:
                    continue
                seen.add(iid)
                ev = item_has_dbd(it)
                if not ev:
                    continue
                found += 1
                price = it.get("price")
                link = f"https://lzt.market/{iid}/"
                seller = (it.get("seller") or {}).get("username")
                line = (f"{datetime.now().isoformat(timespec='seconds')} "
                        f"{link} {price}R seller={seller} :: {ev}")
                print(line, flush=True)
                with FINDS_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                notify(f"🎯 DBD-лот: {link} за {price}₽ (продавец {seller})\n"
                       f"{ev}\nЦена перепродажи ~86-90₽. Проверь и купи!")
            if not res.get("hasNextPage"):
                break
    return found


def main() -> None:
    print("flip watcher started: ranges "
          + ", ".join(f"{a}-{b}₽" for a, b in RANGES)
          + f", cycle {CYCLE_SECONDS}s", flush=True)
    seen = load_seen()
    n = 0
    while True:
        n += 1
        try:
            found = cycle(seen)
            print(f"[cycle {n}] {datetime.now():%H:%M:%S} "
                  f"seen={len(seen)} new_finds={found}", flush=True)
        except Exception as e:  # noqa: BLE001 - never die
            print(f"[cycle {n}] error: {type(e).__name__}: {e}", flush=True)
        save_seen(seen)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
