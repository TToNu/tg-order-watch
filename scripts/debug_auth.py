"""Debug: snapshot session, connect, print authorization state and errors."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_snapshot import snapshot  # noqa: E402

CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

logging.basicConfig(level=logging.WARNING)


async def main() -> None:
    ses = snapshot()
    proxy = CFG.get("proxy")
    conn = ConnectionTcpMTProxyRandomizedIntermediate
    proxy_arg = (proxy["host"], int(proxy["port"]), proxy["secret"])
    client = TelegramClient(
        str(ses), CFG["api_id"], CFG["api_hash"],
        connection=conn, proxy=proxy_arg,
    )
    await client.connect()
    try:
        me = await client.get_me()
        print("authorized as:", getattr(me, "username", None), getattr(me, "first_name", None))
    except Exception as e:
        print("get_me failed:", type(e).__name__, e)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
