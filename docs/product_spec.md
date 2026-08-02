# MANDATE — Product Specification

> Source of truth for design intent. This document is derived from the original master build
> brief supplied to the project and is kept in the repository so later work can be checked against
> it without depending on external chat history. Section numbers match the original brief.

## 1. Role and working method

The team building MANDATE acts as game designer, systems designer, full-stack architect, backend
engineer, frontend engineer, database engineer, UI/UX designer, and QA lead simultaneously. MANDATE
is a polished, playable, single-player political strategy game. The player governs a fictional
country: economy, political system, population groups, institutions, diplomacy, trade, alliances,
and war. The central challenge is not making the country powerful — it is **remaining in power**
while living with the consequences of every decision.

Work proceeds in controlled phases (see `roadmap.md`). Each phase builds a working, tested slice
before the next begins. When requirements conflict, priority order is:

1. A playable and understandable game loop.
2. Deterministic, correct simulation behavior.
3. Player decisions with meaningful tradeoffs.
4. Save-game integrity and test coverage.
5. Clear UI and strong feedback.
6. Content quantity and visual polish.

No feature is described as working until it is implemented and verified.

## 2. Product vision

MANDATE is a turn-based political survival and nation-management strategy game, combining the
accessibility of a management dashboard with the strategic depth of grand strategy. The world is
fictional and procedurally/seed-generated — no real leaders, parties, or exact real countries.

Representative player dilemmas: raise taxes vs. business/elite backlash; cut spending vs.
unemployment and strikes; expand voting rights vs. weakened control; restrict the press vs.
long-term corruption and unrest; fund the military vs. coup risk; subsidize essentials vs. treasury
strain; sign trade deals that grow the economy but hurt protected industries; join alliances that
trade security for independence; go to war and accept casualties, debt, and backlash for strategic
gain.

Target feeling: *"I solved one problem, but my solution changed the political balance and created
two new problems."*

## 3. Design pillars

**3.1 Political survival is the objective.** Retaining power depends on regime type: democracies
need elections, legislative support, and constitutional compliance; monarchies need legitimacy,
succession stability, and court/military/traditional support; military regimes need officer
loyalty and factional balance; one-party states need party unity and control of challengers;
theocracies need clerical legitimacy; hybrid regimes depend on overlapping sources of power.
Removal from office can come via election, impeachment, party challenge, coup, revolution, forced
abdication, assassination, foreign occupation, or state collapse. In the initial release, losing
office ends the game (opposition-continuation is a deferred idea, §41).

**3.2 Government design changes mechanics**, not just labels. Constitutional rules determine leader
selection, term structure, lawmaking, vetoes, judicial selection, regional governance, press/
opposition legality, military control, removal mechanisms, and legitimacy sources.

**3.3 The population is not one approval number.** It is modeled as groups with distinct interests;
national approval is a derived, population-weighted summary. Initial groups: urban workers, rural
farmers, middle class/professionals, business owners, industrialists/elites, public-sector
employees, students/young adults, retirees, religious conservatives, secular progressives,
ethnic/regional minorities, military families/veterans. Each group has size, influence/turnout,
economic interests, ideology, trust, approval, radicalization, organization, and issue salience.
Groups are exclusive simulation segments initially, to avoid double-counting.

**3.4 Institutions have independent power**, distinct from population groups: executive,
legislature, judiciary, military, civil service, police/internal security, central bank, state
media, independent press, organized labor, business council, religious establishment, regional
governments. Each has loyalty, power, competence, corruption, independence, resources, and
leadership. An institution can support the player while being inefficient or corrupt.

**3.5 Every important result must be explainable.** Approval and GDP changes show contributing
factors; coup risk shows visible warning signs. Randomness creates uncertainty, not unexplained
punishment.

**3.6 The simulation should create stories** — emergent political narratives arising from the
interaction of systems, not scripted plot.

## 4–37. Full system specification

The remaining subject areas — technical stack, engineering rules, world model, calendar/turn
structure, core game state, constitutional system, political capital, population simulation,
parties/legislature, economy, public services, policy system, diplomacy, trade, military/war,
coups/revolutions, elections, leaders/cabinet, events, technology, AI countries, intelligence/fog
of war, UI, visual direction, accessibility, persistence, API design, security, testing strategy,
balance/observability, difficulty, tutorial, and the initial scenario ("The Arken Crisis") — are
authoritative as originally specified and are tracked section-by-section in `roadmap.md` against
the phase that implements each one. They are not restated in full here to avoid the spec and the
roadmap drifting apart; `roadmap.md` §references map 1:1 to the numbered sections of the original
brief. Nothing in this project should implement a system in a way that contradicts those numbered
sections without an explicit, documented decision (see `docs/adr/`).

## 38. Vertical slice definition of done

A new player can: start *The Arken Crisis*; understand the country's major problems; make
domestic, economic, diplomatic, and military decisions; end at least four turns; see understandable
consequences; experience at least one crisis or event chain; save and resume; win or lose political
support based on decisions rather than scripted outcomes.

## 41. Explicitly deferred

Multiplayer diplomacy, cooperative cabinet mode, opposition-party continuation after losing office,
procedural world generation, scenario/mod editor, Steam packaging, mobile layout, espionage
networks, civil wars with multiple internal actors, international organizations, climate/long-term
environment systems, detailed naval logistics, currency unions, colonial/historical scenarios,
workshop content sharing, optional locally generated newspaper flavor text. Architecture should
avoid obvious dead ends against these, without building unused abstraction now.

## 42. Final product standard

MANDATE succeeds if players can understand their country's condition, make politically meaningful
decisions, see how groups and institutions respond, and experience an evolving story produced by
the simulation. No government form or economic policy is presented as objectively correct — every
system has advantages, weaknesses, supporters, opponents, and transition costs. Outcomes emerge
from conditions and choices, with uncertainty that is visible and bounded. The map, economy,
population, constitution, diplomacy, trade, war, and political-survival systems must eventually
feed the same deterministic turn loop and explain their consequences to the player.
