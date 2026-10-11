"""Start ONE build's API server for the timing check. usage: serve.py <backend-dir> <scenario-dir> <save-root> <port>
Identical settings for every build: loopback, one worker (run_server), SPA serving off (the measured
endpoint does not involve it). Asserts the imported app comes from <backend-dir>."""
import os, sys
backend, scenarios, save_root, port = sys.argv[1:5]
sys.path.insert(0, backend)
import app
assert os.path.realpath(app.__file__).startswith(os.path.realpath(backend)), app.__file__
print("app from", app.__file__, flush=True)
from pathlib import Path
from app.api.main import ApiSettings, run_server
run_server(ApiSettings(save_root=Path(save_root), scenario_root=Path(scenarios), port=int(port), serve_spa=False))
