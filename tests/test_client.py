"""_client.get: throttle, retry/backoff, error mapping, User-Agent.

conftest blocks `_client.get` for every test so nothing can hit a live host. These
tests exercise the real function, so they grab it at import time (before the
autouse fixture patches it) and point it at a throwaway server on 127.0.0.1.
"""

from __future__ import annotations

import http.server
import threading
import types

import pytest
import requests

from twmarket import _client

REAL_GET = _client.get
REAL_FETCH_STOCK_DAY = _client.fetch_stock_day
REAL_FETCH_MOPS = _client.fetch_mops_revenue


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        server = self.server
        server.hits.append({"path": self.path, "ua": self.headers.get("User-Agent")})
        status = server.script[min(len(server.hits), len(server.script)) - 1]
        body = b"ok" if status == 200 else b"nope"
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture
def server(monkeypatch):
    """A local HTTP server answering with a scripted sequence of status codes.

    The last status repeats once the script runs out. Backoff sleeping is
    replaced by a recorder, so retry tests take milliseconds and the delays
    can be asserted on.
    """
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(_client, "_session", None)  # fresh session + adapter per test
    monkeypatch.setattr(_client, "_last_request_time", 0.0)
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.hits, srv.script, srv.sleeps = [], [200], sleeps
    thread = threading.Thread(
        target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}/x"
    yield srv
    srv.shutdown()
    srv.server_close()


def test_success_sends_realistic_user_agent(server):
    resp = REAL_GET(server.url)
    assert resp.content == b"ok"
    ua = server.hits[0]["ua"]
    assert ua == _client.USER_AGENT
    assert ua.startswith("Mozilla/5.0")  # not python-requests/x.y


def test_404_raises_httperror_without_retrying(server):
    server.script = [404]
    with pytest.raises(requests.HTTPError):
        REAL_GET(server.url)
    assert len(server.hits) == 1


def test_transient_5xx_is_retried_then_succeeds(server):
    server.script = [503, 503, 200]
    assert REAL_GET(server.url).content == b"ok"
    assert len(server.hits) == 3


def test_persistent_5xx_gives_up_after_bounded_retries(server):
    server.script = [500]
    with pytest.raises(requests.RequestException):
        REAL_GET(server.url)
    # Retry(total=4): the first try plus four retries, then a hard stop.
    assert len(server.hits) == 5


def test_backoff_grows_between_retries(server):
    server.script = [500]
    with pytest.raises(requests.RequestException):
        REAL_GET(server.url)
    # Sleeps: one throttle sleep is possible on the first call only if a request
    # happened <1s ago (not the case here), so what was recorded is retry backoff.
    backoff = [s for s in server.sleeps if s > 0]
    assert len(backoff) >= 3
    assert backoff == sorted(backoff)
    assert backoff[-1] > backoff[0]


def test_429_is_treated_as_retryable(server):
    """MOPS/TWSE rate limiting must slow us down, not raise on first contact."""
    server.script = [429, 200]
    assert REAL_GET(server.url).status_code == 200
    assert len(server.hits) == 2


def test_throttle_enforces_minimum_spacing(monkeypatch):
    clock = {"now": 100.0}
    slept: list[float] = []

    def _sleep(seconds):
        slept.append(seconds)
        clock["now"] += seconds

    fake_time = types.SimpleNamespace(monotonic=lambda: clock["now"], sleep=_sleep)
    monkeypatch.setattr(_client, "time", fake_time)
    monkeypatch.setattr(_client, "_last_request_time", 0.0)

    _client._throttle()  # long since any previous request: no wait
    assert slept == []

    clock["now"] += 0.25  # a caller asks again after 250 ms
    _client._throttle()
    assert slept == [pytest.approx(_client.MIN_REQUEST_SPACING - 0.25)]

    clock["now"] += _client.MIN_REQUEST_SPACING + 5  # slow caller: no wait
    _client._throttle()
    assert len(slept) == 1


def test_every_get_passes_through_the_throttle(server, monkeypatch):
    calls = []
    monkeypatch.setattr(_client, "_throttle", lambda: calls.append(1))
    REAL_GET(server.url)
    REAL_GET(server.url)
    assert len(calls) == 2


def test_mops_url_drops_suffix_for_roc_year_98_and_earlier(monkeypatch):
    seen = []

    def _get(url, **kw):
        seen.append(url)
        return types.SimpleNamespace(content=b"")

    monkeypatch.setattr(_client, "get", _get)
    for roc_year, month in [(98, 12), (99, 1), (114, 6)]:
        REAL_FETCH_MOPS(roc_year, month)
    assert seen[0].endswith("/t21sc03_98_12.html")
    assert seen[1].endswith("/t21sc03_99_1_0.html")
    assert seen[2].endswith("/t21sc03_114_6_0.html")
    assert all(u.startswith("https://mopsov.twse.com.tw/") for u in seen)


def test_stock_day_request_params(monkeypatch):
    seen = {}

    def _get(url, params=None, **kw):
        seen.update(url=url, params=params)
        return types.SimpleNamespace(json=lambda: {"stat": "OK"})

    monkeypatch.setattr(_client, "get", _get)
    REAL_FETCH_STOCK_DAY("2330", 2025, 6)
    assert seen["url"] == _client.TWSE_STOCK_DAY_URL
    assert seen["params"] == {"response": "json", "date": "20250601", "stockNo": "2330"}
