"""Exercise video seeking and file boundaries through the real HTTP server."""
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from scripts.media.preview import make_server


@pytest.fixture
def media_http(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    (root / "index.html").write_text('<video controls src="film.mp4"></video>')
    payload = bytes(range(256)) * 4
    (root / "film.mp4").write_bytes(payload)
    (root / "empty.mp4").touch()
    (root / "directory").mkdir()
    (tmp_path / "secret.txt").write_text("outside presentation assets")
    (root / "escape.txt").symlink_to(tmp_path / "secret.txt")
    (root / "linked-index").mkdir()
    (root / "linked-index" / "index.html").symlink_to(tmp_path / "secret.txt")
    server = make_server(root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path="/film.mp4", *, headers=None, method="GET"):
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", headers=headers or {}, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read(), response.headers

    yield request, payload
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_full_movie_and_head_have_matching_length(media_http):
    request, payload = media_http
    code, body, headers = request()
    assert code == 200 and body == payload
    assert headers["Content-Type"] == "video/mp4"
    assert headers["Accept-Ranges"] == "bytes"
    code, body, head = request(method="HEAD")
    assert code == 200 and body == b""
    assert head["Content-Length"] == headers["Content-Length"] == str(len(payload))


@pytest.mark.parametrize(("range_header", "start", "end"), [
    ("bytes=0-127", 0, 127),
    ("bytes=700-", 700, 1023),
    ("bytes=-128", 896, 1023),
    ("bytes=900-9999", 900, 1023),
    ("bytes=-9999", 0, 1023),
])
def test_browser_can_read_an_exact_video_range(media_http, range_header, start, end):
    request, payload = media_http
    code, body, headers = request(headers={"Range": range_header})
    assert code == 206 and body == payload[start:end + 1]
    assert headers["Content-Range"] == f"bytes {start}-{end}/{len(payload)}"
    assert int(headers["Content-Length"]) == len(body)
    code, body, head = request(headers={"Range": range_header}, method="HEAD")
    assert code == 206 and not body and head["Content-Range"] == headers["Content-Range"]


@pytest.mark.parametrize("value", ["bytes=1024-", "bytes=8-3", "bytes=-0", "bytes=-", "bytes=0-1,5-6", "items=0-3"])
def test_invalid_ranges_do_not_send_a_misleading_full_movie(media_http, value):
    request, payload = media_http
    code, body, headers = request(headers={"Range": value})
    assert code == 416 and not body
    assert headers["Content-Range"] == f"bytes */{len(payload)}"


def test_if_range_mismatch_returns_a_complete_representation(media_http):
    request, payload = media_http
    code, body, _ = request(headers={"Range": "bytes=10-20", "If-Range": '"outdated"'})
    assert code == 200 and body == payload


@pytest.mark.parametrize("path", ["/%2e%2e/secret.txt", "/escape.txt", "/directory/", "/linked-index/", "/missing.mp4"])
def test_only_existing_presentation_files_are_readable(media_http, path):
    request, _ = media_http
    code, body, _ = request(path)
    assert code == 404 and b"outside presentation assets" not in body


def test_preview_rejects_external_host_headers(media_http):
    request, _ = media_http
    code, _, _ = request(headers={"Host": "untrusted.example"})
    assert code == 403


def test_empty_file_and_home_page(media_http):
    request, _ = media_http
    code, body, headers = request("/empty.mp4")
    assert code == 200 and body == b"" and headers["Content-Length"] == "0"
    code, _, _ = request("/empty.mp4", headers={"Range": "bytes=0-"})
    assert code == 416
    code, body, _ = request("/")
    assert code == 200 and b"<video controls" in body
