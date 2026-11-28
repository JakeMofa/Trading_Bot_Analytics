#!/usr/bin/env python3
"""Open an SSH-authenticated Benchmark feed-control grant, received on stdin."""
import json
import sys
import time
import webbrowser
from urllib.parse import urlencode


def main():
    grant=json.loads(sys.stdin.buffer.read(8193))
    token=grant.get('access_token','')
    if (grant.get('origin')!='pp-live-pp-benchmark-watch' or not 0<grant['expires_at']-time.time()<=1801
            or len(token)>160 or len(token.split('.'))!=3 or not all(c in '0123456789abcdef.' for c in token)):
        raise SystemExit('Invalid or expired Benchmark feed-control grant')
    # The URL fragment never enters the HTTP request. Dashboard JS erases it
    # before contacting the operator and keeps the grant only in page memory.
    if not webbrowser.open('http://127.0.0.1:18433/dashboard#'+urlencode({'feed_session':token})):
        raise SystemExit('Browser launch failed')


if __name__=='__main__':
    main()
