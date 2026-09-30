"""Gate 4A3 Commit 6: the security boundary and the startup promises, against a RUNNING server.

Every other API test drives the ASGI app through `TestClient`, which never opens a socket. That proves
the middleware's logic; it cannot prove what a real listener does -- which address it binds, what a raw
request with no `Host` reaches, whether a second launch on a bound port fails fast, or whether SIGINT
shuts it down. This module starts the real `mandate-gui` console script from the active environment
and talks to it over real sockets.

The frontend build is a one-line temporary `index.html`, so this module never depends on
`npm run build` having been run.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.api.security import UNTRUSTED_FORWARDING_HEADERS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "data" / "scenarios"
ENTRY_POINT = Path(sys.executable).parent / "mandate-gui"
STARTUP_TIMEOUT_S = 20.0
EXIT_TIMEOUT_S = 10.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _raw_request(port: int, request: bytes, *, host: str = "127.0.0.1") -> tuple[int, bytes]:
    """Send bytes exactly as given and return (status, raw response). No client library, so
    nothing adds or normalises a header on the way out."""
    with socket.create_connection((host, port), timeout=5) as conn:
        conn.sendall(request)
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    match = re.match(rb"HTTP/1\.[01] (\d{3})", raw)
    assert match, f"not an HTTP response: {raw[:200]!r}"
    return int(match.group(1)), raw


def _get(port: int, path: str, headers: dict[str, str]) -> int:
    lines = [f"GET {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in headers.items()]
    lines.append("Connection: close")
    status, _ = _raw_request(port, ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    return status


def _post(port: int, path: str, headers: dict[str, str], body: bytes = b"{}") -> int:
    lines = [f"POST {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in headers.items()]
    lines += ["Content-Type: application/json", f"Content-Length: {len(body)}", "Connection: close"]
    status, _ = _raw_request(port, ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
    return status


def _start(port: int, tmp: Path) -> subprocess.Popen[bytes]:
    dist = tmp / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<!doctype html><title>live-server test</title>\n")
    return subprocess.Popen(
        [
            str(ENTRY_POINT),
            "--port",
            str(port),
            "--frontend-dist",
            str(dist),
            "--scenario-root",
            str(SCENARIO_ROOT),
            "--save-root",
            str(tmp / "saves"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def _wait_ready(proc: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        assert proc.poll() is None, f"mandate-gui exited early: {proc.stderr.read()!r}"  # type: ignore[union-attr]
        try:
            if _get(port, "/api/scenarios", {"Host": f"127.0.0.1:{port}"}) == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError("mandate-gui did not become ready")


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    assert ENTRY_POINT.is_file(), f"the console script is not installed at {ENTRY_POINT}"
    port = _free_port()
    proc = _start(port, tmp_path_factory.mktemp("live"))
    try:
        _wait_ready(proc, port)
        yield port
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=EXIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()


# ------------------------------------------------------------------ loopback binding


def _listening_addresses(port: int) -> set[str]:
    """Local IPv4 addresses with a LISTEN socket on `port`, read from the kernel's own table."""
    found: set[str] = set()
    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        local, state = fields[1], fields[3]
        address_hex, port_hex = local.split(":")
        if state != "0A" or int(port_hex, 16) != port:
            continue
        octets = bytes.fromhex(address_hex)[::-1]
        found.add(".".join(str(b) for b in octets))
    return found


def _non_loopback_ipv4() -> list[str]:
    trie = Path("/proc/net/fib_trie").read_text()
    local = set(re.findall(r"\|-- ([0-9.]+)\n\s+/32 host LOCAL", trie))
    return sorted(a for a in local if not a.startswith("127."))


@pytest.mark.skipif(not Path("/proc/net/tcp").exists(), reason="needs Linux /proc/net/tcp")
def test_the_listener_is_bound_to_loopback_only(server: int) -> None:
    assert _listening_addresses(server) == {"127.0.0.1"}


@pytest.mark.skipif(
    not Path("/proc/net/fib_trie").exists(), reason="needs Linux /proc/net/fib_trie"
)
def test_no_non_loopback_address_of_this_host_reaches_it(server: int) -> None:
    addresses = _non_loopback_ipv4()
    if not addresses:
        pytest.skip("this host has no non-loopback IPv4 address to try; recorded, not passed")
    for address in addresses:
        with pytest.raises(OSError):
            socket.create_connection((address, server), timeout=2).close()


# ------------------------------------------------------------------ Host


def test_the_two_loopback_hosts_are_served(server: int) -> None:
    assert _get(server, "/api/scenarios", {"Host": f"127.0.0.1:{server}"}) == 200
    assert _get(server, "/api/scenarios", {"Host": f"localhost:{server}"}) == 200


def test_a_request_with_no_host_is_refused(server: int) -> None:
    # HTTP/1.0 is the only way to send no Host at all: HTTP/1.1 makes it mandatory.
    status, _ = _raw_request(server, b"GET /api/scenarios HTTP/1.0\r\n\r\n")
    assert status == 403


