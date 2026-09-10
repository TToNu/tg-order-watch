"""Hourly health check for the whole lzt/tg stack. Fixes what it can.

Checks:
  1. monitor (telegram) and flipper (lzt) processes alive -> restart
     via their keepalive supervisors if missing
  2. notification channel: silent probe (empty command through cmds.json)
  3. market API reachable + balance
  4. flipper liveness by its log freshness
Prints PASS/FAIL/ACTION lines for the hourly report.
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"


def run_ps(query: str) -> str:
    return subprocess.run(
        ["powershell", "-Command", query],
        capture_output=True, text=True, timeout=30).stdout


def python_procs() -> list[str]:
    out = run_ps(
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "ForEach-Object { $_.CommandLine }")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def start_window(title: str, script: str) -> None:
    subprocess.run(
        ["cmd", "/c", f'start "{title}" cmd /c "{SCRIPTS / script}"'],
        shell=True, cwd=str(BASE), timeout=15)


def kill_pattern(pattern: str) -> int:
    out = run_ps(
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{pattern}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "
        "Write-Output $_.ProcessId }")
    return len([ln for ln in out.splitlines() if ln.strip().isdigit()])


def check_channel() -> tuple[bool, str]:
    """Silent probe: empty command must be consumed with a result."""
    cmds = BASE / "cmds.json"
    res = BASE / "cmds.result.json"
    if cmds.exists():
        age = time.time() - cmds.stat().st_mtime
        if age > 120:
            return False, f"cmds.json stuck {age:.0f}s (monitor zombie?)"
        return False, "cmds.json busy right now"
    cmds.write_text(json.dumps({"join": [], "send": []}), encoding="utf-8")
    deadline = time.time() + 40
    while time.time() < deadline:
        if res.exists():
            res.unlink()
            return True, "consumed"
        time.sleep(1)
    return False, "no result in 40s"


def main() -> None:
    report: list[str] = []
    procs = python_procs()
    monitor_up = any("monitor.py" in p for p in procs)
    flipper_up = any("lzt_flip_loop" in p for p in procs)

    if monitor_up:
        report.append("PASS monitor process")
    else:
        start_window("tg-order-watch", "monitor_keepalive.cmd")
        report.append("ACTION monitor restarted (was dead)")
        time.sleep(20)
        procs = python_procs()
        monitor_up = any("monitor.py" in p for p in procs)
        report.append("PASS monitor after restart" if monitor_up
                      else "FAIL monitor did not start")

    if flipper_up:
        report.append("PASS flipper process")
    else:
        start_window("lzt-flip", "flipper_keepalive.cmd")
        report.append("ACTION flipper restarted (was dead)")
        time.sleep(15)
        procs = python_procs()
        report.append("PASS flipper after restart"
                      if any("lzt_flip_loop" in p for p in procs)
                      else "FAIL flipper did not start")

    ok, info = check_channel()
    if ok:
        report.append("PASS notify channel")
    else:
        report.append(f"ACTION notify channel broken ({info}) -> "
                      "monitor restart")
        kill_pattern("monitor.py")
        time.sleep(12)
        start_window("tg-order-watch", "monitor_keepalive.cmd")
        time.sleep(25)
        ok2, info2 = check_channel()
        report.append("PASS notify after restart" if ok2
                      else f"FAIL notify still broken: {info2}")

    # market API + balance
    try:
        r = subprocess.run(
            ["python", str(SCRIPTS / "lzt.py"), "me"],
            capture_output=True, text=True, timeout=120, cwd=str(SCRIPTS))
        bal = ""
        for ln in (r.stdout or "").splitlines():
            if "balance" in ln.lower():
                bal = ln.strip()
        report.append(f"PASS market api ({bal})" if bal
                      else f"WARN market api output: "
                           f"{(r.stdout or r.stderr)[:120]}")
    except Exception as e:  # noqa: BLE001
        report.append(f"WARN market api: {type(e).__name__}: {e}")

    # flipper freshness
    logf = BASE / "flip_run.log"
    if logf.exists():
        age_min = (time.time() - logf.stat().st_mtime) / 60
        if age_min > 15:
            report.append(f"ACTION flipper log stale {age_min:.0f} min -> "
                          "restart")
            kill_pattern("lzt_flip_loop")
            time.sleep(10)
            start_window("lzt-flip", "flipper_keepalive.cmd")
        else:
            report.append(f"PASS flipper fresh ({age_min:.0f} min ago)")

    # listings summary
    try:
        st = json.loads((BASE / ".flip_state.json").read_text(encoding="utf-8"))
        report.append(
            f"INFO listings={len(st.get('my_listings', []))} "
            f"pending_relists={len(st.get('pending_relists', []))} "
            f"pending_discounts={len(st.get('pending_discounts', []))} "
            f"spent={st.get('spent', 0):.0f} earned={st.get('earned', 0):.0f}")
    except Exception:  # noqa: BLE001
        report.append("INFO no flip state yet")

    stamp = datetime.now().strftime("%d.%m %H:%M")
    print(f"=== health {stamp} ===")
    for ln in report:
        print(ln)
    fails = [ln for ln in report if ln.startswith("FAIL")]
    print("RESULT:", "FAIL" if fails else "OK")


if __name__ == "__main__":
    main()
