import json, subprocess, time
# Test MTProto proxies for Telegram connectivity
with open(r'C:\Users\alexa\.zcode\workspace\default\tg-order-watch\mtproto.json', 'r') as f:
    proxies = json.load(f)

print(f"total proxies: {len(proxies)}")
working = []
for p in proxies[:20]:
    host, port = p['server'], p['port']
    # Quick TCP test
    result = subprocess.run(
        ['curl', '-s', '-m', '5', f'https://{host}:{port}', '-o', '/dev/null',
         '-w', '%{http_code}'],
        capture_output=True, text=True, timeout=8)
    # Even a non-200 response means the host is reachable
    if result.stdout.strip() not in ('000', ''):
        working.append(p)
        print(f"REACHABLE: {host}:{port} -> {result.stdout.strip()}")

print(f"\nreachable: {len(working)}/{min(20, len(proxies))}")
for p in working[:5]:
    print(json.dumps(p, indent=1))
