#!/usr/bin/env python3
"""Batch 19.3: which failed requests are asked once more, and a host that does not answer asked nothing more in a drawing.

Terry, 2026-10-22 (decision 52): "one retry after 2 s, only for a dropped or reset connection
or a 5xx; none for a 404 or other 4xx, an outage page, a bot check or a timeout". A server
on 127.0.0.1 answers each address as its path says, and counts the requests it receives:

  ok       a two-column CSV, as FRED sends;
  page     an outage page with status 200 (FRED's of 2026-10-21);
  404      not found; 503 a server error;
  reset    the connection reset as soon as the request arrives;
  close    the connection closed without an answer;
  partway  an answer promising 1000 bytes, broken off after 10;
  hang     the connection held open, never answered (the program's timeout ends it);
  bad      a one-column CSV, which FRED's reader refuses.

Each kind is asked through ``http.canadian_get`` (requests, as every source but FRED) and
``http.fetch_fred_csv`` (urllib, FRED's), and a refused connection (a port nothing listens
on) through both. A dropped connection (reset, close, partway) and a 503 must be asked twice,
``RETRY_WAIT_SECONDS`` apart; everything else once. The downloads are not cached here, and
no last good copy is kept.

Then, in a drawing (``http.drawing_downloads``; Terry, decision 52: "once a host fails as
unavailable (timeout after retries, refused connection, outage page, bot check), ask it
nothing more in that drawing ... a series-specific failure doesn't stop the others; the
next drawing tries again"): after a hang, an outage page or a refused connection, the
host's next request is not made and fails as the first did, while another host is asked;
the next drawing asks it again; after a 404, a reset (twice), a 503 (twice) or an answer
that cannot be read, the host's other requests are made; a request of another thread,
waiting its turn while the host hangs, is not made; outside a drawing each request is.

Usage (from the project root)::

    python tools/check_requests.py

Exit code 1 if any check fails. No network beyond this machine.
"""

from __future__ import annotations

import contextlib
import io
import socket
import struct
import sys
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import config, http  # noqa: E402

RESULTS: list[bool] = []
TIMEOUT = 1  # the program's timeout here, in seconds (90 in use)


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    print(f"{'ok  ' if condition else 'FAIL'} {label}" + (f"  [{detail}]" if detail != "" else ""))


class Server:
    """Answers each request by its path's first part (the module docstring), counting the requests by path."""

    PAGE = b"<!doctype html>\n<html><head><title>Site Maintenance</title></head><body>down</body></html>"

    def __init__(self) -> None:
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(64)
        self.port = self.listener.getsockname()[1]
        self.asked: Counter = Counter()
        self.held: list[socket.socket] = []  # the hung connections, kept open
        self.arrived = threading.Event()  # set at each request
        threading.Thread(target=self._serve, daemon=True).start()

    def url(self, kind: str) -> str:
        return f"http://127.0.0.1:{self.port}/{kind}"

    def _serve(self) -> None:
        while True:
            connection, _address = self.listener.accept()
            threading.Thread(target=self._answer, args=(connection,), daemon=True).start()

    @staticmethod
    def _send(connection: socket.socket, status: str, body: bytes, kind: str = "text/csv") -> None:
        head = f"HTTP/1.1 {status}\r\nContent-Type: {kind}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        connection.sendall(head.encode() + body)
        connection.close()

    def _answer(self, connection: socket.socket) -> None:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = connection.recv(4096)
            if not chunk:
                return
            request += chunk
        path = request.split(b" ", 2)[1].decode()
        kind = path.lstrip("/").split("?", 1)[0].split("/", 1)[0]
        self.asked[kind] += 1
        self.arrived.set()
        if kind == "ok":
            self._send(connection, "200 OK", b"observation_date,X\n2026-01-01,1.5\n2026-02-01,1.75\n")
        elif kind == "bad":
            self._send(connection, "200 OK", b"observation_date\n2026-01-01\n")
        elif kind == "page":
            self._send(connection, "200 OK", self.PAGE, "text/html")
        elif kind in ("404", "503"):
            self._send(connection, {"404": "404 Not Found", "503": "503 Service Unavailable"}[kind], b"")
        elif kind == "reset":
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            connection.close()
        elif kind == "close":
            connection.close()
        elif kind == "partway":
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n0123456789")
            connection.close()
        elif kind == "hang":
            self.held.append(connection)


def refused_url() -> str:
    """An address on this machine that nothing listens on."""
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    return f"http://127.0.0.1:{port}/refused"


def via_requests(url: str) -> object:
    return http.canadian_get(url, timeout=TIMEOUT)


def via_urllib(url: str) -> object:
    """FRED's reader, its address pointed at ``url``; the series named for the address's kind (``?id=X_ok``), so each is its own request."""
    http.FRED_CSV_URL = url
    return http.fetch_fred_csv(f"X_{url.rsplit('/', 1)[1]}")


def ask(server: Server, get, kind: str, url: str | None = None) -> tuple[int, str, str, float]:
    """Ask one address; return (requests the server received, what was raised or "answered", what was printed, seconds)."""
    server.asked.clear()
    printed = io.StringIO()
    began = time.monotonic()
    with contextlib.redirect_stdout(printed):
        try:
            get(url or server.url(kind))
            outcome = "answered"
        except Exception as exc:
            outcome = type(exc).__name__
    return server.asked[kind], outcome, printed.getvalue(), time.monotonic() - began


