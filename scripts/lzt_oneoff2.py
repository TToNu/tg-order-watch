"""Finish the interrupted flow: relist already-bought item 258545447."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call
from lzt_flip_loop import load_state, log, relist, save_state, STATE

IID = 258545447
PRICE = 39.0
GAME = "Dead by Daylight"


def main() -> None:
    st = load_state()
    if IID not in st["bought_ids"]:
        st["bought_ids"].append(IID)
    res = api_call("GET", f"/{IID}")
    item = res.get("item", res)
    ok, info = relist({"item": item}, PRICE, GAME)
    if ok:
        st["spent"] += PRICE
        st["my_listings"].append({
            "item_id": IID, "bought": PRICE, "game": GAME,
            "link": info.split(" ")[0],
            "ts": datetime.now().isoformat(timespec="seconds")})
        log(f"[manual] relisted: {info}")
    else:
        log(f"[manual] relist FAILED: {info}")
    save_state(st)


if __name__ == "__main__":
    main()
