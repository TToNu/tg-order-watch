import socket
import time

HOST, PORT = "mobile-x.bpproxy.at", 3002
USER = "bpuser-Bh1RGb3X"
PWD = "2ZEwhdXODGsRehldtYCz_country-US_region-texas"


def attempt(host, port, wait_reply=20):
    for n in range(2):
        try:
            s = socket.create_connection((HOST, PORT), timeout=15)
            s.settimeout(wait_reply)
            s.sendall(b"\x05\x01\x02")
            s.recv(2)
            u, p = USER.encode(), PWD.encode()
            s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            s.recv(2)
            h = host.encode()
            s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h
                      + port.to_bytes(2, "big"))
            resp = s.recv(16)
            print(f"{host}:{port} try{n} rep=0x{resp[1]:02x} {resp[:6]!r}",
                  flush=True)
            return s if resp[1] == 0 else None
        except OSError as e:
            print(f"{host}:{port} try{n}: {e}", flush=True)
            time.sleep(6)
    return None


time.sleep(8)
s = attempt("www.epicgames.com", 443)
if s:
    import ssl
    tls = ssl.create_default_context().wrap_socket(
        s, server_hostname="www.epicgames.com")
    tls.sendall(b"GET /id/login HTTP/1.1\r\nHost: www.epicgames.com\r\n"
                b"Connection: close\r\n\r\n")
    print("http:", tls.recv(60)[:60])
