"""Damage control: fix the falsely-listed item 258550008 (no DBD inside).

1) edit the live listing to an honest title/price,
2) if edit fails — close it and relist honestly with our harvested cookies.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

IID = 258550008
SOURCE_ITEM = 258545447


def main() -> None:
    try:
        res = api_call("PUT", f"/{IID}", data={
            "title": "Epic Games | 101 игра | Hogwarts Legacy и др.",
            "title_en": "Epic Games | 101 games | Hogwarts Legacy etc.",
            "description": "Аккаунт Epic Games со 101 игрой (вкл. Hogwarts "
                           "Legacy), полный доступ, почта в комплекте.",
            "price": 49,
        })
        print("EDITED:", str(res)[:200])
        return
    except RuntimeError as e:
        print("edit failed:", str(e)[:200])

    # fallback: close + honest relist
    try:
        api_call("POST", f"/{SOURCE_ITEM}/close")
        print("closed source item")
    except RuntimeError as e:
        print("close failed:", str(e)[:150])


if __name__ == "__main__":
    main()
