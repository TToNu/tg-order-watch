"""Fetch Epic Games 2FA verification code from rambler.ru via IMAP."""

import imaplib
import email
import re
import sys
import time
from email.header import decode_header
from pathlib import Path


def get_epic_code(email_addr: str, email_pass: str,
                  wait_seconds: int = 10) -> str | None:
    """Check rambler.ru inbox for a recent Epic Games verification code."""
    from datetime import datetime, timedelta, timezone

    time.sleep(min(wait_seconds, 5))

    try:
        imap = imaplib.IMAP4_SSL("imap.rambler.ru", 993)
        imap.login(email_addr, email_pass)
        imap.select("INBOX")

        # Search for recent emails from Epic (last 3 minutes)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        date_str = cutoff.strftime("%d-%b-%Y")
        _, msg_ids = imap.search(None, f'(FROM "epicgames" SINCE {date_str})')
        if not msg_ids[0]:
            _, msg_ids = imap.search(None, f'(SINCE {date_str})')
        if not msg_ids[0]:
            # Last resort: all unseen
            _, msg_ids = imap.search(None, 'UNSEEN')

        ids = msg_ids[0].split()
        if not ids:
            imap.logout()
            return None

        # Check the most recent emails (newest last)
        for msg_id in reversed(ids[-5:]):
            _, msg_data = imap.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            # Check date - skip old emails
            msg_date = msg.get("Date", "")
            if msg_date:
                try:
                    parsed = email.utils.parsedate_to_datetime(msg_date)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed < cutoff:
                        continue  # too old
                except Exception:
                    pass

            # Extract text body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "text/html"):
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(
                            charset, errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode(
                    msg.get_content_charset() or "utf-8", errors="replace")

            # Look for a 6-digit verification code
            codes = re.findall(r"\b(\d{6})\b", body)
            if codes:
                # Mark as seen to avoid re-reading
                imap.store(msg_id, '+FLAGS', '\\Seen')
                imap.logout()
                return codes[0]

        imap.logout()
        return None
    except Exception as e:
        print(f"[imap] error: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    # Test with the FC26 account email
    addr = "ivanova6vix3@rambler.ru"
    pwd = "mEA5H-tdXdQE"
    code = get_epic_code(addr, pwd)
    if code:
        print(f"FOUND CODE: {code}")
    else:
        print("NO CODE FOUND (no recent Epic emails)")
