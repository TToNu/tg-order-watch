"""Fetch Epic Games 2FA verification code from rambler.ru via IMAP.
Filters out CSS color codes that look like 6-digit numbers."""

import email
import imaplib
import re
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header

# Common CSS/HTML color codes that match \d{6} — NEVER the real code
CSS_COLORS = {
    "000000", "000001", "000080", "008000", "008080", "00ff00",
    "111111", "121212", "1a1a1a", "202020", "222222", "2a2a2a",
    "333333", "333336", "3a3a3a", "404040", "444444", "4a4a4a",
    "555555", "595959", "666666", "6a6a6a", "707070", "777777",
    "7a7a7a", "808080", "888888", "8a8a8a", "909090", "999999",
    "9a9a9a", "a0a0a0", "aaaaaa", "b0b0b0", "bbbbbb", "c0c0c0",
    "cccccc", "d0d0d0", "dddddd", "e0e0e0", "eeeeee", "f0f0f0",
    "ffffff", "ff0000", "00ffff", "0000ff", "ff00ff",
    "101010", "151515", "171717", "1e1e1e", "242424", "2d2d2d",
    "343434", "3d3d3d", "454545", "4d4d4d", "565656", "5e5e5e",
    "676767", "6f6f6f", "787878", "818181", "898989", "929292",
    "9b9b9b", "a3a3a3", "acacac", "b4b4b4", "bdbdbd", "c5c5c5",
    "cecece", "d6d6d6", "dfdfdf", "e7e7e7", "efefef", "f7f7f7",
    "fafafa", "fcfcfc", "fefefe",
}


def extract_real_code(body: str) -> str | None:
    """Extract the actual 2FA code, filtering CSS colors."""
    # Method 1: Look for code near keywords
    # Epic emails typically say "Your code is: 123456" or have
    # the code in a prominent element
    patterns = [
        r'(?:code is|код|enter|введите)[^0-9]{0,20}(\d{6})',
        r'(\d{6})[^0-9]{0,20}(?:code|код)',
        r'font-size:\s*2\d+px[^>]*>[^0-9]*(\d{6})',  # large font element
        r'(\d{6})\s*</(?:div|span|p|h[1-6])>',  # inside HTML element
    ]
    for pattern in patterns:
        matches = re.findall(pattern, body, re.IGNORECASE)
        for m in matches:
            if m not in CSS_COLORS and not m.startswith('00'):
                return m

    # Method 2: All 6-digit numbers, filter known CSS colors
    all_codes = re.findall(r'\b(\d{6})\b', body)
    candidates = [c for c in all_codes
                  if c not in CSS_COLORS
                  and not c.startswith('00')  # 00xxxx = likely color
                  and not all(ch == c[0] for ch in c)  # xxxxxx = color
                  and c[0] != '0']  # 0xxxxx = likely CSS

    if candidates:
        # The real code appears once per email (CSS colors repeat)
        from collections import Counter
        counts = Counter(candidates)
        unique = [c for c, n in counts.items() if n <= 2]
        if unique:
            return unique[-1]  # last unique = most recent

    return None


def get_epic_code(email_addr: str, email_pass: str,
                  wait_seconds: int = 5) -> str | None:
    """Check rambler.ru inbox for a recent Epic Games verification code."""
    time.sleep(min(wait_seconds, 3))

    try:
        imap = imaplib.IMAP4_SSL("imap.rambler.ru", 993)
        imap.login(email_addr, email_pass)
        imap.select("INBOX")

        # Search by SUBJECT (FROM search doesn't match acct-auth domain)
        typ, ids1 = imap.search(None, 'SUBJECT "two-factor"')
        typ, ids2 = imap.search(None, 'SUBJECT "Security Code"')
        all_ids = sorted(set(ids1[0].split() + ids2[0].split()),
                         key=lambda x: int(x))

        if not all_ids:
            # Fallback: recent unseen
            _, ids3 = imap.search(None, 'UNSEEN')
            all_ids = ids3[0].split()

        if not all_ids:
            imap.logout()
            return None

        # Check most recent emails (newest last)
        for msg_id in reversed(all_ids[-3:]):
            _, msg_data = imap.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            # Check date (must be recent)
            msg_date = msg.get("Date", "")
            if msg_date:
                try:
                    parsed = email.utils.parsedate_to_datetime(msg_date)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
                    if parsed < cutoff:
                        continue
                except Exception:
                    pass

            # Extract body
            body = ""
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace")
                    break

            code = extract_real_code(body)
            if code:
                imap.store(msg_id, '+FLAGS', '\\Seen')
                imap.logout()
                return code

        imap.logout()
        return None
    except Exception as e:
        print(f"[imap] error: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    addr = "osipov-ai4p6@rambler.ru"
    pwd = "ffeaCb9BYPVx"
    code = get_epic_code(addr, pwd, wait_seconds=2)
    if code:
        print(f"FOUND CODE: {code}")
    else:
        print("NO CODE")
