"""Gate 4A1: the localhost security boundary, port collision, and startup.

Covers `LocalSecurityMiddleware` (Host/Origin allow-listing, JSON-only
mutations, no CORS) against the REAL ASGI application, and `mandate-gui`'s
socket, startup failures with a real (empty) directory, and single-worker
guarantees. No timing sleeps anywhere: a real bound socket proves collision,
a real (empty) directory proves the missing-build failure, and configuration
assertions -- not a running server -- prove the worker/bind rules.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.main import (
    ApiSettings,
    FrontendBuildMissingError,
    PortInUseError,
    _settings_from_args,
    build_argument_parser,
    create_app,
    probe_port_available,
    require_frontend_build,
    run,
    run_server,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
DEFAULT_ORIGIN = "http://127.0.0.1:8420"


def _frontend_dist_with_build(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>MANDATE</title>", encoding="utf-8")
    return dist


def _build_app(tmp_path: Path, **overrides: Any) -> FastAPI:
    settings = ApiSettings(
        save_root=tmp_path / "saves",
        scenario_root=SCENARIO_DIR,
        serve_spa=False,
        **overrides,
    )
    return create_app(settings)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(_build_app(tmp_path), base_url=DEFAULT_ORIGIN) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Host
# --------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1:8420", "localhost:8420"])
def test_accepted_loopback_hosts(client: TestClient, host: str) -> None:
    response = client.get("/api/scenarios", headers={"host": host})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example.com",
        "127.0.0.1:9999",  # wrong port
        "localhost:9999",  # wrong port
        "127.0.0.1.evil.com:8420",  # rebinding-shaped
        "",
    ],
)
def test_rejected_hosts(client: TestClient, host: str) -> None:
    response = client.get("/api/scenarios", headers={"host": host})
    assert response.status_code == 403
    assert response.json()["type"] == "forbidden_origin"


# --------------------------------------------------------------------------
# Origin
# --------------------------------------------------------------------------


def test_same_origin_mutation_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/game/new",
        json={"scenario_id": "decree_state"},
        headers={"origin": DEFAULT_ORIGIN},
    )
    assert response.status_code == 200


def test_absent_origin_is_accepted_for_local_tools(client: TestClient) -> None:
    """A bare `curl` sends no Origin at all -- Host and Content-Type still apply."""
    response = client.post("/api/game/new", json={"scenario_id": "decree_state"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example.com",
        "https://127.0.0.1:8420",  # wrong scheme
        "http://127.0.0.1:9999",  # wrong port
        "null",
    ],
)
def test_hostile_origin_is_rejected(client: TestClient, origin: str) -> None:
    response = client.post(
        "/api/game/new", json={"scenario_id": "decree_state"}, headers={"origin": origin}
    )
    assert response.status_code == 403
    assert response.json()["type"] == "forbidden_origin"


def test_an_explicitly_configured_dev_origin_is_accepted(tmp_path: Path) -> None:
    app = _build_app(tmp_path, dev_origin="http://localhost:5173")
    with TestClient(app, base_url=DEFAULT_ORIGIN) as dev_client:
        response = dev_client.post(
            "/api/game/new",
            json={"scenario_id": "decree_state"},
            headers={"origin": "http://localhost:5173"},
        )
        assert response.status_code == 200


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------


def test_no_wildcard_cors_header_is_ever_sent(client: TestClient) -> None:
    response = client.get("/api/scenarios", headers={"origin": DEFAULT_ORIGIN})
    assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


def test_no_wildcard_cors_in_the_source() -> None:
    source = Path(REPO_ROOT / "backend" / "app" / "api" / "security.py").read_text(encoding="utf-8")
    assert "CORSMiddleware" not in source
    assert "allow_origins" not in source
    assert 'Access-Control-Allow-Origin", "*"' not in source


# --------------------------------------------------------------------------
# Content-Type
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]
)
def test_mutations_reject_non_json_content_types(client: TestClient, content_type: str) -> None:
    response = client.post(
        "/api/game/new",
        content=b'{"scenario_id": "decree_state"}',
        headers={"content-type": content_type},
    )
    assert response.status_code == 415
    assert response.json()["type"] == "unsupported_media_type"


def test_get_requests_need_no_content_type(client: TestClient) -> None:
    response = client.get("/api/scenarios")
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Save security and error hygiene, re-asserted through this real app
# --------------------------------------------------------------------------


@pytest.mark.parametrize("attempt", ["../../etc/passwd", "/etc/passwd", "not-a-uuid", ".."])
def test_traversal_shaped_save_ids_are_refused_without_a_traceback(
    client: TestClient, attempt: str
) -> None:
    response = client.post("/api/game/load", json={"save_id": attempt})
    assert response.status_code == 400
    assert "Traceback" not in response.text
    assert str(REPO_ROOT) not in response.text


def test_no_raw_report_endpoint_exists(client: TestClient) -> None:
    for path in ("/api/report", "/api/raw-report", "/api/debug", "/api/game/report"):
        assert client.get(path).status_code == 404


def test_unexpected_failures_stay_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _build_app(tmp_path)
    # TestClient's default re-raises unhandled exceptions instead of letting the
    # catch-all handler answer, so this one test builds its own client.
    with TestClient(app, base_url=DEFAULT_ORIGIN, raise_server_exceptions=False) as raw_client:

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr("app.api.routes.load_scenario_file", explode)
        response = raw_client.post("/api/game/new", json={"scenario_id": "decree_state"})

        assert response.status_code == 500
        body = response.json()
        assert body["type"] == "internal_error"
        # No stack trace and no application source path -- `detail` carries only
        # the exception's own message (errors.py's documented, deliberate trade).
        assert "Traceback" not in response.text
        assert 'File "' not in response.text
        assert str(REPO_ROOT / "backend" / "app") not in response.text


# --------------------------------------------------------------------------
# Startup: port collision and the frontend build
# --------------------------------------------------------------------------


def test_probe_detects_a_bound_port() -> None:
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        with pytest.raises(PortInUseError):
            probe_port_available("127.0.0.1", port)
    finally:
        holder.close()


def test_probe_succeeds_on_a_free_port() -> None:
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    port = holder.getsockname()[1]
    holder.close()  # released -- the port is free again

    probe_port_available("127.0.0.1", port)  # must not raise


def test_run_exits_cleanly_on_a_taken_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    dist = _frontend_dist_with_build(tmp_path)
    try:
        with pytest.raises(SystemExit) as excinfo:
            run(["--port", str(port), "--frontend-dist", str(dist)])
        assert excinfo.value.code == 1
    finally:
        holder.close()


def test_require_frontend_build_names_the_exact_fix(tmp_path: Path) -> None:
    with pytest.raises(FrontendBuildMissingError, match="npm ci && npm run build"):
        require_frontend_build(tmp_path / "does-not-exist")


def test_require_frontend_build_passes_when_index_html_exists(tmp_path: Path) -> None:
    dist = _frontend_dist_with_build(tmp_path)
    require_frontend_build(dist)  # must not raise


def test_creating_the_app_with_a_missing_build_fails_at_construction(tmp_path: Path) -> None:
    settings = ApiSettings(
        save_root=tmp_path / "saves",
        scenario_root=SCENARIO_DIR,
        frontend_dist=tmp_path / "no-such-dist",
        serve_spa=True,
    )
    with pytest.raises(FrontendBuildMissingError):
        create_app(settings)


def test_the_greybox_is_served_when_the_build_exists(tmp_path: Path) -> None:
    dist = _frontend_dist_with_build(tmp_path)
    settings = ApiSettings(
        save_root=tmp_path / "saves",
        scenario_root=SCENARIO_DIR,
        frontend_dist=dist,
        serve_spa=True,
    )
    app = create_app(settings)
    with TestClient(app, base_url=DEFAULT_ORIGIN) as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        assert "MANDATE" in response.text
        # Never served the /api/* namespace, which is registered first.
        assert test_client.get("/api/scenarios").status_code == 200


def test_run_exits_cleanly_when_the_frontend_build_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    # A guaranteed-free port: bind-then-release rather than a hardcoded number.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    with pytest.raises(SystemExit) as excinfo:
        run(["--port", str(port), "--frontend-dist", str(tmp_path / "no-such-dist")])
    assert excinfo.value.code == 1


# --------------------------------------------------------------------------
# Startup: bind address, single worker
# --------------------------------------------------------------------------


def test_default_bind_host_is_loopback_never_all_interfaces() -> None:
    assert ApiSettings().bind_host == "127.0.0.1"
    assert ApiSettings().bind_host != "0.0.0.0"  # noqa: S104


def test_the_argument_parser_exposes_no_workers_flag() -> None:
    """There is no way to ask for more than one worker -- by omission, not a rejected flag."""
    parser = build_argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--workers", "4"])


def test_run_server_always_configures_exactly_one_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = _frontend_dist_with_build(tmp_path)
    settings = ApiSettings(
        save_root=tmp_path / "saves", scenario_root=SCENARIO_DIR, frontend_dist=dist
    )
    captured: dict[str, Any] = {}

    def fake_run(app: object, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("app.api.main.uvicorn.run", fake_run)
    run_server(settings)

    assert captured["workers"] == 1
    assert captured["host"] == "127.0.0.1"


def test_settings_from_args_apply_a_port_override_to_the_whole_allowed_set() -> None:
    settings = _settings_from_args(["--port", "9001"])
    assert settings.port == 9001
    assert settings.allowed_hosts == {"127.0.0.1:9001", "localhost:9001"}
    assert settings.allowed_origins == {"http://127.0.0.1:9001", "http://localhost:9001"}


def test_a_failed_startup_never_touches_the_save_root(tmp_path: Path) -> None:
    save_root = tmp_path / "saves"
    with pytest.raises(SystemExit):
        run(
            [
                "--save-root",
                str(save_root),
                "--frontend-dist",
                str(tmp_path / "no-such-dist"),
            ]
        )
    # The failure is reported before `create_app` (and therefore the
    # `SaveRepository`) is ever constructed, so nothing was created on disk.
    assert not save_root.exists()


def test_run_server_starts_no_docker_or_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source scan: no container, database, auth, cloud, or telemetry client."""
    source = (REPO_ROOT / "backend" / "app" / "api" / "main.py").read_text(encoding="utf-8")
    for forbidden in ("docker", "sqlalchemy", "psycopg", "boto3", "sentry", "posthog", "oauth"):
        assert forbidden not in source.lower()
