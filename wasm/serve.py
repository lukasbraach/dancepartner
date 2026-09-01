"""Serve the built browser bundle locally, with the fallback a static host needs.

``python -m http.server`` is almost enough, and fails on exactly one thing: the app's pages are
client-side routes. ``st.navigation`` puts ``/survey`` in the address bar, and reloading there
asks the server for a file that was never built, so the stock handler answers 404 and the coach
sees a broken app.

This is the same rule GitHub Pages gets from ``404.html`` and a returning visitor gets from the
service worker, applied to the one server that has neither: anything that looks like a page
request is answered with ``index.html``, and the client router takes it from there.

Development only -- nothing in ``src/dancepartner/`` imports it, and no deployment runs it.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO


class SPAHandler(SimpleHTTPRequestHandler):
    """A static handler that falls back to the app shell for unknown page requests."""

    def send_head(self) -> BytesIO | BinaryIO | None:
        """Rewrite a miss that looks like a route, then serve normally.

        Only extensionless paths are rewritten. A missing ``icons/icon-192.png`` is a build
        bug and should stay a 404 rather than quietly return 226 KiB of HTML.
        """
        candidate = Path(self.translate_path(self.path))
        if not candidate.exists() and not candidate.suffix:
            self.path = "/index.html"
        return super().send_head()


def main(argv: list[str] | None = None) -> int:
    """Serve ``--directory`` on ``--port`` until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--directory", default="wasm/dist")
    args = parser.parse_args(argv)

    handler: Any = partial(SPAHandler, directory=args.directory)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving {args.directory} on http://localhost:{args.port} -- Ctrl-C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":  # pragma: no cover -- entry point
    sys.exit(main())
