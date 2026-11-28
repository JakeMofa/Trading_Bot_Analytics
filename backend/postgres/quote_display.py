"""Best-effort PP display snapshots. The Unix datagram never acknowledges a write."""
import asyncio
import json
import os
from pathlib import Path
import socket
import stat

SOCKET_PATH = '/run/quote-display/live.sock'


def enabled(settings):
    return (settings.environment == 'preprod' and settings.data_mode == 'pp_live'
            and os.environ.get('TRADEBOT_PP_QUOTE_DISPLAY') == '1')


class DisplaySender:
    def __init__(self, origin, path=SOCKET_PATH):
        self.origin = origin
        self.path = path
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)

    def send(self, snapshot):
        body = json.dumps({'origin': self.origin, **snapshot}, separators=(',', ':')).encode()
        if len(body) <= 8192:
            try:
                self.socket.sendto(body, self.path)
            except OSError:
                # API restarts and a full display buffer must never hold the writer.
                pass


async def receive(state, path=SOCKET_PATH):
    endpoint = Path(path)
    if endpoint.exists() and stat.S_ISSOCK(endpoint.stat().st_mode):
        endpoint.unlink()
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
        receiver.bind(path)
        os.chmod(path, 0o600)
        receiver.setblocking(False)
        try:
            while True:
                data = await asyncio.get_running_loop().sock_recv(receiver, 8193)
                if len(data) <= 8192:
                    try:
                        packet = json.loads(data)
                        if packet['origin'] == state.settings.origin_id:
                            state.display(packet)
                    except (UnicodeDecodeError, ValueError, TypeError, KeyError):
                        continue
        finally:
            endpoint.unlink(missing_ok=True)
