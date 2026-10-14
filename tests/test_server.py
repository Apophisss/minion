import json
import threading
import urllib.error
import urllib.request

import pytest

from minion import server


class FakeBackend:
    name = "fake"

    def list(self, stats=False):
        return []


@pytest.fixture()
def http(monkeypatch):
    monkeypatch.setattr(server, "get_backend", lambda name=None: FakeBackend())
    httpd, base, token = server.make_server("127.0.0.1", 0, token="", quiet=True)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield base, token
    httpd.shutdown()
    httpd.server_close()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.headers, r.read()


def test_requires_token(http):
    base, token = http
    with pytest.raises(urllib.error.HTTPError) as e:
        get(f"{base}/api/desktops")
    assert e.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as e:
        get(f"{base}/api/desktops", {"Authorization": "Bearer wrong"})
    assert e.value.code == 401


def test_api_with_token(http):
    base, token = http
    code, _, body = get(f"{base}/api/health?token={token}")
    assert code == 200 and json.loads(body)["ok"]
    code, _, body = get(f"{base}/api/desktops", {"Authorization": f"Bearer {token}"})
    assert json.loads(body) == []
    code, _, body = get(f"{base}/api/profiles?token={token}")
    assert "office" in [p["name"] for p in json.loads(body)]


def test_pages_and_cookie(http):
    base, token = http
    code, headers, body = get(f"{base}/?token={token}")
    assert code == 200 and b"minion" in body
    assert "minion_token=" in headers.get("Set-Cookie", "")
    code, _, body = get(f"{base}/static/logo.svg")  # public asset
    assert code == 200 and body.startswith(b"<svg")
    with pytest.raises(urllib.error.HTTPError) as e:
        get(f"{base}/static/../server.py")
    assert e.value.code in (400, 404)
