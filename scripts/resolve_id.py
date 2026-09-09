"""Resolve a chat id from the session's entity cache (read-only, retried)."""

import sqlite3
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGET = 1172763541


def main() -> None:
    for _ in range(15):
        try:
            con = sqlite3.connect(BASE / "session.session")
            try:
                rows = con.execute(
                    "select id, username, name, phone from entities "
                    "where id in (?, ?)",
                    (TARGET, -100 - TARGET),
                ).fetchall()
            finally:
                con.close()
            if rows:
                for r in rows:
                    print(f"id={r[0]} username=@{r[1]} name={r[2]!r} phone={r[3]}")
            else:
                print("no entity row for this id")
            return
        except sqlite3.Error:
            time.sleep(2)
    print("session db locked")


if __name__ == "__main__":
    sys.exit(main())
