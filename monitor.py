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
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events, utils

CONFIG_PATH = Path(__file__).with_name("config.json")
ORDERS_LOG = Path(__file__).with_name("orders.log")
QUESTIONS_LOG = Path(__file__).with_name("questions.log")
SENT_LOG = Path(__file__).with_name("sent.log")
AUTO_STATE = Path(__file__).with_name("auto_state.json")
CMDS_PATH = Path(__file__).with_name("cmds.json")
CMDS_RESULT = Path(__file__).with_name("cmds.result.json")

# Auto-reply text variants (rotation keeps messages from looking copy-pasted,
# which is what Telegram's spam heuristics and chat admins look for).
AUTO_TEMPLATES_RU = [
    "{handle}, здравствуйте! Возьму эту задачу ({quote}). "
    "Python — скрипты, боты, парсинг, автоматизация. "
    "Напишите мне в личку: пришлю план и вилку цены, отвечаю быстро.",
    "{handle}, добрый день! По вашей задаче есть релевантный опыт, "
    "открытый код: github.com/TToNu/sysmon. "
    "Пару уточняющих вопросов в личке — и назову сроки и цену, удобно?",
    "{handle}, готов взяться ({quote}). "
    "Python-разработчик: утилиты, парсеры, телеграм-боты, автоматизация. "
    "Детали — в личку, отвечаю в течение получаса.",
]

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


def msg_link(chat_id: int, msg_id: int, usernames: dict[int, str]) -> str:
    username = usernames.get(chat_id)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    inner = str(chat_id)
    inner = inner[4:] if inner.startswith("-100") else inner.lstrip("-")
    return f"https://t.me/c/{inner}/{msg_id}"


def autoreply_decision(
    text: str, is_bot: bool, is_broadcast: bool, auto: dict
) -> str | None:
    """Return a skip reason when auto-reply must not fire, else None."""
    if not auto.get("enabled"):
        return "disabled"
    low = (text or "").lower()
    if not low:
        return "empty text"
    if is_bot:
        return "sender is bot"
    if is_broadcast:
        return "broadcast channel (replies not possible)"
    if any(b in low for b in auto.get("exclude", [])):
        return "excluded"
    if not any(k in low for k in auto.get("strong_keywords", [])):
        return "no strong keyword"
    return None


def load_auto_state() -> dict:
    try:
        return json.loads(AUTO_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"day": "", "sent": 0, "chats": {}}


def save_auto_state(state: dict) -> None:
    AUTO_STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


async def process_command_file(client: TelegramClient) -> None:
    """Execute cmds.json (written by helper scripts) on the live connection.

    Protocol: writer waits until cmds.json is absent, writes it, then polls
    cmds.result.json. We clear stale results, run the commands, write results
    and remove cmds.json.
    """
    if not CMDS_PATH.exists():
        return
    try:
        cmds = json.loads(CMDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("cmds.json unreadable: %s", e)
        CMDS_PATH.rename(CMDS_PATH.with_name("cmds.bad.json"))
        return
    CMDS_RESULT.unlink(missing_ok=True)

    from telethon.tl.functions.channels import JoinChannelRequest
    result: dict = {"join": [], "send": []}
    for name in cmds.get("join", []):
        entry = {"chat": name, "ok": False, "error": None}
        try:
            ent = await client.get_entity(name)
            await client(JoinChannelRequest(ent))
            entry["ok"] = True
            log.info("cmd: joined %s", name)
        except Exception as e:  # noqa: BLE001
            entry["error"] = str(e)
            log.warning("cmd: join %s failed: %s", name, e)
        result["join"].append(entry)

    for item in cmds.get("send", []):
        entry = {"chat": item.get("chat"), "ok": False, "msg_id": None, "error": None}
        try:
            rt = item.get("reply_to") or None
            msg = await client.send_message(item["chat"], item["text"], reply_to=rt)
            entry.update(ok=True, msg_id=msg.id)
            log.info("cmd: sent to %s (reply_to=%s)", item["chat"], rt)
        except Exception as e:  # noqa: BLE001
            entry["error"] = str(e)
            log.warning("cmd: send to %s failed: %s", item.get("chat"), e)
        result["send"].append(entry)

    CMDS_RESULT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    CMDS_PATH.unlink()


async def command_loop(client: TelegramClient) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            await process_command_file(client)
        except Exception as e:  # noqa: BLE001 - never kill the loop
            log.warning("command loop error: %s", e)


def ask_phone() -> str:
    """Ask for the phone and normalize to international +<digits> format."""
    raw = input("Введите номер телефона (например +79133075862): ").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:  # typed without a country code (RU default)
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):  # 8-xxx Russian style
        digits = "7" + digits[1:]
    return f"+{digits}"


