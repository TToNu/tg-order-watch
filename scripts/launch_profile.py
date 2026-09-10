"""Launch the Dolphin profile browser manually with a CDP debug port.

Dolphin Anty's own API start refuses automation on the free plan, but the
profile browser is a regular executable: we replay the exact argument set
Dolphin uses (fingerprint stays identical) and add --remote-debugging-port,
plus swap the proxy to the one from config.

Usage: python launch_profile.py [--proxy socks5://user:pass@host:port] [--port 9223]
"""

import base64
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BROWSER = (r"C:\Users\alexa\AppData\Roaming\dolphin_anty\browser"
           r"\1423-mini_installer\anty.exe")
PROFILE_DIR = (r"C:\Users\alexa\AppData\Roaming\dolphin_anty\browser_profiles"
               r"\802982781\data_dir")
SHARED_DIR = r"C:\Users\alexa\AppData\Roaming\dolphin_anty\chromium_components"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def dolphin_proxy_arg(proxy_url: str) -> str:
    """Dolphin's patched Chromium expects socks5://<b64 user:pass>:base64@host:port."""
    scheme, rest = proxy_url.split("://", 1)
    creds, _, hostport = rest.rpartition("@")
    b64 = base64.b64encode(creds.encode()).decode()
    return f"{scheme}://{b64}:base64@{hostport}"


def main() -> None:
    args = sys.argv[1:]
    proxy = None
    port = 9223
    if "--proxy" in args:
        proxy = args[args.index("--proxy") + 1]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    cmd = [
        BROWSER,
        f"--user-data-dir={PROFILE_DIR}",
        f"--dolphin-shared-dir={SHARED_DIR}",
        "--enable-features=enable-tls13-early-data",
        f"--down-port={free_port()}",
        "--locale=en-US",
        f"--user-agent={UA}",
        "--enable-unsafe-webgpu",
        "--new-extensions",
        "--no-first-run",
        f"--remote-debugging-port={port}",
        f"--proxy-bypass-list=*anty-api.com; https://dolphin-anty-mirror3.com",
    ]
    if proxy:
        cmd.append(f"--proxy-server={dolphin_proxy_arg(proxy)}")
    else:
        # keep the profile's original US-Texas mobile proxy
        cmd.append("--proxy-server=socks5://"
                   "YnB1c2VyLUJoMVJHYjNYOjJaRXdoZFhPREdzUmVobGR0WUN6X2NvdW50cnktVVNfcmVnaW9uLXRleGFz"
                   ":base64@mobile-x.bpproxy.at:3002")

    subprocess.Popen(cmd, close_fds=True,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)

    for _ in range(30):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                        timeout=3) as r:
                print(json.loads(r.read().decode())["Browser"])
                print(f"CDP ready: http://127.0.0.1:{port}")
                return
        except Exception:
            pass
    sys.exit(f"CDP on port {port} did not come up in 30s")


if __name__ == "__main__":
    main()
