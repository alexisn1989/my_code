# Gate 4A3 external playtest — facilitator kit for build `b3ac1a94…`

**Status: PREPARED, NOT RUN.**

The [protocol](gate-4a3-external-playtest-protocol.md) and the
[observation sheet](gate-4a3-observation-sheet.md) govern the playtest, and both are unchanged. This
kit only adds what is specific to the build:
- which archive to install, and how to check it;
- on which platform;
- where each thing the protocol names appears in this build;
- what to write on the sheets.

**It changes nothing about:**
- who is recruited;
- what the facilitator says;
- the questions asked;
- the scoring;
- the pass criterion (at least 3 of 5).

**The kit is never shown to testers.**

## 1. The build

| | |
|---|---|
| file | `mandate-gui-0.1.0.tar.gz` |
| SHA-256 | `b3ac1a946daaacac5bfbb635ee679aebb5e39608722626089d76160566d7a2b0` |
| built from | commit `8ba9ff7`, `SOURCE_DATE_EPOCH` 1791945066 |
| record | [`gate-4a3-rc-release-and-walkthroughs.md`](../reviews/gate-4a3-rc-release-and-walkthroughs.md) |
| approved | by the user, recorded in [`docs/roadmap.md`](../roadmap.md) (Gate 4A3 entry, `3f0c881`) |

**How it was checked before approval:**
- reproducible, and identical from a fresh clone;
- `verify_release` `PASSED`;
- against a fresh installation, the original installed walkthrough, the redesign walk and an
  enforced five-turn dry run each passed.

Those were internal runs. **They are not playtesters, and they do not count toward the playtest.**

## 2. Platform: Linux, or Windows through WSL 2

**The archive's own `README.md` gives Unix commands only:**
- `python3.11 -m venv .venv`, `.venv/bin/pip …` and `.venv/bin/mandate-gui …`;
- `sha256sum -c SHA256SUMS`.

**This build has been installed, served and played only on Linux.**

- **Supported for the playtest:**
  - **Linux**;
  - **Windows through WSL 2,** with a Linux distribution such as Ubuntu, running every command below
    inside the WSL shell, exactly as written.
- **Not supported for the playtest:** native Windows (PowerShell or cmd) and macOS. **They are
  unverified for this build.** No PowerShell commands are given, because none could be checked.
- **WSL 2 (unverified):** a Windows browser can usually reach a server running inside WSL 2 at
  `http://127.0.0.1:8420`, through WSL's localhost forwarding. If the page does not load, use a
  browser inside WSL instead.
- **Requirements, from the README:**
  - Python 3.11 or 3.12; Python 3.13 is not supported;
  - about 100 MB of disk for the virtual environment.

## 3. Getting the archive

1. **The file.** It was delivered alongside this kit, and is not stored in the repository.
2. **A rebuild,** if needed. This is the toolchain the approved archive was built with:
   - git;
   - Python 3.11 with `uv` (0.8.17 was used);
   - Node 22 with npm (22.22.2 and 10.9.7 were used).

   ```
   git clone <repository> mandate && cd mandate && git checkout 8ba9ff7
   (cd frontend && npm ci)
   python3 scripts/build_release.py --epoch 1791945066
   sha256sum dist/mandate-gui-0.1.0.tar.gz
   ```

**The SHA-256 decides.** Reproducibility was proven on the build machine. A different toolchain
can produce different bytes. **If the hash is not exactly the one in §1, do not use that archive.**
Use the delivered file instead.

## 4. Before each session (one fresh setup per tester)

From the directory holding the archive:

```
sha256sum mandate-gui-0.1.0.tar.gz
# must print b3ac1a946daaacac5bfbb635ee679aebb5e39608722626089d76160566d7a2b0
mkdir tester-N && tar -xzf mandate-gui-0.1.0.tar.gz -C tester-N && cd tester-N/mandate-gui-0.1.0
sha256sum -c SHA256SUMS
# every line must end in OK
python3.11 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt && .venv/bin/pip install --no-deps mandate_backend-0.1.0-py3-none-any.whl
.venv/bin/mandate-gui --frontend-dist dist --scenario-root scenarios --save-root ./saves-tester-N
```

- **The last command is the protocol's Setup step 2,** with a fresh save root per tester.
- **The port:** if port 8420 is taken, the game refuses to start and says so. Add `--port 8431` and
  open that port instead. The game never picks a different port on its own.
