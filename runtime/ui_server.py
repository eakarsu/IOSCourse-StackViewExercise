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
            f"connect-src http://127.0.0.1:{os.environ.get('API_PORT', '')}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        super().end_headers()


def main() -> int:
    port_text = os.environ.get("UI_PORT", "")
    if not port_text.isdigit() or not 1024 <= int(port_text) <= 65535:
        print("UI_PORT must be numeric and between 1024 and 65535", file=sys.stderr)
        return 2
    directory = Path(__file__).resolve().parent / "ui"
    handler = partial(UIHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", int(port_text)), handler)
    print(f"runtime UI listening on http://127.0.0.1:{port_text}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
