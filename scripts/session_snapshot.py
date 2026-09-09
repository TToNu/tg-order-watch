"""Snapshot the live sqlite session file with retries.

The long-running monitor keeps session.session locked much of the time;
helper scripts connect with a throwaway copy instead. A copy taken mid-write
can look unauthorized, so validate the auth key and retry.
"""

import shutil
import sqlite3
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def snapshot(dst_name: str = "session.helper") -> Path:
    src = BASE / "session.session"
    dst = BASE / dst_name
    for _ in range(20):
        try:
            shutil.copy2(src, dst)
            con = sqlite3.connect(dst)
            try:
                row = con.execute(
                    "select count(*) from sessions where auth_key is not null"
                ).fetchone()
            finally:
                con.close()
            if row and row[0]:
                return dst
        except (OSError, sqlite3.Error):
            pass
        time.sleep(1.5)
    sys.exit("cannot snapshot session.session (locked or empty)")