- **The browser:** open `http://127.0.0.1:8420` at a normal window size, and leave the Title screen
  showing. Do not start the scenario.
- **Stopping:** stop the server with **Ctrl+C** after the session.

## 5. What the protocol names, in this build

These are for the facilitator's own reference. **Nothing here is said to the tester**, because the
protocol's no-help rule stands.

| the protocol says | in this build |
|---|---|
| the *How to govern* note | the header's **"How to govern"** button. The note **starts closed**; the tester opens it |
| the Glossary | the header's **"Glossary"** button. It opens a Glossary panel under the header, and the button then reads "Close glossary" |
| the goal card | on the Dashboard, **"Your current priority"** (with its **"Build a decision"** button), beside **"Your campaign objective"** |
| the tooltips | e.g. hovering the header's **"Capital N / 1,000"** shows the Glossary's definition of political capital |
| the decree / legislature trade-off (§4 of the sheet) | the **"Legislative vote"** and **"Decree (N capital)"** choices under the selected proposal in **Decisions**. **Legislature** (Parliament) shows "No vote is held on a decree, so the legislature is bypassed." for a decree draft. In the Kingdom of Valdrun a budget can be decreed |
| what political capital bought (§5 of the sheet) | the header's **"Capital"**, and on the turn result the folded **"What your decision committed (N)"** |
| **Why this happened** (protocol step 3; sheet §3) | see §6 below |

## 6. Step 3, in this build: what to compare against

**Unchanged:**
- after every resolved turn, ask exactly: *"What just happened, and why?"*;
- write the answer **verbatim**;
- score it **yes / partly / no** in the sheet's §3, as before.

**Where the engine's reasons now are.** "Why this happened" listed the turn's reasons, apart from
routine steps. In this build the same reasons appear **once each**, in four places on the turn
result:
1. **the proposal card**, under "Turn outcome": the verdict word (for example "Enacted", "Did not
   carry" or "Enacted by decree"), and the reason lines on the card;
2. **"People and reactions"**;
3. **"How the blocs took it"**, inside People and reactions;
4. **"What else happened"**.

**Not part of the comparison,** as before: "Routine steps this turn", "What your decision committed",
"What did not change" and "Show exact values". All are folded.

**Recording.** In the sheet's §3 column "the engine's reasons (Turn result)", copy **each sentence
you compare against, verbatim, prefixed with its section name**, one per line.

**Examples.** The angle brackets mark only the shape of each line; copy the actual names and
figures from the screen.

```
Proposal card: "Enacted by decree — no vote was held."
Proposal card: "The legislature voted the budget down: <n> of <n> chambers carried."
People and reactions: "<leader> of the <party> backed the budget, for <price> political capital."
```

The first is the decree turn's exact wording. The second and third are a legislative turn's.

Then mark **match? (yes / partly / no)** exactly as the sheet says.

## 7. What the facilitator may see, and must not explain

These carried risks are open on this build ([roadmap](../roadmap.md), Gate 4A3 "Carried risks").
Note any you see on the sheet as observed, and **do not explain them to the tester**.

- **R1:** if one save folder holds many long saves, the saved-games list can take a second or two on
  its first load after the server starts. A fresh save root per tester keeps it short.
- **R2:** the Title screen's scenario list can occasionally be slow to appear.
- **R3:** History lists each turn as "Turn N — …", where N is the turn the result produced, one
  higher than the turn the tester just played.
- **R4:** foreign-assistance amounts are shown in minor units, 100 times the denar figure shown
  elsewhere.

**What is new since the previous playtest build (`083c7a98…`),** so nothing surprises the
facilitator:
- the Dashboard is an illustrated map, with a Places list beside it;
- Legislature is now the Parliament screen, with seat diagrams and bloc panels for bargains,
  influence and investment;
- there is an objective card, and the Constitution screen is a checklist;
- the turn result is reorganised (§6).

## 8. Recording

- **On every sheet's Archive row,** write exactly: `mandate-gui-0.1.0.tar.gz`, SHA-256
  `b3ac1a946daaacac5bfbb635ee679aebb5e39608722626089d76160566d7a2b0`.
- **Fill in the rest of the sheet and the tally exactly as the sheet instructs.**
- **The result goes to the user,** as the protocol describes. The repository claims no result until
  it exists. Until then, the gate reads **internally complete; externally pending**.
