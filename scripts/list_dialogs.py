"""Dump all dialogs (chats/channels/groups) with dev-relevance flags."""

import asyncio
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

DEV_WORDS = [
    "python", "django", "flask", "программ", "разработ", "dev",
    "код", "code", "скрипт", "парсинг", "автоматиз", "it ",
    "айти", "фриланс", "freelance", "бот", "java", "c++", "sql",
    "data", "верст", "web", "ваканс", "работ", "удалён", "удален",
    "remote", "job", "career", "карьер",
]


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

    rows = []
    async for d in client.iter_dialogs():
        if d.is_user:
            continue
        ent = d.entity
        kind = "channel" if getattr(ent, "broadcast", False) else "chat"
        uname = getattr(ent, "username", None) or ""
        title = (d.name or "").strip()
        low = title.lower()
        dev = any(w in low for w in DEV_WORDS)
        rows.append({
            "kind": kind,
            "archived": d.archived,
            "dev": dev,
            "title": title,
            "username": uname,
            "id": d.id,
            "last": d.date.isoformat() if d.date else None,
        })

    out = Path(__file__).with_name("dialogs.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    dev_rows = [r for r in rows if r["dev"]]
    print(f"total chats/channels: {len(rows)}; dev-related: {len(dev_rows)}")
    for r in sorted(dev_rows, key=lambda x: x["last"] or "", reverse=True):
        print(f"[{r['kind']:<7}] last={r['last']:<20} @{r['username']:<25} {r['title'][:60]}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
