"""Mark all existing emails as seen, then harvest with fresh 2FA code."""
import imaplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def mark_all_seen(email_addr: str, email_pass: str) -> int:
    """Mark ALL emails in INBOX as seen. Returns count marked."""
    imap = imaplib.IMAP4_SSL("imap.rambler.ru", 993)
    imap.login(email_addr, email_pass)
    imap.select("INBOX")
    _, msg_ids = imap.search(None, "ALL")
    ids = msg_ids[0].split()
    count = 0
    for msg_id in ids:
        imap.store(msg_id, "+FLAGS", "\\Seen")
        count += 1
    imap.logout()
    return count


if __name__ == "__main__":
    addr = sys.argv[1]
    pwd = sys.argv[2]
    n = mark_all_seen(addr, pwd)
    print(f"marked {n} emails as seen")
