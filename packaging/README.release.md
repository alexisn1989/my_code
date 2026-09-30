# MANDATE {version} — local playtest build

MANDATE is a political strategy game you play in your browser. It runs entirely on your own
computer: a small local server, reached only from this machine.

## Requirements

- **Python 3.11 or 3.12.** Python 3.13 is not supported yet. Check with `python3.11 --version`, or
  use `python3.12` in the first command below if that is what you have.
- About 100 MB of disk for the virtual environment.

## Install and run — two commands, from this directory

```
python3.11 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt && .venv/bin/pip install --no-deps {wheel}
.venv/bin/mandate-gui --frontend-dist dist --scenario-root scenarios
```

Then open **http://127.0.0.1:8420** in a browser and choose a scenario.

- `--require-hashes` installs exactly the pinned, hash-checked versions in `requirements.txt` and
  nothing else.
- Stop the game with **Ctrl+C** in the terminal.
- If port 8420 is taken, add `--port 8431` (or any free port) to the second command. The game never
  picks a different port on its own.
- Saved games are written to `~/.mandate/saves` by default; pass `--save-root <directory>` to put them
  elsewhere.

## What is in this archive

| path | what it is |
|---|---|
| `{wheel}` | the game engine and local server |
| `requirements.txt` | the exact, hash-pinned runtime dependencies |
| `dist/` | the browser interface |
| `scenarios/` | the three scenarios: `decree_state`, `deficit_demo`, `tiny_valid` |
| `SHA256SUMS` | a checksum for every other file here: `sha256sum -c SHA256SUMS` |

The server binds to 127.0.0.1 only and refuses requests from any other host or web page. Nothing is
sent anywhere else.
