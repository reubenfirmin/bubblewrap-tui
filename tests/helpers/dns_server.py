"""Serve deterministic UDP/TCP DNS in a test namespace, then run a child."""

import socket
import struct
import subprocess
import sys
import threading


def answer(query):
    """Return a fixed A record, preserving the transaction ID and question."""
    header = query[:2] + struct.pack("!5H", 0x8180, 1, 1, 0, 0)
    record = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4)
    return header + query[12:] + record + socket.inet_aton("93.184.216.34")


def serve_udp(sock):
    while True:
        query, peer = sock.recvfrom(65535)
        sock.sendto(answer(query), peer)


def serve_tcp(sock):
    while True:
        conn, _ = sock.accept()
        with conn:
            conn.settimeout(5)
            size = conn.recv(2, socket.MSG_WAITALL)
            if len(size) != 2:
                continue
            query = conn.recv(struct.unpack("!H", size)[0], socket.MSG_WAITALL)
            response = answer(query)
            conn.sendall(struct.pack("!H", len(response)) + response)


def main():
    address = sys.argv[1]
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    udp = socket.socket(family, socket.SOCK_DGRAM)
    tcp = socket.socket(family, socket.SOCK_STREAM)
    udp.bind((address, 53))
    tcp.bind((address, 53))
    tcp.listen()
    threading.Thread(target=serve_udp, args=(udp,), daemon=True).start()
    threading.Thread(target=serve_tcp, args=(tcp,), daemon=True).start()
    try:
        return subprocess.run(sys.argv[2:], timeout=40).returncode
    finally:
        udp.close()
        tcp.close()


if __name__ == "__main__":
    sys.exit(main())
