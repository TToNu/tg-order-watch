"""Post the intro message (promo-kit §4) into the three order chats.

One post per chat, human-paced delays. Run once — re-running would duplicate.
"""

import asyncio
import json
import random
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

# python_vacancy is pending admin approval of the join request — add it later.
CHATS = ["django_jobs", "python_django_work"]

INTRO = """Всем привет! Python/C-разработчик, делаю утилиты, парсеры,
ботов и автоматизацию рутинных процессов.

Недавно выложил открытый проект — sysmon, мониторинг системы
для терминала (живой дашборд + JSON-логи для Grafana):
github.com/TToNu/sysmon — буду рад критике и звёздам.

Если есть задача на скрипт или бота — пишите в личку,
обсудим."""


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
    await client.start(phone=lambda: (_ for _ in ()).throw(RuntimeError(
        "session not authorized — run monitor.py once to log in")))

    for name in CHATS:
        ent = await client.get_entity(name)
        msg = await client.send_message(ent, INTRO)
        print(f"posted in {name} (message id {msg.id})")
        await asyncio.sleep(random.uniform(8, 15))

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
