"""The localhost security boundary.

This server is a **local single-player interface**, not a service. It binds
loopback and expects exactly one browser on the same machine. The checks here
exist because "only listening on 127.0.0.1" is not by itself sufficient: a page
on any website can make requests to `http://localhost:<port>`, and DNS rebinding
can make an attacker-controlled hostname resolve to loopback. Validating `Host`
and `Origin` is what closes that.

Deliberately NOT here: authentication, sessions, tokens, rate limiting. There is
one local user and no privilege boundary to enforce; adding a login screen to a
single-player desktop game would be security theatre. What the boundary actually
protects is "a web page you visited cannot drive your game".

`Host` and `Origin` allow-lists are **derived from the configured port**, never
hand-maintained, so a `--port` override cannot leave the previous port
authorised. Forwarded headers are ignored entirely: there is no proxy in front
of this process, so `X-Forwarded-Host` can only be an attacker's suggestion.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .errors import problem_response

#: Verbs that can change server state. `GET`/`HEAD` are exempt from the
#: Content-Type and Origin rules because they carry no body and cannot mutate.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Headers a reverse proxy would set. There is no proxy here, so a request
#: carrying one is either confused or hostile; either way it is ignored, never
#: preferred over the real `Host`.
UNTRUSTED_FORWARDING_HEADERS = ("x-forwarded-host", "x-forwarded-proto", "forwarded")

JSON_CONTENT_TYPE = "application/json"


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    """Host, Origin and Content-Type enforcement for a loopback-only server."""

    def __init__(
        self, app: ASGIApp, *, allowed_hosts: frozenset[str], allowed_origins: frozenset[str]
    ) -> None:
        super().__init__(app)
        self._allowed_hosts = allowed_hosts
        self._allowed_origins = allowed_origins

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.headers.get("host")
        if host is None or host.lower() not in self._allowed_hosts:
            # Covers missing, malformed, non-loopback and rebound hostnames in
            # one comparison, because the allowed set is exact strings.
            return _forbidden("host not permitted")

        origin = request.headers.get("origin")
        if origin is not None and origin.lower() not in self._allowed_origins:
            # `Origin: null` lands here too: sandboxed iframes and some file://
            # contexts send it, and no legitimate local client does.
            return _forbidden("origin not permitted")

        if request.method in MUTATING_METHODS:
            content_type = request.headers.get("content-type", "")
            if content_type.split(";")[0].strip().lower() != JSON_CONTENT_TYPE:
                return problem_response(
                    type_="unsupported_media_type",
                    title="Mutations must be JSON",
                    status=415,
                    detail="this endpoint accepts application/json only",
                )

        response = await call_next(request)
        # No CORS headers are ever added. Same-origin operation is the design:
        # Vite proxies /api in development, and the playtest build is served by
        # this same process, so there is nothing cross-origin to allow.
        return response


def _forbidden(detail: str) -> JSONResponse:
    """Deliberately terse: never echo the rejected value back to the caller."""
    return problem_response(
        type_="forbidden_origin", title="Request not permitted", status=403, detail=detail
    )
