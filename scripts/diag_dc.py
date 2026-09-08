"""Diagnose why DC pinning does not apply."""

import asyncio
import json
from pathlib import Path

from telethon import TelegramClient

HERE = Path(__file__).resolve().parent.parent
cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
print("config dc:", cfg.get("dc"))

session_path = HERE / "session"
print("session file exists before:", session_path.with_suffix(".session").exists())

client = TelegramClient(str(session_path), cfg["api_id"], cfg["api_hash"])
print("after ctor, session.server_address =", client.session.server_address)

if cfg.get("dc") and not session_path.with_suffix(".session").exists():
    client.session.set_dc(cfg["dc"]["id"], cfg["dc"]["ip"], cfg["dc"].get("port", 443))
    print("after set_dc, session.server_address =", client.session.server_address)
    print("dc_id =", client.session.dc_id)


async def try_connect():
    await client.connect()
    print("connected! server:", client.session.server_address)
    await client.disconnect()


asyncio.run(try_connect())
