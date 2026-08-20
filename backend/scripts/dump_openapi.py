"""Emit the local game API's OpenAPI schema, offline, for `openapi-typescript`.

Gate 4A2 (frozen plan Sec 14.3 / R13): the frontend's generated types must come
from the REAL application's own schema, not a hand-maintained sketch. This
script builds the same `FastAPI` app `mandate-gui` serves and calls its own
`.openapi()` method directly -- no server process, no network socket, no
`frontend/dist` requirement (`serve_spa=False`), so it runs identically in CI
and locally and produces a deterministic, git-diffable JSON file.

Usage: `uv run python scripts/dump_openapi.py > ../docs/contracts/phase4a-openapi.json`
(invoked by `frontend`'s `npm run generate:api`; see that script for the exact
path). Never hand-edit the output -- regenerate it instead.
"""

from __future__ import annotations

import json
import sys

from app.api.main import ApiSettings, create_app


def main() -> None:
    # A representative save/scenario root is enough: the schema is determined
    # by the route/model declarations, not by what data exists on disk. The
    # real repo's scenario dir is used anyway (the default) so the /scenarios
    # response model stays exercised at import time, but no request is made.
    settings = ApiSettings(serve_spa=False)
    app = create_app(settings)
    schema = app.openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
