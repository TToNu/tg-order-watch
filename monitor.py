"""tg-order-watch — Telegram freelance order monitor.

Watches a list of chats/channels and instantly notifies you (in Saved Messages)
when a new message matches configurable keywords: "ищу разработчика", "нужен
скрипт", "кто напишет бота" etc. Being the first to reply is what wins orders
in small chats.

Usage:
    python monitor.py            # run with config.json in the working dir
    python monitor.py --once     # test config + login, print monitored chats, exit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events

CONFIG_PATH = Path(__file__).with_name("config.json")

log = logging.getLogger("tg-order-watch")


def load_config(path: Path) -> dict:
    if not path.exists():
        example = path.with_suffix(".example.json")
        sys.exit(
            f"config.json not found. Copy {example.name} to config.json, "
            "fill in api_id/api_hash and your chat list."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("api_id", "api_hash", "phone", "chats", "keywords"):
        if key not in cfg:
            sys.exit(f"config.json is missing required key: {key}")
    return cfg


def build_matcher(keywords: list[str]):
    """Case-insensitive substring match on any keyword."""
    parts = [re.escape(k.lower()) for k in keywords]
    rx = re.compile("|".join(parts))
    return lambda text: bool(text) and bool(rx.search(text.lower()))


def snippet(text: str, limit: int = 500) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def run(cfg: dict, once: bool) -> None:
    client = TelegramClient(
        str(Path(__file__).with_name("session")),
        cfg["api_id"],
        cfg["api_hash"],
    )
    # Empty "phone" in config -> Telethon asks for it (and the login code)
    # interactively in the console; the account number never touches any file.
    await client.start(phone=cfg.get("phone") or None)
    me = await client.get_me()
    log.info("logged in as %s", me.first_name)

    matches = build_matcher(cfg["keywords"])

    # Resolve chat identifiers (usernames, t.me links, or numeric ids) once.
    targets: dict[int, str] = {}
    for ref in cfg["chats"]:
        try:
            ent = await client.get_entity(ref)
            targets[ent.id] = getattr(ent, "title", None) or getattr(ent, "username", str(ref))
        except Exception as e:  # noqa: BLE001 - keep other chats working
            log.warning("cannot resolve %s: %s", ref, e)
    if not targets:
        sys.exit("no monitored chats resolved — check the 'chats' list in config.json")
    log.info("monitoring %d chats: %s", len(targets), ", ".join(targets.values()))

    @client.on(events.NewMessage(chats=list(targets)))
    async def on_message(event: events.NewMessage.Event) -> None:
        if event.out:
            return
        if not matches(event.raw_text):
            return
        title = targets.get(event.chat_id, str(event.chat_id))
        sender = await event.get_sender()
        who = getattr(sender, "username", None) or getattr(sender, "first_name", "?")
        stamp = datetime.now().strftime("%H:%M:%S")
        log.info("[%s] match in %s from @%s", stamp, title, who)
        await client.send_message(
            "me",
            f"🔥 Заказ? [{title}] @{who} {stamp}\n\n{snippet(event.raw_text)}",
        )

    if once:
        await client.disconnect()
        return

    log.info("watching for keywords: %s", ", ".join(cfg["keywords"]))
    await client.run_until_disconnected()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Telegram freelance order monitor")
    ap.add_argument("--once", action="store_true", help="check config/login and exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config(CONFIG_PATH)
    asyncio.run(run(cfg, args.once))
    return 0


if __name__ == "__main__":
    sys.exit(main())
