import socket
import time

HOST, PORT = "mobile-x.bpproxy.at", 3002
USER = "bpuser-Bh1RGb3X"
PWD = "2ZEwhdXODGsRehldtYCz_country-US_region-texas"

s = socket.create_connection((HOST, PORT), timeout=20)
s.sendall(b"\x05\x01\x02")
print("greeting resp:", s.recv(2))
u, p = USER.encode(), PWD.encode()
s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
time.sleep(1)
print("auth resp:", s.recv(2))
h = b"api.ipify.org"
s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + (443).to_bytes(2, "big"))
time.sleep(2)
print("connect resp:", s.recv(10))
# TLS through it
import ssl
ctx = ssl.create_default_context()
tls = ctx.wrap_socket(s, server_hostname="api.ipify.org")
tls.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
data = b""
while True:
    chunk = tls.recv(4096)
    if not chunk:
        break
    data += chunk
print(data.decode()[-120:])
