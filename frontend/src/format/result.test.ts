/**
 * Gate 4A3 M-4: the result's pure rules -- where every driver goes (exactly once, original index
 * kept, unmatched bloc reactions reported), the verdict in words, the bloc move in words and a mark,
 * the person beside a people entry, and one colour palette per recorded vote.
 *
 * The fixtures are BACKEND OUTPUT: `src/test/turn-results.json`, pinned by
 * `backend/tests/test_result_fixtures.py`.
 */

import { describe, expect, it } from "vitest";

import fixtures from "../test/turn-results.json";
import { partyColours } from "./parliament";
import {
  BLOC_COMPONENT_REASONS,
  BLOC_TOTAL_REASON,
  blocMove,
  noVoteLine,
  partitionDrivers,
  personOf,
  resultVerdict,
  voteColours,
  type DriverLike,
  type DriverPartition,
} from "./result";

const ALL = fixtures as unknown as Record<string, { drivers: DriverLike[]; recorded_vote: unknown; no_vote_reason: unknown }>;

/** Every index placed, as a multiset: card, people, every bloc's total and components, other, routine. */
function placed(parts: DriverPartition): number[] {
  return [
    ...parts.card,
    ...parts.people,
    ...parts.blocs.flatMap((g) => [g.total, ...g.components]),
    ...parts.other,
    ...parts.routine,
  ].map((row) => row.index);
}

function expectExactlyOnce(drivers: readonly DriverLike[], parts: DriverPartition) {
  const indices = placed(parts).sort((a, b) => a - b);
  expect(indices).toEqual(drivers.map((_, i) => i));
}

const total = (party: string, bloc: string, change = 50): DriverLike => ({
  reason_id: BLOC_TOTAL_REASON,
  label: "A bloc's relationship with the government changed.",
  params: { party_id: party, bloc_id: bloc, bloc_display_name: `${party} ${bloc}`, opening_relationship_bps: 1000, closing_relationship_bps: 1000 + change, applied_total_change_bps: change },
});
const component = (party: string, bloc: string, reason = "enacted_policy_relationship_reaction", bps = 20): DriverLike => ({
  reason_id: reason,
  label: "A bloc reacted.",
  params: { party_id: party, bloc_id: bloc, bloc_display_name: `${party} ${bloc}`, policy_reaction_component_bps: bps, decree_bypass_component_bps: bps },
});

