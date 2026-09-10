import socket
import ssl

HOST, PORT = "151.242.178.178", 50101
USER = b"iZv57jYf"
PWD = b"GiQ4H1jE6X"


def recv(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise OSError("closed")
        b += c
    return b


s = socket.create_connection((HOST, PORT), timeout=20)
s.sendall(b"\x05\x01\x02")
print("greet:", recv(s, 2))
s.sendall(b"\x01" + bytes([len(USER)]) + USER + bytes([len(PWD)]) + PWD)
print("auth:", recv(s, 2))
h = b"api.ipify.org"
s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + (443).to_bytes(2, "big"))
r = recv(s, 4)
print("connect:", r)
if r[3] == 3:
    ln = recv(s, 1)[0]
    recv(s, ln + 2)
elif r[3] == 1:
    recv(s, 6)

tls = ssl.create_default_context().wrap_socket(s, server_hostname="api.ipify.org")
tls.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
d = b""
while True:
    c = tls.recv(4096)
    if not c:
        break
    d += c
print("body tail:", d[-60:])
