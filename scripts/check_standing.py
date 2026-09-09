"""Inspect our standing in python_django_work + recent context + django_jobs intro."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.tl.functions.channels import GetParticipantRequest

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))


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
    me = await client.get_me()

    for chat_name in ["python_django_work", "django_jobs"]:
        ent = await client.get_entity(chat_name)
        try:
            res = await client(GetParticipantRequest(ent, me))
            part = res.participant
            ptype = type(part).__name__
            banned = getattr(getattr(part, "banned_rights", None), "send_messages", None)
            until = getattr(part, "until_date", None)
            print(f"{chat_name}: member, type={ptype}, muted(send_messages)={banned}, until={until}")
        except Exception as e:
            print(f"{chat_name}: NOT a member or check failed: {type(e).__name__}: {e}")

    # recent context in python_django_work
    print("\n--- last 8 messages in python_django_work ---")
    async for m in client.iter_messages("python_django_work", limit=8):
        who = getattr(getattr(m, "sender", None), "username", None) or "?"
        ts = m.date.astimezone().strftime("%d.%m %H:%M") if m.date else "?"
        print(f"[{ts}] @{who} (id={m.id}): {(m.raw_text or '<media>')[:100]}")

    intro = await client.get_messages("django_jobs", ids=74550)
    print(f"\ndjango_jobs intro 74550 exists: {bool(intro)}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
