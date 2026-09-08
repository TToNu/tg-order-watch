"""Try the top N MTProto proxies until one completes a Telegram handshake."""

from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

HERE = Path(__file__).resolve().parent.parent
cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
proxies = json.loads((HERE / "mtproto.json").read_text(encoding="utf-8"))
TIMEOUT = 6.0
TOP = 12


def reachable(p: dict) -> tuple[float, dict] | None:
    try:
        ip = socket.gethostbyname(p["server"])
        t0 = time.monotonic()
        with socket.create_connection((ip, int(p["port"])), timeout=TIMEOUT):
            return time.monotonic() - t0, p
    except OSError:
        return None


async def try_handshake(p: dict) -> bool:
    client = TelegramClient(
        str(HERE / "test_session"),
        cfg["api_id"],
        cfg["api_hash"],
        connection=ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=(p["server"], int(p["port"]), p["secret"]),
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        ok = client.session.dc_id is not None and client.session.dc_id > 0
        print(f"    handshake OK, dc_id={client.session.dc_id}")
        return True
    except Exception as e:
        print(f"    handshake failed: {type(e).__name__}")
        return False
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main() -> None:
    scored = sorted(
        (r for r in (reachable(p) for p in proxies) if r), key=lambda r: r[0]
    )
    print(f"reachable: {len(scored)}, trying top {TOP}")
    for dt, p in scored[:TOP]:
        print(f"  {p['server']}:{p['port']} ({dt*1000:.0f} ms)")
        if await try_handshake(p):
            (HERE / "best_proxy.json").write_text(
                json.dumps(
                    {"host": p["server"], "port": int(p["port"]), "secret": p["secret"]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print("WINNER ->", p["server"])
            return
    print("no working proxy in top", TOP)
    (HERE / "test_session.session").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
