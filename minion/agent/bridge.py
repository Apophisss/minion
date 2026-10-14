"""stdin/stdout <-> agent socket relay.

The host runs `docker exec -i <desktop> python3 -S /opt/minion/minion_agent/bridge.py`
and speaks JSON lines through it. Standard library only, so it starts in milliseconds.
"""

import os
import socket
import sys
import threading
import time


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MINION_SOCKET", "/tmp/minion/agent.sock")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + float(os.environ.get("MINION_CONNECT_TIMEOUT", "30"))
    while True:
        try:
            sock.connect(path)
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() > deadline:
                sys.stderr.write(f"minion: agent socket {path} is not available\n")
                return 2
            time.sleep(0.1)

    def upstream() -> None:
        try:
            while True:
                data = os.read(0, 65536)
                if not data:
                    break
                sock.sendall(data)
        except OSError:
            pass
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=upstream, daemon=True).start()
    out = sys.stdout.fileno()
    try:
        while True:
            data = sock.recv(262144)
            if not data:
                break
            view = memoryview(data)
            while view:
                n = os.write(out, view)
                view = view[n:]
    except OSError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