async def run(cfg: dict, once: bool) -> None:
    session_path = Path(__file__).with_name("session")
    proxy = cfg.get("proxy")
    proxy_arg = None
    connection = None
    if proxy and proxy.get("proto") == "mtproto":
        # MTProto proxy tunnels the whole Telegram traffic through the proxy
        # host; ISP-level blocks of Telegram DC IPs stop mattering.
        from telethon.network.connection import ConnectionTcpMTProxyRandomizedIntermediate

        connection = ConnectionTcpMTProxyRandomizedIntermediate
        proxy_arg = (proxy["host"], int(proxy["port"]), proxy["secret"])
    elif proxy:
        # Plain SOCKS5/HTTP proxy (requires python-socks).
        proxy_arg = (proxy.get("type", "socks5"), proxy["host"], int(proxy["port"]))

    client = TelegramClient(
        str(session_path),
        cfg["api_id"],
        cfg["api_hash"],
        connection=connection,
        proxy=proxy_arg,
    )
    # Pin a specific DC for fresh sessions when no proxy is configured.
    dc = cfg.get("dc")
    if dc and not proxy and not session_path.with_suffix(".session").exists():
        client.session.set_dc(dc["id"], dc["ip"], dc.get("port", 443))
    # Empty "phone" in config -> ask in the console on first run and accept
    # both +7... and bare 10-digit input; the login code is asked the same way.
    phone = cfg.get("phone") or ask_phone
    await client.start(phone=phone)
    me = await client.get_me()
    log.info("logged in as %s", me.first_name)

    matches = build_matcher(cfg["keywords"])

    # Resolve chat identifiers (usernames, t.me links, or numeric ids) once.
    # Key by the marked id (e.g. -100…) — that is what event.chat_id carries.
    targets: dict[int, str] = {}
    usernames: dict[int, str] = {}
    for ref in cfg["chats"]:
        try:
            ent = await client.get_entity(ref)
            marked = utils.get_peer_id(ent)
            targets[marked] = getattr(ent, "title", None) or getattr(ent, "username", str(ref))
            if getattr(ent, "username", None):
                usernames[marked] = ent.username
        except Exception as e:  # noqa: BLE001 - keep other chats working
            log.warning("cannot resolve %s: %s", ref, e)
    if not targets:
        sys.exit("no monitored chats resolved — check the 'chats' list in config.json")
    log.info("monitoring %d chats: %s", len(targets), ", ".join(targets.values()))

    # Activity chats: same watcher, but questions go to questions.log for the
    # scheduled assistant to answer — this builds presence without spam.
    act = cfg.get("activity", {})
    act_targets: dict[int, str] = {}
    for ref in act.get("chats", []):
        try:
            ent = await client.get_entity(ref)
            marked = utils.get_peer_id(ent)
            act_targets[marked] = getattr(ent, "title", None) or str(ref)
            if getattr(ent, "username", None):
                usernames[marked] = ent.username
        except Exception as e:  # noqa: BLE001
            log.warning("cannot resolve activity chat %s: %s", ref, e)
    act_matches = build_matcher(act.get("keywords", []))
    log.info("activity chats (%d): %s", len(act_targets), ", ".join(act_targets.values()))

    watch_ids = list(targets) + [c for c in act_targets if c not in targets]

    @client.on(events.NewMessage(chats=watch_ids))
    async def on_message(event: events.NewMessage.Event) -> None:
        if event.out:
            return

        # Anti-spam captchas (MissRose etc.): press the button before it
        # times out, otherwise the account gets muted/kicked from the chat.
        low = (event.raw_text or "").lower()
        sender = await event.get_sender()
        if (
            getattr(sender, "bot", False)
            and event.buttons
            and ("нажмите кнопку" in low or "не бот" in low or "prove" in low)
        ):
            try:
                await event.buttons[0][0].click()
                log.info("captcha button clicked in %s",
                         targets.get(event.chat_id) or act_targets.get(event.chat_id))
            except Exception as e:  # noqa: BLE001
                log.warning("captcha click failed: %s", e)
            return

        if not matches(event.raw_text):
            if event.chat_id in act_targets and act_matches(event.raw_text):
                sender = await event.get_sender()
                who = getattr(sender, "username", None) or getattr(sender, "first_name", "?")
                if getattr(sender, "bot", False):
                    return
                record = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "chat": act_targets[event.chat_id],
                    "who": str(who),
                    "link": msg_link(event.chat_id, event.id, usernames),
                    "text": event.raw_text or "",
                }
                with QUESTIONS_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.info("question in %s from @%s", act_targets[event.chat_id], who)
            return
        title = targets.get(event.chat_id, str(event.chat_id))
        sender = await event.get_sender()
        who = getattr(sender, "username", None) or getattr(sender, "first_name", "?")
        stamp = datetime.now().strftime("%H:%M:%S")
        log.info("[%s] match in %s from @%s", stamp, title, who)

        link = msg_link(event.chat_id, event.id, usernames)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "chat": title,
            "who": str(who),
            "link": link,
            "text": event.raw_text or "",
        }
        with ORDERS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        await client.send_message(
            "me",
            f"🔥 Заказ? [{title}] @{who} {stamp}\n\n{snippet(event.raw_text)}",
        )

        # --- auto-reply (group chats only, conservative anti-ban limits) ---
        auto = cfg.get("auto_reply", {})
        is_bot = getattr(sender, "bot", False)
        is_broadcast = event.is_channel and not event.is_group
        reason = autoreply_decision(event.raw_text, is_bot, is_broadcast, auto)
        if reason:
            log.info("auto-reply skipped: %s", reason)
            return

        st = load_auto_state()
        today = datetime.now().strftime("%Y-%m-%d")
        if st.get("day") != today:
            st = {"day": today, "sent": 0, "chats": {}}
        if st["sent"] >= int(auto.get("daily_limit", 8)):
            log.info("auto-reply skipped: daily limit reached")
            return
        cooldown = int(auto.get("chat_cooldown_min", 10)) * 60
        if time.time() - st["chats"].get(str(event.chat_id), 0) < cooldown:
            log.info("auto-reply skipped: chat cooldown")
            return

        quote = " ".join((event.raw_text or "").split())
        quote = (quote[:80] + "…") if len(quote) > 80 else quote
        handle = f"@{who}" if not str(who).startswith("@") else str(who)
        msg = random.choice(AUTO_TEMPLATES_RU).format(handle=handle, quote=f"«{quote}»")
        delay = random.uniform(
            float(auto.get("min_delay_s", 20)), float(auto.get("max_delay_s", 60))
        )
        log.info("auto-reply in %s in ~%.0fs", title, delay)
        await asyncio.sleep(delay)
        try:
            await event.reply(msg)
        except Exception as e:  # noqa: BLE001 - flood waits, muted chats etc.
            log.warning("auto-reply failed: %s", e)
            return
        st["sent"] += 1
        st["chats"][str(event.chat_id)] = time.time()
        save_auto_state(st)
        with SENT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "chat": title,
                    "link": link,
                    "sent": msg,
                },
                ensure_ascii=False,
            ) + "\n")
        await client.send_message("me", f"🤖 Авто-отклик отправлен: [{title}] {link}")

    if once:
        await client.disconnect()
        return

    log.info("watching for keywords: %s", ", ".join(cfg["keywords"]))
    asyncio.create_task(command_loop(client))
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
