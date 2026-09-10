"""Game detection based ONLY on actual owned games, never text mentions.

For fortnite items: fortniteTransactions where orderType == "PURCHASE"
For epicgames items: eg_games dict values (each has a .title)
NEVER matches against: descriptions, titles, hashes, URLs, raw text.
"""

import re
from pathlib import Path

DBD_RE = re.compile(r"(dead\s*by\s*day\s*light|\bdbd\b|\bdaylight\b|\bдбд\b)",
                     re.I)

GAME_TARGETS = [
    ("GTA V", re.compile(r"grand\s*theft\s*auto|\bgta\s*v\b", re.I)),
    ("Red Dead Redemption 2", re.compile(r"red\s*dead\s*redemption", re.I)),
    ("Cyberpunk 2077", re.compile(r"cyberpunk\s*2077", re.I)),
    ("Dead by Daylight", DBD_RE),
    ("Kerbal Space Program", re.compile(r"kerbal\s*space", re.I)),
    ("EA SPORTS FC 26", re.compile(r"ea\s*sports\s*fc\s*2[56]|\bfc\s*26\b",
                                   re.I)),
]

STATE = Path(__file__).with_name(".flip_seen.json")


def _owned_titles_fortnite(item: dict) -> list[str]:
    """Titles from fortniteTransactions with PURCHASE type only."""
    titles = []
    for tr in item.get("fortniteTransactions") or []:
        if tr.get("orderType") == "PURCHASE" and tr.get("title"):
            titles.append(tr["title"])
    return titles


def _owned_titles_epicgames(item: dict) -> list[str]:
    """Titles from eg_games — the parsed list of games on the account."""
    titles = []
    eg = item.get("eg_games") or {}

    def walk(node):
        if isinstance(node, dict):
            t = node.get("title")
            if isinstance(t, str) and len(t) > 2 and t != "None":
                titles.append(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(eg)
    return titles


def detect_game_fortnite(it: dict) -> tuple[str, str] | None:
    """(game, evidence) — matches ONLY against purchased game titles."""
    platform = (it.get("fortnite_platform") or "").lower()
    if platform not in ("epic", "epicpc", "epicandroid"):
        return None
    for title in _owned_titles_fortnite(it):
        for game, rx in GAME_TARGETS:
            if rx.search(title):
                return game, f"owned: {title!r}"
    return None


def detect_game_epicgames(it: dict) -> tuple[str, str] | None:
    """(game, evidence) — matches ONLY against eg_games titles."""
    for title in _owned_titles_epicgames(it):
        for game, rx in GAME_TARGETS:
            if rx.search(title):
                return game, f"owned: {title!r}"
    return None


# Backward compatibility
detect_game = detect_game_fortnite
detect_game_generic = detect_game_epicgames
