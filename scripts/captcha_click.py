"""Complete a bot captcha (inline button) and verify our intro post survived."""

import asyncio
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

CHAT = "python_django_work"
CAPTCHA_MSG_ID = 140275
INTRO_MSG_ID = 140272


async def main() -> None:
    proxy = CFG.get("proxy")
    conn = None
    proxy_arg = None
    if proxy and proxy.get("proto") == "mtproto":
        conn = ConnectionTcpMTProxyRandomizedIntermediate
        proxy_arg = (proxy["host"], int(proxy["port"]), proxy["secret"])
    client = TelegramClient(
        str(BASE / "session"), CFG["api_id"], CFG["api_hash"],
        connection=conn, proxy=proxy_arg,
    )
    await client.start(phone=lambda: (_ for _ in ()).throw(RuntimeError("unauthorized")))

    msg = await client.get_messages(CHAT, ids=CAPTCHA_MSG_ID)
    if not msg:
        print("captcha message gone (already handled or deleted)")
    else:
        print(f"captcha text: {(msg.raw_text or '')[:120]!r}")
        if msg.buttons:
            texts = [b.text for row in msg.buttons for b in row]
            print(f"buttons: {texts}")
            await msg.click(0, 0)
            print("clicked first button")
        else:
            print("no inline buttons on the message")

    intro = await client.get_messages(CHAT, ids=INTRO_MSG_ID)
    print(f"intro post {INTRO_MSG_ID} exists: {bool(intro)}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
