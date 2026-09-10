"""Debug: relist a queued item and print the actual error."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call
from lzt_flip_loop import relist

IID = int(sys.argv[1]) if len(sys.argv) > 1 else 258553032
PRICE = 43.0
GAME = "Dead by Daylight"

res = api_call("GET", f"/{IID}")
item = res.get("item", res)
print("state:", item.get("item_state"))
ok, info = relist({"item": item}, PRICE, GAME)
print("relist ok:", ok)
print("info:", info[:600])
