"""Fortnite -> EpicGames flip scanner for lzt.market.

Concept (user's scheme): buy cheap Fortnite-section accounts (1-20 RUB) that
own Dead by DayLIGHT (visible in fortniteTransactions / title / description),
then relist in the Epic Games section at the DBD market price.

Usage:
    python lzt_flip.py scan [pages]     # find DBD candidates among cheap lots
    python lzt_flip.py price            # current DBD price level in epicgames
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

DBD_RE = re.compile(r"(dead\s*by\s*day\s*light|\bdbd\b|\bdaylight\b|\bдбд\b)",
                     re.I)

# Resale portfolio: games NEVER given free on the Epic Games Store —
# only those carry transferable value in an Epic ownership record.
# Verified 10.09: Chivalry 2, Disco Elysium, Ghostrunner 2, Genshin,
# Rogue Company were free/F2P → dropped (stale 15-149₽ lots, no churn).
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


def load_seen() -> set:
    if STATE.exists():
        return set(json.loads(STATE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    STATE.write_text(json.dumps(list(seen))[-200000:], encoding="utf-8")


# Only native-Epic-platform accounts carry a standalone Epic login:password
# we can resell in the Epic Games section; console/store-platform accounts
# (Xbox Live, PSN, IOSAppStore, GooglePlay) may log in via platform SSO only.
EPIC_PLATFORMS = {"epic", "epicpc", "epicandroid"}


def detect_game(it: dict) -> tuple[str, str] | None:
    """(game, evidence) for the first portfolio game this lot contains."""
    if (it.get("fortnite_platform") or "").lower() not in EPIC_PLATFORMS:
        return None
    text = " ".join(filter(None, [it.get("title"), it.get("title_en"),
                                  it.get("description"),
                                  it.get("description_en")]))
    for tr in it.get("fortniteTransactions") or []:
        tr_text = " ".join(str(v) for v in tr.values())
        for game, rx in GAME_TARGETS:
            if rx.search(tr_text):
                return game, f"transaction: {tr_text[:80]!r}"
    for game, rx in GAME_TARGETS:
        if rx.search(text):
            return game, f"title/description: {text[:80]!r}"
    return None


def detect_game_generic(obj) -> tuple[str, str] | None:
    """Scan every string in an arbitrary item JSON (epicgames-section lots
    keep owned-game lists in nested fields) for portfolio games."""
    texts: list[str] = []
    hash_like = re.compile(r"^[0-9a-f]{16,}$")

    def walk(node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("loginData", "emailLoginData"):
                    continue  # never regex credentials
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            # game app_ids are md5-like hashes: 'dbd' inside one once caused
            # a false portfolio hit — never scan hash-shaped strings
            if not hash_like.match(node.strip()):
                texts.append(node)

    walk(obj)
    for game, rx in GAME_TARGETS:
        for t in texts:
            m = rx.search(t)
            if m:
                return game, f"field: {t[:80]!r}"
    return None


def item_has_dbd(it: dict) -> str | None:  # kept for compatibility
    hit = detect_game(it)
    if hit and hit[0] == "Dead by Daylight":
        return hit[1]
    return None


def scan(pages: int, pmin: str = "1", pmax: str = "20") -> None:
    seen = load_seen()
    fresh = []
    for page in range(pages):
        params = {"pmin": pmin, "pmax": pmax, "order_by": "price_to_up",
                  "page": str(page + 1)}
        res = api_call("GET", "/fortnite", params)
        items = res.get("items", [])
        if not items:
            break
        for it in items:
            iid = it.get("item_id")
            if iid in seen:
                continue
            seen.add(iid)
            ev = item_has_dbd(it)
            if ev:
                fresh.append((it, ev))
        print(f"page {page + 1}: {len(items)} items, "
              f"hasNextPage={res.get('hasNextPage')}")
        if not res.get("hasNextPage"):
            break
    save_seen(seen)
    print(f"scanned, candidates with DBD mention: {len(fresh)} "
          f"(seen total {len(seen)})")
    for it, ev in fresh:
        print(f"\nhttps://lzt.market/{it['item_id']}/  {it.get('price')}₽  "
              f"seller={it.get('seller', {}).get('username')}")
        print(f"  evidence: {ev}")
        tr_count = len(it.get("fortniteTransactions") or [])
        print(f"  transactions: {tr_count}, "
              f"skins: {it.get('fortnite_skin_count')}, "
              f"vbucks: {it.get('fortnite_balance')}")


def price_level() -> None:
    res = api_call("GET", "/epicgames",
                   {"title": "dead by daylight", "order_by": "price_to_up"})
    items = res.get("items", [])
    print(f"epicgames 'dead by daylight' lots: {res.get('totalItems')}")
    for it in items[:10]:
        print(f"{it.get('item_id')}  {it.get('price')}₽  "
              f"{(it.get('title') or '')[:70]}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        scan(int(sys.argv[2]) if len(sys.argv) > 2 else 5,
             sys.argv[3] if len(sys.argv) > 3 else "1",
             sys.argv[4] if len(sys.argv) > 4 else "20")
    elif cmd == "price":
        price_level()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
