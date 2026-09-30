# Gate 4A3 Commit 6 — the `GET /api/saves` budget: FAILED, WAIVED BY USER RULING

**Status: FAILED — WAIVED BY USER RULING.**

The read-projection budget has a STOP threshold of **200 ms**. `GET /api/saves` exceeds it. That
budget **failed**. The user's ruling **waived** the failure so that the rest of Commit 6 could land.
It did **not** turn the budget into a pass, reclassify it, or move its threshold. Nothing in this
repository may describe it as passing.

Landed as a forward-only correction in Commit 6a. Commit 6 (`fb19b5f0`) is not amended.

---

## 1. The failure, as measured

| run | artifact | `/api/saves` median | `/api/saves` worst | STOP |
|---|---|---:|---:|---:|
| clean measurement put to the user, 23 saves on disk | (the question below) | 211 ms | 248 ms | 200 ms |
| Commit 6 verification, packaged instance | `gate-4a3-commit6-budgets.json` | 196.39 ms | 245.25 ms (245–314 ms across all Commit 6 runs) | 200 ms |
| Commit 6a re-run, same archive (`54290cca…`) | `gate-4a3-commit6a-budgets.json` | 232.02 ms | 278.81 ms | 200 ms |

**Cause:** `list_saves` replays `validate_history` on every save file on every listing. Cost therefore
grows with the number of saves multiplied by their length. Every new game writes a save, so ordinary
play makes it worse over time.

**Why it was not fixed in Commit 6:** frozen section 18 makes a STOP breach stop-and-report. It
forbids fixing one with caching or weakened validation.

## 2. The ruling, verbatim

Asked through the question tool on **2026-09-30** (01:13:51Z), answered 01:14:17Z.

**Question:**

> GET /api/saves breaches its 200 ms STOP (median 211 ms, worst 248 ms, clean run, 23 saves on disk).
> Cause: every listing fully replays validate_history on EVERY save file, so cost grows with the number
> of saves times their length — and every new game writes a save, so real play makes it worse over
> time. The frozen plan forbids fixing a breach with caching or weaker validation. How should Commit 6
> handle it?

**The four options offered:**

1. **Record breach, ship rest (Recommended)** — "Commit 6 lands packaging/security/everything else; the
   budget artifact records /api/saves as a STOP breach verbatim, the roadmap says 'internally complete
   except the /api/saves budget', and the fix becomes its own follow-up decision. Honors the frozen rule
   exactly; nothing is weakened or reclassified."
2. **Validate on load only** — "Listing checks each save's envelope and hash chain but no longer replays
   it; a full validate_history still runs on load, so nothing unvalidated is ever played. Fast and
   bounded, but the list's 'loadable' flag becomes a weaker claim than today — a validation change the
   frozen rule forbids without your say-so."
3. **Content-keyed memo** — "Remember each save's validation result keyed by the SHA-256 of its file
   bytes, so an unchanged file is never replayed twice and any change re-validates. Sound because
   validation is a pure function of the bytes — but it is caching, which the frozen rule names
   explicitly."
4. **Separate listing budget** — "Treat listings (/api/saves, /api/scenarios) as a separate row with a
   per-save threshold instead of the 200 ms projection row. Resolves it on paper by reclassifying — the
   kind of exclusion-broadening the standing rules warn against."

**Answer chosen:** *"Record breach, ship rest (Recommended)"*.

## 3. What the waiver covers, and what it does not

**Covers:** exactly one failed budget, the `read_projection_ms` STOP breach, and only from
`GET /api/saves`. `scripts/verify_release.py` enforces that narrowness in `ruled_breach_only()`. The
run is accepted only when `read_projection_ms` is the sole breached budget **and** `/api/saves` is the
sole endpoint over its STOP. In that case the release record writes `"verdict": "FAILED_WAIVED"`,
names the endpoint, and links this document.

**Does not cover:**

- **Any other budget.** A breach anywhere else fails the verification run.
- **Any other endpoint.** This includes `GET /api/scenarios`, which runs close to the same STOP: worst
  198.9 ms in one Commit 6 run, 177.34 ms in the committed Commit 6 artifact, 174.74 ms in the
  6a re-run. If it ever crosses 200 ms, the run fails, and this waiver does not extend to it.
- **The fix.** The fix stays owed and needs its own decision. The three options not chosen above
  (validate on load only, a content-keyed memo, a separate listing budget) each need the user's
  explicit say-so, because each weakens validation, caches, or reclassifies.

**What ends the waiver:** a follow-up decision on the fix, once it is implemented and measured under
the 200 ms STOP.

## 4. Addendum — the three loose phrasings in Commit 6's record, corrected here

Commit 6's committed evidence is left byte-identical as the record of that run. It said three things
too loosely, and this document is the correction.

1. **"STOP — recorded by ruling"** (and "One breach, recorded by the user's ruling") in
   `gate-4a3-commit6-packaging.md`, and **"one budget breach recorded"** in `docs/roadmap.md`. These
   describe a failure without using the word. The correct status is **FAILED — WAIVED BY USER
   RULING**. The roadmap is corrected in Commit 6a; the packaging record is not edited.
2. **The `knownBreach: true` field** in `gate-4a3-commit6-release.json`. It records that the run
   matched the ruled exception, but not that a budget failed. From Commit 6a on, `verify_release.py`
   writes `verdict` (`"FAILED_WAIVED"` or `"PASSED"`), `waivedEndpoint` and `waiver` in its place. See
   `gate-4a3-commit6a-release.json`, produced from the same archive, SHA-256
   `54290ccaebc66f3146b75e2869921972008570b7d9807977c83f4ed9eba7379b`.
3. **The browser reruns' exit codes were not in the repository.** They lived only in `/tmp` logs and
   harness task files, both ephemeral. The same was true of Commit 5b. All twelve are now in
   `gate-4a3-commit6-browser-reruns.json`, with their log tails in
   `gate-4a3-commit6-browser-reruns.log.txt`.

   Each rerun artifact there carries exactly one of three dispositions:
   - **byte-identical** to its predecessor;
   - **measurements unchanged, bytes differ, with the reason** — Commit 6's campaigns evidence differs
     in exactly two fields, the built asset filenames;
   - **reproduced byte-for-byte in place** — the seated stress artifact.

   That replaces the overbroad summary "every piece of evidence matches exactly".

The gate's status is unchanged: **internally complete; externally pending**. It now also reads **one
budget FAILED and waived by user ruling**.