describe("partitionDrivers", () => {
  it.each(Object.keys(ALL))("places every driver of the real turn %s exactly once, with nothing unmatched", (name) => {
    const drivers = ALL[name]!.drivers;
    const parts = partitionDrivers(drivers);
    expectExactlyOnce(drivers, parts);
    expect(parts.unmatched).toEqual([]);
    for (const row of [...parts.card, ...parts.people, ...parts.other, ...parts.routine]) {
      expect(drivers[row.index]).toBe(row.driver); // the original index is kept
    }
  });

  it("groups the real Arken turn: the vote in the card, two people, five blocs each with its reaction", () => {
    const parts = partitionDrivers(ALL["arkenBargainBudget"]!.drivers);
    expect(parts.card.map((r) => r.reason_id)).toEqual(["tax_rate_changed", "legislative_vote_resolved"]);
    expect(parts.people.map((r) => r.reason_id)).toEqual(["cabinet_replaced", "legislative_bargain_accepted"]);
    expect(parts.blocs).toHaveLength(5);
    for (const group of parts.blocs) {
      expect(group.components.map((c) => c.reason_id)).toEqual(["enacted_policy_relationship_reaction"]);
      expect(group.components[0]!.driver.params?.["party_id"]).toBe(group.partyId);
      expect(group.components[0]!.driver.params?.["bloc_id"]).toBe(group.blocId);
    }
  });

  it("matches by the PAIR: the same bloc id under two parties stays two rows, each with its own reactions", () => {
    const drivers = [
      component("crown", "main", "enacted_policy_relationship_reaction", 10),
      component("reform", "main", "decree_bypass_relationship_reaction", -30),
      total("crown", "main", 10),
      total("reform", "main", -30),
    ];
    const parts = partitionDrivers(drivers);
    expectExactlyOnce(drivers, parts);
    expect(parts.blocs.map((g) => [g.partyId, g.blocId, g.components.map((c) => c.index)])).toEqual([
      ["crown", "main", [0]],
      ["reform", "main", [1]],
    ]);
    expect(parts.unmatched).toEqual([]);
  });

  it("keeps every repeated reaction for one bloc, in server order, with its original index", () => {
    const drivers = [
      component("crown", "core", "enacted_policy_relationship_reaction", 10),
      component("crown", "core", "decree_bypass_relationship_reaction", -20),
      component("crown", "core", "enacted_policy_relationship_reaction", 5),
      total("crown", "core", -5),
    ];
    const parts = partitionDrivers(drivers);
    expect(parts.blocs[0]!.components.map((c) => c.index)).toEqual([0, 1, 2]);
    expect(parts.blocs[0]!.total.index).toBe(3);
  });

  it("reports a reaction with no matching bloc row -- and still shows it, under 'What else happened'", () => {
    const orphan = component("ghost", "core");
    const missingPair: DriverLike = { reason_id: "decree_bypass_relationship_reaction", label: "Blocs resented it.", params: {} };
    const drivers = [orphan, total("crown", "core"), missingPair];
    const parts = partitionDrivers(drivers);
    expectExactlyOnce(drivers, parts);
    expect(parts.unmatched.map((r) => r.index)).toEqual([0, 2]);
    expect(parts.other.map((r) => r.index)).toEqual([0, 2]);
  });

  it("places every driver exactly once for random sequences (property)", () => {
    const reasons = [
      "legislative_vote_resolved", "tax_rate_changed", "legislative_bargain_accepted", "cabinet_dismissed",
      "promise_made", "legitimacy_resolved", "labor_market_resolved", "turn_resolved", "sector_inactive",
      BLOC_TOTAL_REASON, ...BLOC_COMPONENT_REASONS, "relationship_decay_resolved", "something_new",
    ];
    const parties = ["crown", "reform"];
    const blocs = ["main", "core"];
    let seed = 20261012;
    const next = (n: number) => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % n;
    };
    for (let trial = 0; trial < 300; trial++) {
      const length = next(25);
      const drivers: DriverLike[] = Array.from({ length }, () => {
        const reason = reasons[next(reasons.length)]!;
        const withPair = next(5) !== 0;
        return {
          reason_id: reason,
          label: reason,
          params: (withPair
            ? { party_id: parties[next(2)]!, bloc_id: blocs[next(2)]!, category: "construction" }
            : { category: "construction" }) as Record<string, string | number>,
        };
      });
      const parts = partitionDrivers(drivers);
      expectExactlyOnce(drivers, parts);
      const totals = new Set(
        drivers
          .filter((d) => d.reason_id === BLOC_TOTAL_REASON && d.params?.["party_id"] !== undefined)
          .map((d) => `${d.params!["party_id"]}/${d.params!["bloc_id"]}`),
      );
      const expectedUnmatched = drivers
        .map((d, index) => ({ d, index }))
        .filter(({ d }) => BLOC_COMPONENT_REASONS.has(d.reason_id))
        .filter(({ d }) => d.params?.["party_id"] === undefined || !totals.has(`${d.params["party_id"]}/${d.params["bloc_id"]}`))
        .map(({ index }) => index);
      expect(parts.unmatched.map((r) => r.index)).toEqual(expectedUnmatched);
    }
  });
});

