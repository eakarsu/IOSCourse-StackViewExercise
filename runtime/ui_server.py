from __future__ import annotations

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class UIHandler(SimpleHTTPRequestHandler):
    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = urlsplit(self.path).path
        self.log_message('"%s %s" %s %s', self.command, path, code, size)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("runtime-ui: " + (fmt % args) + "\n")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src http://127.0.0.1:31004; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        super().end_headers()


def main() -> int:
    port_text = os.environ.get("UI_PORT", "")
    if port_text != "31005":
        print("UI_PORT must be 31005 for this verification shard", file=sys.stderr)
        return 2
    directory = Path(__file__).resolve().parent / "ui"
    handler = partial(UIHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 31005), handler)
    print("runtime UI listening on http://127.0.0.1:31005", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
