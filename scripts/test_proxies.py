"""Test public SOCKS5 proxies for reachability of Telegram DCs.

Reads socks5.txt (host:port per line), tries each in parallel, prints the ones
that can open a TCP connection to a Telegram datacenter, fastest first.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import python_socks

DCS = [
    ("149.154.167.51", 443),  # DC2
    ("149.154.175.53", 443),  # DC1
    ("91.108.56.130", 443),   # DC5
]
LIST = Path(__file__).resolve().parent.parent / "socks5.txt"
TIMEOUT = 8.0


async def test_proxy(host: str, port: int) -> tuple[str, float] | None:
    for dc_host, dc_port in DCS:
        t0 = time.monotonic()
        try:
            conn = await python_socks.async_.asyncio.Proxy.from_url(
                f"socks5://{host}:{port}"
            ).connect(dest_host=dc_host, dest_port=dc_port, timeout=TIMEOUT)
            dt = time.monotonic() - t0
            conn.close()
            return f"{host}:{port}", dt
        except Exception:
            continue
    return None


async def main() -> None:
    entries = [ln.strip() for ln in LIST.read_text().splitlines() if ln.strip()]
    print(f"testing {len(entries)} proxies ...")
    results = await asyncio.gather(
        *(test_proxy(*e.split(":")) for e in entries)
    )
    ok = sorted((r for r in results if r), key=lambda r: r[1])
    print(f"\nworking: {len(ok)} of {len(entries)}")
    for addr, dt in ok[:15]:
        print(f"  {addr:<24} {dt * 1000:5.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