describe("the proposal card's verdict", () => {
  it("is a word for each state, from the stored fields only", () => {
    expect(resultVerdict({ outcome: "passed_legislative" }, null)).toEqual({ kind: "enacted", word: "Enacted" });
    expect(resultVerdict({ outcome: "failed_legislative" }, null)).toEqual({ kind: "not_carried", word: "Did not carry" });
    expect(resultVerdict(null, "enacted_by_decree")).toEqual({ kind: "decree", word: "Enacted by decree" });
    expect(resultVerdict(null, "no_proposal")).toEqual({ kind: "no_proposal", word: "No proposal" });
    expect(resultVerdict(null, null)).toBeNull();
  });

  it("matches every real fixture", () => {
    const kinds = Object.fromEntries(
      Object.entries(ALL).map(([name, r]) => [
        name,
        resultVerdict(r.recorded_vote as { outcome: string } | null, r.no_vote_reason as string | null)?.kind,
      ]),
    );
    expect(kinds).toEqual({
      arkenBargainBudget: "enacted",
      valdrunFailedBudget: "not_carried",
      valdrunDecreeBudget: "decree",
      valdrunAmendmentFailed: "not_carried",
      valdrunAmendmentPassed: "enacted",
      valdrunNoProposal: "no_proposal",
    });
  });

  it("says why no vote was held only where nothing else says it", () => {
    expect(noVoteLine("no_proposal")).toBe("No proposal was put to a vote this turn.");
    expect(noVoteLine("enacted_by_decree")).toBeNull();
  });
});

describe("a bloc's move", () => {
  it("is in words and a mark, never colour alone", () => {
    expect(blocMove(total("crown", "core", 60).params)).toMatchObject({ direction: "closer", mark: "▲", words: "closer +0.60 points" });
    expect(blocMove(total("crown", "core", -40).params)).toMatchObject({ direction: "cooler", mark: "▼", words: "cooler -0.40 points" });
    expect(blocMove(total("crown", "core", 0).params)).toMatchObject({ direction: "unchanged", words: "no change" });
    expect(blocMove(total("crown", "core", -70).params)?.span).toBe("relationship 10.00% → 9.30%");
    expect(blocMove({ party_id: "x", bloc_id: "y" })).toBeNull();
  });
});

describe("the person beside a people entry", () => {
  it("uses the portrait the server attached from that turn, or the name alone", () => {
    expect(personOf({ character_display_name: "Maret Kuusk", character_portrait_ref: "portrait_x" })).toEqual({ portraitRef: "portrait_x", name: "Maret Kuusk" });
    expect(personOf({ character_display_name: "Maret Kuusk" })).toEqual({ portraitRef: null, name: "Maret Kuusk" });
    expect(personOf({ outgoing_character_display_name: "Hal Verrin", outgoing_character_portrait_ref: "p_h" })).toEqual({ portraitRef: "p_h", name: "Hal Verrin" });
    expect(personOf({ counterpart_display_name: "Envoy", counterpart_portrait_ref: "p_e" })).toEqual({ portraitRef: "p_e", name: "Envoy" });
    expect(personOf({ profile_display_name: "Ostmark" })).toBeNull();
  });
});

describe("one palette per recorded vote", () => {
  it("gives a party the same colour in every chamber, whatever the membership and order", () => {
    const vote = {
      chambers: [
        { blocs: [{ party_id: "crown" }, { party_id: "reform" }] },
        // The upper chamber seats a party the lower does not, and in a different order.
        { blocs: [{ party_id: "rural" }, { party_id: "reform" }, { party_id: "crown" }] },
      ],
    };
    const colours = voteColours(vote);
    expect(Object.keys(colours)).toEqual(["crown", "reform", "rural"]);
    expect(colours).toEqual(partyColours(["crown", "reform", "rural"]));
    // A per-chamber palette would have coloured the upper chamber's first party (rural) gold.
    expect(colours["rural"]).not.toBe(partyColours(["rural"])["rural"]);
  });

  it("is a function of the vote alone", () => {
    const vote = (ALL["arkenBargainBudget"]!.recorded_vote ?? { chambers: [] }) as Parameters<typeof voteColours>[0];
    expect(voteColours(vote)).toEqual(voteColours(JSON.parse(JSON.stringify(vote))));
    expect(Object.keys(voteColours(vote)).length).toBeGreaterThan(1);
  });
});
