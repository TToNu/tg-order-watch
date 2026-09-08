"""Offline tests for the auto-reply decision logic (no network)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor import autoreply_decision  # noqa: E402

AUTO = {
    "enabled": True,
    "strong_keywords": ["нужен парсер", "кто сделает", "нужен бот", "freela"],
    "exclude": ["no rf and rb", "no rf", "не рф", "без рф"],
}

CASES = [
    # (text, is_bot, is_broadcast, expected_reason)
    ("Нужен парсер товаров с сайта, кто сделает и почём?", False, False, None),
    ("Нужен бот для рассылки уведомлений", False, False, None),
    ("Freela phyton para desenvolver uma API", False, False, None),
    ("No RF and RB. Looking for python dev", False, False, "excluded"),
    ("Работа только для Европы, без РФ. Нужен парсер", False, False, "excluded"),
    ("Статья: как устроен парсинг на python", False, False, "no strong keyword"),
    ("Вакансия: Нужен парсер данных в штат", True, False, "sender is bot"),
    ("Нужен парсер товаров (пост в канал)", False, True, "broadcast channel (replies not possible)"),
    ("Нужен парсер", False, False, None),
]

failures = 0
for text, bot, bc, expected in CASES:
    got = autoreply_decision(text, bot, bc, AUTO)
    ok = got == expected
    failures += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} got={got!r:<45} text={text[:45]}")

# disabled switch
off = dict(AUTO, enabled=False)
r = autoreply_decision("Нужен парсер", False, False, off)
print(f"{'ok  ' if r == 'disabled' else 'FAIL'} got={r!r} (disabled switch)")

sys.exit(1 if failures else 0)
