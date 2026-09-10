"""ClipProxy manager: auto-rotate proxy countries when the current one dies.

API: http://10.6.7.1:1998/api?country=X&start=N&num=1
Returns: 10.6.7.1:N (an HTTP proxy port)

Updates:
  - scripts/lzt_proxy.json   (market API transport)
  - config.json → proxy       (Telegram monitor)

Usage:
    python proxy_manager.py status     # show current proxy, test it
    python proxy_manager.py rotate     # find a working country and switch
    python proxy_manager.py test US    # test specific country
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
API_URL = "http://192.168.56.1:1998/api"
LZT_PROXY = HERE / "lzt_proxy.json"
CONFIG = BASE / "config.json"

# Countries to try in order (Western = best for Epic/Telegram trust)
COUNTRIES = ["US", "DE", "NL", "GB", "FR", "CA", "AU", "JP"]
PORT_START = 40000


def api_get_proxy(country: str, port_offset: int = 0) -> str | None:
    """Request a proxy from the ClipProxy API."""
    url = (f"{API_URL}?country={country}&state=&city=&postal=&isp="
           f"&start={PORT_START + port_offset}&num=1&ip=")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            addr = r.read().decode().strip()
            return addr if ":" in addr else None
    except Exception:
        return None


def test_proxy(addr: str) -> bool:
    """Quick liveness check: fetch ipify through the proxy."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "8", "-x", f"http://{addr}",
             "https://api.ipify.org"],
            capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and len(result.stdout.strip()) > 5
    except Exception:
        return False


def update_configs(addr: str) -> None:
    """Write the proxy address into both config files."""
    host, _, port = addr.partition(":")
    # lzt market transport
    LZT_PROXY.write_text(
        json.dumps({"url": f"http://{addr}"}), encoding="utf-8")
    # telegram monitor
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["proxy"] = {"proto": "http", "host": host, "port": int(port)}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"[proxy] configs updated -> http://{addr}")


def current_proxy() -> str | None:
    if LZT_PROXY.exists():
        url = json.loads(LZT_PROXY.read_text(encoding="utf-8")).get("url", "")
        return url.replace("http://", "") if url else None
    return None


def find_working(start_idx: int = 0) -> str | None:
    """Try countries in order, return first working proxy address."""
    for i, country in enumerate(COUNTRIES):
        offset = (start_idx + i) % len(COUNTRIES)
        addr = api_get_proxy(country, offset)
        if not addr:
            print(f"[proxy] {country}: API returned nothing")
            continue
        print(f"[proxy] {country} -> {addr}, testing...", end=" ", flush=True)
        if test_proxy(addr):
            print("ALIVE")
            return addr
        print("dead")
    return None


def cmd_status() -> None:
    addr = current_proxy()
    if not addr:
        print("[proxy] no proxy configured")
        return
    alive = test_proxy(addr)
    print(f"[proxy] current: {addr} ({'ALIVE' if alive else 'DEAD'})")
    if not alive:
        print("[proxy] run 'rotate' to find a working one")


def cmd_rotate() -> None:
    print("[proxy] rotating...")
    addr = find_working()
    if addr:
        update_configs(addr)
        print(f"[proxy] switched to {addr}")
        # restart monitor supervisor
        subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*monitor.py*' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            timeout=15)
        import time
        time.sleep(3)
        subprocess.run(
            ["powershell", "-Command",
             "Start-Process -FilePath 'cmd' -ArgumentList '/c',"
             f"'{BASE / 'scripts' / 'monitor_keepalive.cmd'}' "
             "-WindowStyle Minimized"],
            timeout=15)
        print("[proxy] monitor restarted")
    else:
        print("[proxy] ALL countries dead — ClipProxy host unreachable?")


def cmd_test(country: str) -> None:
    addr = api_get_proxy(country)
    if addr:
        alive = test_proxy(addr)
        print(f"[proxy] {country} -> {addr}: {'ALIVE' if alive else 'DEAD'}")
    else:
        print(f"[proxy] {country}: API unreachable")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        cmd_status()
    elif cmd == "rotate":
        cmd_rotate()
    elif cmd == "test" and len(sys.argv) > 2:
        cmd_test(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
