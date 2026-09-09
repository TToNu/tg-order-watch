"""One-off: finish the interrupted purchase of item 258545447 and relist."""

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt_flip_loop import fast_buy, relist, resale_stats, log, STATE

IID = 258545447
PRICE = 39.0
GAME = "Dead by Daylight"


def main() -> None:
    st = json.loads(STATE.read_text(encoding="utf-8"))
    log(f"[manual] buying {IID} for {PRICE}")
    bought = fast_buy(IID, PRICE)
    if not bought:
        log("[manual] buy failed")
        return
    log(f"[manual] bought {IID}")
    st["bought_ids"].append(IID)
    st["spent"] += PRICE
    ok, info = relist(bought, PRICE, GAME)
    if ok:
        st["my_listings"].append({
            "item_id": IID, "bought": PRICE, "game": GAME,
            "link": info.split(" ")[0],
            "ts": datetime.now().isoformat(timespec="seconds")})
        log(f"[manual] relisted: {info}")
    else:
        log(f"[manual] relist FAILED: {info}")
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
