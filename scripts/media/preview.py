#!/usr/bin/env python3
"""Open VIGIL's local film gallery with seekable video; Python 3.10+ only."""
from __future__ import annotations

import argparse
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import webbrowser

MEDIA = Path(__file__).resolve().parents[2] / "docs" / "media"


def byte_range(value: str, size: int) -> tuple[int, int]:
    """Resolve one inclusive HTTP byte range, including suffix ranges."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()) or size == 0:
        raise ValueError("Unsupported byte range")
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError("Empty suffix range")
        return max(0, size - length), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable byte range")
    return start, end


def make_server(root: Path = MEDIA, port: int = 0) -> ThreadingHTTPServer:
    root = root.resolve()
    if not (root / "index.html").is_file():
        raise ValueError("Film assets are missing. Run this command from the source release.")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, *, head=False):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed:
                self.send_error(403, "Local access only")
                return
            relative = unquote(urlsplit(self.path).path).lstrip("/")
            try:
                path = (root / relative).resolve()
                if path.is_dir():
                    path = (path / "index.html").resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    self.send_error(404, "File not found")
                    return
                with path.open("rb") as source:
                    stat = path.stat()
                    size = stat.st_size
                    modified = formatdate(stat.st_mtime, usegmt=True)
                    requested = self.headers.get("Range")
                    if self.headers.get("If-Range") not in (None, modified):
                        requested = None
                    start, end = 0, size - 1
                    if requested:
                        try:
                            start, end = byte_range(requested, size)
                        except ValueError:
                            self.send_response(416)
                            self.send_header("Content-Range", f"bytes */{size}")
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    self.send_response(206 if requested else 200)
                    self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                    self.send_header("Content-Length", str(end - start + 1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Last-Modified", modified)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                    if requested:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    if head:
                        return
                    source.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = source.read(min(128 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                # Browsers cancel one range request when the viewer seeks again.
                pass
            except (OSError, ValueError):
                self.send_error(404, "File not found")

        def do_GET(self):
            self.respond()

        def do_HEAD(self):
            self.respond(head=True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Local port; 0 selects an available port.")
    parser.add_argument("--no-open", action="store_true", help="Print the URL without opening a browser.")
    args = parser.parse_args()
    try:
        server = make_server(port=args.port)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"VIGIL films: {url}\nLocal playback only. Press Ctrl+C to close.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
