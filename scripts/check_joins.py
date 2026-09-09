"""Check join/subscribe status for the foreign chats and join if needed.

Uses the same session + MTProto proxy as monitor.py, so no new login.
"""

import asyncio
import json
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_snapshot import snapshot  # noqa: E402

# Work on a copy of the session: the long-running monitor keeps the sqlite
# session locked, while the auth key in the copy is all we need.
SESSION = snapshot()

CHATS = sys.argv[1:] or ["remotejobss", "itfreelancers", "vagaumdev"]


async def main() -> None:
    proxy = CFG.get("proxy")
    conn = None
    proxy_arg = None
    if proxy and proxy.get("proto") == "mtproto":
        conn = ConnectionTcpMTProxyRandomizedIntermediate
        proxy_arg = (proxy["host"], int(proxy["port"]), proxy["secret"])
    client = TelegramClient(
        str(SESSION), CFG["api_id"], CFG["api_hash"],
        connection=conn, proxy=proxy_arg,
    )
    # Session is already authorized, but Telethon v1.44 requires a phone arg
    # anyway; the callable is only invoked for a fresh (unauthorized) session.
    await client.start(phone=lambda: (_ for _ in ()).throw(RuntimeError(
        "session not authorized — run monitor.py once to log in")))

    for name in CHATS:
        ent = await client.get_entity(name)
        me = await client.get_me()
        joined = False
        try:
            joined = await client.get_permissions(ent, me) is not None
        except Exception:
            joined = False
        if joined:
            print(f"{name}: ALREADY JOINED (id={ent.id})")
            continue
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            await client(JoinChannelRequest(ent))
            print(f"{name}: JOINED NOW (id={ent.id})")
        except Exception as e:
            print(f"{name}: FAILED: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
