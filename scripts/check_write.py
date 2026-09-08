"""Check write permissions in the order chats (dry probe, no posting)."""

import asyncio
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

CHATS = ["python_vacancy", "django_jobs", "python_django_work"]


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
    from telethon.tl.functions.channels import GetParticipantRequest
    from telethon.tl.types import ChannelParticipantBanned

    for name in CHATS:
        ent = await client.get_entity(name)
        full = await client.get_entity(name)
        banned = getattr(full, "restricted", None)
        me = await client.get_me()
        try:
            p = await client(GetParticipantRequest(ent, me))
            part = p.participants[0] if p.participants else None
            print(f"{name}: participant type={type(part).__name__}, "
                  f"banned_until={getattr(part, 'until_date', None)}")
        except Exception as e:
            print(f"{name}: participant check failed: {type(e).__name__}: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
