"""Pick the fastest reachable MTProto proxy from mtproto.json."""

from __future__ import annotations

import asyncio
import json
import socket
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TIMEOUT = 6.0


def main() -> None:
    proxies = json.loads((HERE / "mtproto.json").read_text(encoding="utf-8"))
    print(f"testing {len(proxies)} MTProto proxies ...")

    scored: list[tuple[float, str, int, str]] = []
    for p in proxies:
        host, port = p["server"], int(p["port"])
        try:
            ip = socket.gethostbyname(host)
        except OSError:
            continue
        t0 = time.monotonic()
        try:
            with socket.create_connection((ip, port), timeout=TIMEOUT):
                scored.append((time.monotonic() - t0, host, port, p["secret"]))
        except OSError:
            continue

    scored.sort()
    print(f"reachable: {len(scored)}")
    for dt, host, port, secret in scored[:10]:
        print(f"  {host}:{port}  {dt * 1000:5.0f} ms  {secret[:16]}…")

    if scored:
        best = scored[0]
        (HERE / "best_proxy.json").write_text(
            json.dumps(
                {"host": best[1], "port": best[2], "secret": best[3], "latency_s": round(best[0], 3)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("\nwrote best_proxy.json ->", best[1], best[2])


if __name__ == "__main__":
    main()
