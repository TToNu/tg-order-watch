import socket
import time

HOST, PORT = "mobile-x.bpproxy.at", 3002
USER = "bpuser-Bh1RGb3X"
PWD = "2ZEwhdXODGsRehldtYCz_country-US_region-texas"


def try_connect(atyp, host_bytes, port, label):
    s = socket.create_connection((HOST, PORT), timeout=15)
    s.sendall(b"\x05\x01\x02")
    s.recv(2)
    u, p = USER.encode(), PWD.encode()
    s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
    s.recv(2)
    req = b"\x05\x01\x00" + atyp + host_bytes + port.to_bytes(2, "big")
    s.sendall(req)
    time.sleep(1.5)
    resp = s.recv(16)
    print(f"{label}: rep=0x{resp[1]:02x} raw={resp[:8]!r}")
    s.close()


try_connect(b"\x03", b"www.google.com", 443, "google:443 (domain)")
try_connect(b"\x03", b"www.epicgames.com", 443, "epic:443 (domain)")
try_connect(b"\x03", b"api.ipify.org", 80, "ipify:80 (domain)")
try_connect(b"\x01", socket.inet_aton("104.26.10.87"), 443, "ip-direct:443")