def check_retries(server: Server) -> None:
    http.RETRY_WAIT_SECONDS = 0.05  # the rule, not the wait; the wait itself is checked once below
    twice = ("reset", "close", "partway", "503")
    for name, get in (("requests", via_requests), ("urllib (FRED)", via_urllib)):
        for kind in ("ok", "404", "page", "hang", *twice) + (("bad",) if get is via_urllib else ()):
            count, outcome, printed, _seconds = ask(server, get, kind)
            expected = 2 if kind in twice else 1
            said = "asked once more" in printed
            check(f"{name}: {kind}: asked {expected} time{'s' if expected > 1 else ''}"
                  + (", the second attempt's failure raised" if kind in twice else f" ({outcome})"),
                  count == expected and said == (kind in twice) and (outcome == "answered") == (kind == "ok"),
                  f"asked {count}, {outcome}, {printed.strip()!r}")
        count, outcome, printed, seconds = ask(server, get, "refused", refused_url())
        check(f"{name}: a refused connection not asked again ({outcome})",
              "asked once more" not in printed and outcome != "answered", f"{seconds:.1f} s, {printed.strip()!r}")
    http.RETRY_WAIT_SECONDS = config.RETRY_WAIT_SECONDS
    count, outcome, printed, seconds = ask(server, via_requests, "503")
    check(f"the second attempt {config.RETRY_WAIT_SECONDS} s after the first ({seconds:.2f} s in all)",
          config.RETRY_WAIT_SECONDS == 2 and count == 2 and 2 <= seconds < 3, printed.strip())


def outcome_of(get, url: str) -> str:
    """"answered", or the name of what was raised."""
    try:
        get(url)
        return "answered"
    except Exception as exc:
        return type(exc).__name__


def check_hosts(server: Server, other: Server) -> None:
    """A host that fails as unavailable is asked nothing more in the drawing (19.3); a failure of one request is not the host's."""
    http.RETRY_WAIT_SECONDS = 0.05
    for name, get in (("requests", via_requests), ("urllib (FRED)", via_urllib)):
        for kind in ("hang", "page"):
            server.asked.clear()
            other.asked.clear()
            with contextlib.redirect_stdout(io.StringIO()), http.drawing_downloads():
                first = outcome_of(get, server.url(kind))
                later = outcome_of(get, server.url("ok"))
                elsewhere = outcome_of(via_requests, other.url("ok"))
            check(f"{name}: after a {kind}, the host asked nothing more in the drawing ({later}, as the first: {first}); another host asked",
                  server.asked[kind] == 1 and server.asked["ok"] == 0 and later == first and elsewhere == "answered"
                  and other.asked["ok"] == 1, (dict(server.asked), dict(other.asked)))
            with contextlib.redirect_stdout(io.StringIO()), http.drawing_downloads():
                again = outcome_of(get, server.url("ok"))
            check(f"{name}: ... the next drawing asks it again", again == "answered" and server.asked["ok"] == 1, again)
        # A refused connection: nothing listens, so nothing counts; the second request fails at once (no connection tried).
        refused = refused_url()
        with contextlib.redirect_stdout(io.StringIO()), http.drawing_downloads():
            first = outcome_of(get, refused)
            began = time.monotonic()
            later = outcome_of(get, refused.replace("/refused", "/ok"))
            seconds = time.monotonic() - began
        check(f"{name}: after a refused connection, the host asked nothing more ({later} in {seconds:.2f} s)",
              later == first and seconds < 0.2, first)
        for kind in ("404", "reset", "503") + (("bad",) if get is via_urllib else ()):
            server.asked.clear()
            with contextlib.redirect_stdout(io.StringIO()), http.drawing_downloads():
                first = outcome_of(get, server.url(kind))
                later = outcome_of(get, server.url("ok"))
            check(f"{name}: after a {kind} ({first}), the host's other requests still made",
                  later == "answered" and server.asked["ok"] == 1, dict(server.asked))
    # Side by side (http.in_parallel): a request waiting its turn while the host hangs is not made.
    server.asked.clear()
    server.arrived.clear()

    def waits_its_turn() -> str:
        server.arrived.wait(5)  # the hang has reached the server, which holds the host's turn
        return outcome_of(via_requests, server.url("ok"))

    with contextlib.redirect_stdout(io.StringIO()), http.drawing_downloads():
        outcomes = http.in_parallel([lambda: outcome_of(via_requests, server.url("hang")), waits_its_turn])
    check(f"side by side: a request waiting its turn while the host hangs not made ({outcomes[1]})",
          server.asked["hang"] == 1 and server.asked["ok"] == 0 and outcomes[0] == outcomes[1] == "ReadTimeout",
          (outcomes, dict(server.asked)))
    # Outside a drawing (nothing to remember it in), each request is made.
    server.asked.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        outcome_of(via_requests, server.url("page"))
        outside = outcome_of(via_requests, server.url("ok"))
    check("outside a drawing: each request made", outside == "answered" and server.asked["ok"] == 1, dict(server.asked))
    http.RETRY_WAIT_SECONDS = config.RETRY_WAIT_SECONDS


def main() -> int:
    http._download_cache = None
    http._copies_folder = None
    http.HTTP_TIMEOUT_SECONDS = TIMEOUT  # FRED's reader reads it at each request
    server = Server()
    print(f"[requests] a server on 127.0.0.1:{server.port}; the program's timeout {TIMEOUT} s")
    check_retries(server)
    check_hosts(server, Server())
    passed = sum(RESULTS)
    print(f"[requests] {passed} of {len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
