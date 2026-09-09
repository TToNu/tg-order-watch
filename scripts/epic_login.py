"""Log into epicgames.com over HTTP with the bought account credentials and
export session cookies in the format lzt.market fast-sell expects.

Usage: python epic_login.py <email> <password>
Writes cookies to epic_cookies.txt (name=value; ... header style).
"""

import json
import re
import sys
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
OUT = Path(__file__).with_name("epic_cookies.txt")


def main() -> None:
    item = json.loads((Path(__file__).with_name("bought_item.json"))
                      .read_text(encoding="utf-8"))
    raw = (item.get("loginData") or {}).get("raw") or ""
    email, _, password = raw.partition(":")
    if not password:
        sys.exit("no credentials in bought_item.json")
    s = requests.Session()
    s.headers["User-Agent"] = UA

    r = s.get("https://www.epicgames.com/id/login", timeout=40)
    print(f"login page: {r.status_code}, cookies: {list(s.cookies.keys())}")
    r0 = s.get("https://www.epicgames.com/id/api/csrf", timeout=40)
    print(f"csrf api: {r0.status_code} {r0.text[:120]}")
    xsrf = None
    try:
        xsrf = r0.json().get("csrfToken")
    except ValueError:
        pass
    xsrf = xsrf or s.cookies.get("XSRF-TOKEN") or s.cookies.get("csrf")
    if xsrf:
        s.headers["x-xsrf-token"] = xsrf
        s.headers["x-csrf-token"] = xsrf

    r = s.post("https://www.epicgames.com/id/api/login",
               json={"email": email, "password": password,
                     "rememberMe": False},
               headers={"Content-Type": "application/json"}, timeout=40)
    print(f"login api: {r.status_code} body[:200]: {r.text[:200]}")
    if r.status_code != 200:
        sys.exit("login failed")

    # session confirmation
    r2 = s.get("https://www.epicgames.com/id/api/authenticate", timeout=40)
    print(f"authenticate: {r2.status_code} {r2.text[:120]}")

    cookies = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
    OUT.write_text(cookies, encoding="utf-8")
    print(f"cookies ({len(s.cookies)}) saved -> {OUT.name}")
    print("names:", [c.name for c in s.cookies])


if __name__ == "__main__":
    main()
