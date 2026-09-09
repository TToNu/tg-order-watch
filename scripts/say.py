"""Send one message as the user — used by the scheduled assistant for
activity-chat answers.

Usage:
    python say.py <chat> <reply_to_msg_id|-> <@textfile|text>

Instead of opening a second Telegram connection (which fights the monitor
for the session database), this writes cmds.json and waits for the running
monitor to execute it and answer via cmds.result.json. Enforces the daily
answer limit from config "activity.daily_answer_limit" (default 3).
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
SENT_LOG = BASE / "sent.log"
CMDS_PATH = BASE / "cmds.json"
CMDS_RESULT = BASE / "cmds.result.json"


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


def main() -> int:
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

    # Wait for a free command slot (another helper may be mid-flight).
    deadline = time.time() + 120
    while CMDS_PATH.exists() and time.time() < deadline:
        time.sleep(1)
    if CMDS_PATH.exists():
        sys.exit("cmds.json busy for 120s — monitor not processing commands?")

    CMDS_RESULT.unlink(missing_ok=True)
    CMDS_PATH.write_text(json.dumps(
        {"send": [{"chat": chat, "reply_to": int(reply_to) if reply_to not in ("-", "0") else None, "text": text}]},
        ensure_ascii=False,
    ), encoding="utf-8")

    deadline = time.time() + 120
    while not CMDS_RESULT.exists() and time.time() < deadline:
        time.sleep(1)
    if not CMDS_RESULT.exists():
        sys.exit("monitor did not process cmds.json in 120s")

    result = json.loads(CMDS_RESULT.read_text(encoding="utf-8"))
    CMDS_RESULT.unlink(missing_ok=True)
    entry = (result.get("send") or [{}])[0]
    if not entry.get("ok"):
        sys.exit(f"send failed: {entry.get('error')}")

    with SENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {
                "kind": "answer",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "chat": chat,
                "link": f"{chat}/{entry.get('msg_id')}",
                "sent": text,
            },
            ensure_ascii=False,
        ) + "\n")
    print(f"sent: chat={chat} msg_id={entry.get('msg_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
