"""Pure connectivity check: connect through the MTProto proxy, no login."""

import asyncio
import json
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

HERE = Path(__file__).resolve().parent.parent
cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
p = cfg["proxy"]


async def main() -> None:
    client = TelegramClient(
        str(HERE / "test_session"),
        cfg["api_id"],
        cfg["api_hash"],
        connection=ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=(p["host"], int(p["port"]), p["secret"]),
    )
    print("connecting via", p["host"], p["port"], "...")
    await asyncio.wait_for(client.connect(), timeout=25)
    print("CONNECTED, telegram says we are on dc:", client.session.dc_id)
    await client.disconnect()
    for f in (HERE / "test_session.session",):
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        sys.exit(1)