@pytest.mark.parametrize(
    "host",
    [
        "evil.example.com",
        "attacker.example:{port}",  # DNS-rebinding shape: a hostile name that resolved to loopback
        "127.0.0.1:{other}",  # the right address on a port this server was not started on
        "127.0.0.1",  # no port at all
        "127.0.0.1:{port}.evil.example",  # suffix trick
        "LOCALHOST.:{port}",  # trailing-dot spelling
    ],
)
def test_every_other_host_is_refused(server: int, host: str) -> None:
    value = host.format(port=server, other=server + 1)
    assert _get(server, "/api/scenarios", {"Host": value}) == 403


# ------------------------------------------------------------------ Origin


def test_a_null_origin_is_refused_on_reads_and_on_mutations(server: int) -> None:
    """`security.py`'s comment used to say GET is exempt from the Origin rule. It never was, and
    this proves the stricter behaviour the code actually has, for both verbs."""
    good_host = {"Host": f"127.0.0.1:{server}"}
    assert _get(server, "/api/scenarios", {**good_host, "Origin": "null"}) == 403
    assert _post(server, "/api/game/new", {**good_host, "Origin": "null"}) == 403


def test_a_foreign_origin_is_refused_and_the_own_origin_is_not(server: int) -> None:
    good_host = {"Host": f"127.0.0.1:{server}"}
    assert (
        _get(server, "/api/scenarios", {**good_host, "Origin": "https://evil.example.com"}) == 403
    )
    assert (
        _get(server, "/api/scenarios", {**good_host, "Origin": f"http://127.0.0.1:{server}"}) == 200
    )


# ------------------------------------------------------------------ forwarded headers


@pytest.mark.parametrize("header", UNTRUSTED_FORWARDING_HEADERS)
def test_forwarded_headers_never_override_the_real_host(server: int, header: str) -> None:
    """Iterates the module's own constant, so every header it names is proved ignored and the
    constant cannot drift from behaviour."""
    hostile = "host=evil.example.com" if header == "forwarded" else "evil.example.com"
    good = f"host=127.0.0.1:{server}" if header == "forwarded" else f"127.0.0.1:{server}"
    # A good Host with a hostile forwarded value is still served...
    assert _get(server, "/api/scenarios", {"Host": f"127.0.0.1:{server}", header: hostile}) == 200
    # ...and a hostile Host is refused however friendly the forwarded value looks.
    assert _get(server, "/api/scenarios", {"Host": "evil.example.com", header: good}) == 403


# ------------------------------------------------------------------ F12: startup and shutdown


def test_a_second_launch_on_a_bound_port_fails_fast_and_names_the_port(
    server: int, tmp_path: Path
) -> None:
    started = time.monotonic()
    second = _start(server, tmp_path)
    try:
        _, stderr = second.communicate(timeout=EXIT_TIMEOUT_S)
    finally:
        if second.poll() is None:
            second.kill()
    elapsed = time.monotonic() - started
    message = stderr.decode()
    assert second.returncode == 1
    assert elapsed < EXIT_TIMEOUT_S
    assert str(server) in message and "--port" in message
    # No auto-increment: nothing took the next port instead.
    assert not _listening(server + 1)
    # And the first server is untouched.
    assert _get(server, "/api/scenarios", {"Host": f"127.0.0.1:{server}"}) == 200


def _stop(proc: subprocess.Popen[bytes]) -> int:
    proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout=EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("mandate-gui did not stop within the timeout after SIGINT") from None


def test_sigint_shuts_down_cleanly_and_the_same_port_restarts_at_once(tmp_path: Path) -> None:
    """The property a player needs from Ctrl+C: it exits 0, and `mandate-gui` can be started again on
    the same port straight away."""
    port = _free_port()
    first = _start(port, tmp_path)
    try:
        _wait_ready(first, port)
    finally:
        returncode = _stop(first)
    assert returncode == 0
    second = _start(port, tmp_path)
    try:
        _wait_ready(second, port)
    finally:
        assert _stop(second) == 0


def test_a_restart_is_not_refused_after_the_server_closed_a_connection(tmp_path: Path) -> None:
    """Gate 4A3 Commit 6, the defect this module found while it was being written.

    A `Connection: close` request makes the SERVER close the socket, which leaves TIME_WAIT on the
    server's own port -- exactly what shutting down with a browser open does. The startup probe bound
    with SO_REUSEADDR=0 and so reported the port "already in use ... Stop the other process" for up
    to a minute after a clean Ctrl+C, when no other process existed."""
    port = _free_port()
    first = _start(port, tmp_path)
    try:
        _wait_ready(first, port)
        assert _get(port, "/api/scenarios", {"Host": f"127.0.0.1:{port}"}) == 200
    finally:
        assert _stop(first) == 0
    second = _start(port, tmp_path)
    try:
        _wait_ready(second, port)
    finally:
        assert _stop(second) == 0
