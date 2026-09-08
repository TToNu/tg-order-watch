# tg-order-watch

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A personal Telegram watchdog for freelance orders: watches a list of chats and
channels and instantly pings **Saved Messages** when a new message matches your
keywords (`нужен скрипт`, `кто напишет бота`, `#job`, …). In small niche chats
the first responder usually wins the order — this tool makes sure that's you.

Built with [Telethon](https://github.com/LonamiWebs/Telethon). Runs on any OS,
uses ~30 MB RAM, survives on a spare machine or a cheap VPS.

## How it works

1. `Telethon` keeps one long-polling connection to Telegram under your account.
2. `NewMessage` events from the chats in your config are matched against a
   keyword list (case-insensitive, substring).
3. On a hit, you get a message in Saved Messages: chat name, author, time and
   the first 500 characters — enough to decide whether to jump in.

## Setup

```bash
pip install -r requirements.txt
copy config.example.json config.json   # Windows
# cp config.example.json config.json   # Linux/macOS
```

1. Get `api_id` / `api_hash` at [my.telegram.org](https://my.telegram.org) →
   *API development tools* → create an app.
2. Edit `config.json`: put your `api_id`, `api_hash`, `phone` (international
   format), and the chats you want to watch (usernames like `python_vacancy`
   or numeric ids).
3. First run asks for the login code Telegram sends you and creates
   `session.session`; afterwards it logs in silently.

```bash
python monitor.py            # run the watchdog
python monitor.py --once     # verify config + login, list monitored chats
python monitor.py -v         # verbose logging
```

## Config reference

| Key | Meaning |
|---|---|
| `api_id`, `api_hash` | Telegram API credentials (my.telegram.org) |
| `phone` | Your number, international format |
| `chats` | Usernames / ids of chats and channels to watch |
| `keywords` | Lowercase substrings to match against new messages |

## Security notes

- `config.json` and `session.session` contain full access to your Telegram
  account. They are git-ignored; never commit or share them.
- The session file can be revoked any time via Telegram → Settings → Devices.

## Roadmap

- [ ] Reply-from-notification (send a templated response right from Saved Messages)
- [ ] SQLite log of matched orders + stats per chat
- [ ] Deduplicate near-identical reposts across channels

## License

[MIT](LICENSE)
