"""Tiny local HTTP-proxy -> authenticated-SOCKS5 forwarder.

Chromium cannot pass SOCKS credentials in --proxy-server, so we expose a
local unauthenticated HTTP proxy and relay every CONNECT through the
upstream mobile SOCKS5 with auth. Threads, no dependencies.
"""

import socket
import threading


class HttpToSocksBridge:
    def __init__(self, upstream_host: str, upstream_port: int,
                 user: str, password: str, listen_port: int = 9340):
        self.uhost = upstream_host
        self.uport = upstream_port
        self.user = user.encode()
        self.password = password.encode()
        self.listen_port = listen_port
        self._sock = None
        self._thread = None

    def start(self) -> None:
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.listen_port))
        self._sock.listen(16)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                client, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,),
                             daemon=True).start()

    def _socks_connect(self, host: str, port: int) -> socket.socket:
        s = socket.create_connection((self.uhost, self.uport), timeout=30)
        # offer both no-auth and user/pass — some servers stall otherwise
        s.sendall(b"\x05\x02\x00\x02")
        resp = self._recv(s, 2)
        if resp[1] == 0x00:
            pass  # no auth needed
        elif resp[1] == 0x02:
            # RFC1929 username/password subnegotiation
            req = b"\x01" + bytes([len(self.user)]) + self.user \
                + bytes([len(self.password)]) + self.password
            s.sendall(req)
            resp = self._recv(s, 2)
            if resp[1:] != b"\x00":
                raise OSError("socks auth failed")
        else:
            raise OSError(f"socks auth rejected: {resp!r}")
        # CONNECT (domain name)
        h = host.encode()
        req = b"\x05\x01\x00\x03" + bytes([len(h)]) + h \
            + (port).to_bytes(2, "big")
        s.sendall(req)
        resp = self._recv(s, 4)
        if resp[1] != 0:
            raise OSError(f"socks connect failed: {resp!r}")
        # skip bound address
        if resp[3] == 1:
            self._recv(s, 4 + 2)
        elif resp[3] == 3:
            ln = self._recv(s, 1)[0]
            self._recv(s, ln + 2)
        elif resp[3] == 4:
            self._recv(s, 16 + 2)
        return s

    @staticmethod
    def _recv(s: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                raise OSError("socks closed")
            buf += chunk
        return buf

    def _handle(self, client: socket.socket) -> None:
        try:
            client.settimeout(60)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(4096)
                if not chunk:
                    return
                head += chunk
            line = head.split(b"\r\n", 1)[0].decode("latin1")
            method, target, _ = line.split(" ", 2)
            if method != "CONNECT":
                return
            host, _, port = target.partition(":")
            remote = self._socks_connect(host, int(port or 443))
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self._pump(client, remote)
        except OSError:
            pass
        finally:
            try:
                client.close()
            except OSError:
                pass

    @staticmethod
    def _pump(a: socket.socket, b: socket.socket) -> None:
        a.settimeout(300)
        b.settimeout(300)

        def one_way(src: socket.socket, dst: socket.socket) -> None:
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        t = threading.Thread(target=one_way, args=(b, a), daemon=True)
        t.start()
        one_way(a, b)
        t.join(timeout=5)
