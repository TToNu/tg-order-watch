"""Launch the anty browser in foreground capture mode to see why it dies."""

import subprocess
import sys

BROWSER = (r"C:\Users\alexa\AppData\Roaming\dolphin_anty\browser"
           r"\1423-mini_installer\anty.exe")
PROFILE_DIR = (r"C:\Users\alexa\AppData\Roaming\dolphin_anty\browser_profiles"
               r"\802982781\data_dir")
SHARED_DIR = r"C:\Users\alexa\AppData\Roaming\dolphin_anty\chromium_components"

cmd = [
    BROWSER,
    f"--user-data-dir={PROFILE_DIR}",
    f"--dolphin-shared-dir={SHARED_DIR}",
    "--enable-features=enable-tls13-early-data",
    "--no-first-run",
    "--remote-debugging-port=9223",
    "--enable-logging=stderr",
    "--v=0",
]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
import time
time.sleep(8)
if p.poll() is not None:
    print(f"EXITED code={p.returncode}")
err = p.stderr.read(4000).decode("utf-8", "replace") if p.stderr else ""
out = p.stdout.read(2000).decode("utf-8", "replace") if p.stdout else ""
print("--- stderr ---")
print(err)
print("--- stdout ---")
print(out)
if p.poll() is None:
    p.kill()
