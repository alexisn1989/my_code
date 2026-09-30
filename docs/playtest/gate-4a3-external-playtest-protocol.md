# Gate 4A3 external playtest — protocol

**Status: PREPARED, NOT RUN.** This document makes frozen plan §22 operational. Running it — recruiting
five people and observing them — is the user's to do, and its result is what moves Gate 4A3 from
*internally complete* to *externally accepted*. Nothing in this repository claims that result until it
exists.

## Who

- **Five** people unfamiliar with the codebase.
- **At least two** who do not play strategy games.
- Five **new** people each time the protocol is re-run; a tester is never reused.

## Setup — before the tester sits down

1. Install from the **release archive**, not the development tree, using only the archive's own
   `README.md`: the install command, then the run command. The archive is built by
   `scripts/build_release.py` and verified by `scripts/verify_release.py`.
2. Start a fresh save root per tester, so no tester sees another's campaign:
   `.venv/bin/mandate-gui --frontend-dist dist --scenario-root scenarios --save-root ./saves-tester-N`
3. Open `http://127.0.0.1:8420` in a browser, at a normal window size.
4. Leave the Title screen showing. Do not start the scenario for them.

## What the facilitator says — the whole of it

> "You govern this country. Start with the **Kingdom of Valdrun**. Play at least five turns. I can't
> help you once you've started — the game has its own help."

Then stop talking. The only help available is what the game itself offers: the *How to govern* note,
the Glossary, the goal card and the tooltips (§8.2). **No coaching, no hints, no answering questions
about the game.** If asked, say: "I can't help with that — use whatever the game shows you."

## During the session

Use one **observation sheet** per tester (`gate-4a3-observation-sheet.md`). Record, as it happens:

1. **Time to first confident decision** — from the first click on *Start* to the first time the tester
   commits a choice without hesitating over it. Note what the choice was.
2. **Every point of visible confusion** — the screen, the element, what they seemed to expect, and
   whether help existed there (a tooltip, the goal card, a Glossary entry) and went **unused**, or was
   genuinely **absent**.
3. **After every resolved turn**, ask exactly: *"What just happened, and why?"* Write down the answer
   verbatim. Afterwards compare it with that turn's **Why this happened** list on Turn result — the
   engine's actual reasons — and mark whether they match.
4. Whether they discover, **unprompted**, the trade-off between governing **by decree** and going
   **to the legislature**.
5. Whether they can say **what their political capital bought**.

## The fun gate — the primary result

At the end of the tester's **fifth** turn, ask exactly:

> "Do you want to play another turn?"

Record the **unprompted** answer — the first thing they say, before any follow-up. Do not rephrase, and
do not ask twice.

**Pass: at least three of five voluntarily want another turn.**

## If fewer than three of five want another turn

**Stop.** Do not add systems, screens or scenarios. Fix the decision-to-feedback loop and the help
surfaces instead — clarity of consequence, legibility of the trade-off, the weight of the result,
tooltip placement, goal-card wording — then re-run this protocol with **five new testers**.

## Recording the result

Collect the five sheets and complete the tally on the last sheet. The result — pass or fail, the
tally, and the sheets — is what the Gate 4A3 roadmap entry waits for. Until then the gate reads
**internally complete; externally pending**.
