"""List entity-cache rows for every config chat to spot the banned one."""

import json
import sqlite3
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
CHATS = CFG.get("chats", []) + CFG.get("activity", {}).get("chats", [])


def main() -> None:
    for _ in range(15):
        try:
            con = sqlite3.connect(BASE / "session.session")
            try:
                rows = con.execute(
                    "select username, id from entities where username is not null"
                ).fetchall()
            finally:
                con.close()
            break
        except sqlite3.Error:
            time.sleep(2)
    else:
        print("session db locked")
        return

    known = {u.lower(): i for u, i in rows}
    missing = []
    for ref in dict.fromkeys(CHATS):
        uname = ref.rsplit("/", 1)[-1].lstrip("@").lower()
        if uname in known:
            print(f"ok       @{uname} -> {known[uname]}")
        else:
            missing.append(uname)
            print(f"MISSING  @{uname}  <- likely the banned chat")
    print("\nmissing count:", len(missing))


if __name__ == "__main__":
    main()
