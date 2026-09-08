"""Send one message as the user — used by the scheduled assistant for
activity-chat answers.

Usage:
    python say.py <chat> <reply_to_msg_id|-> <@textfile|text>

Appends a kind="answer" record to sent.log and enforces the daily answer
limit from config "activity.daily_answer_limit" (default 3), so even a buggy
schedule cannot turn into a spam burst.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, utils
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
SENT_LOG = BASE / "sent.log"


def answers_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    n = 0
    if SENT_LOG.exists():
        for ln in SENT_LOG.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            if rec.get("kind") == "answer" and str(rec.get("ts", "")).startswith(today):
                n += 1
    return n


async def main() -> None:
    if len(sys.argv) < 4:
        sys.exit("usage: say.py <chat> <reply_to_msg_id|-> <@textfile|text>")
    chat, reply_to, text_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    text = (
        Path(text_arg[1:]).read_text(encoding="utf-8")
        if text_arg.startswith("@")
        else text_arg
    )

    limit = int(CFG.get("activity", {}).get("daily_answer_limit", 3))
    if answers_today() >= limit:
        sys.exit(f"daily answer limit reached ({limit}) — not sending")

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
    await client.start(phone=lambda: (_ for _ in ()).throw(RuntimeError(
        "session not authorized — run monitor.py once to log in")))

    rt = int(reply_to) if reply_to not in ("-", "0") else None
    msg = await client.send_message(chat, text, reply_to=rt)
    ent = await client.get_entity(chat)
    link = msg_link(utils.get_peer_id(ent), msg.id,
                    {utils.get_peer_id(ent): getattr(ent, "username", "")})

    with SENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {
                "kind": "answer",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "chat": getattr(ent, "title", None) or chat,
                "link": link,
                "sent": text,
            },
            ensure_ascii=False,
        ) + "\n")
    print(f"sent: chat={chat} reply_to={rt} msg_id={msg.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
