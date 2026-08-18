/**
 * Gate 4A0 greybox — the single STATIC fixture.
 *
 * Every value below is a LITERAL. Nothing is computed, derived, summed,
 * subtracted, or scaled from another value — not even to make the fixture look
 * internally consistent. If two numbers here agree, it is because both were
 * written down, exactly as both would arrive as separate projection fields from
 * the real API in Gate 4A1+.
 *
 * The figures are the ones the frozen Revision 2 plan states for `decree_state`:
 * hereditary monarchy with unlimited decree authority, 45 government / 55
 * opposition seats, legitimacy 60%, capital 500/1,000, opposition relationship
 * -80%, no election initially, the amendment passing 67/100 against a required
 * 67, and the two turn-11 election outcomes (seed 77 defeat at 48.22%, seed 0
 * victory at 58.10%).
 *
 * These are DISPLAY FIXTURES. They are not simulation results, and the greybox
 * never claims a turn was resolved.
 */

import type { GreyboxFixture } from "./contract";

export const GREYBOX_FIXTURE: GreyboxFixture = {
  scenarios: [
    {
      scenarioId: "decree_state",
      displayName: "The Decree State",
      governmentForm: "Hereditary monarchy",
      electionIntervalLabel: "No election scheduled",
      startingLegitimacyText: "60.00%",
      pitch: "Unlimited decree power, and a constitution you could choose to give away.",
      isShowcase: true,
    },
    {
      scenarioId: "deficit_demo",
      displayName: "Deficit Demo",
      governmentForm: "Parliamentary republic",
      electionIntervalLabel: "Every 12 turns",
      startingLegitimacyText: "55.00%",
      pitch: "A treasury running down, and a legislature that has to be paid for.",
      isShowcase: false,
    },
    {
      scenarioId: "tiny_valid",
      displayName: "Tiny Valid",
      governmentForm: "Bicameral republic",
      electionIntervalLabel: "Every 16 turns",
      startingLegitimacyText: "58.00%",
      pitch: "Two chambers, comfortable majorities, and a term limit waiting at the end.",
      isShowcase: false,
    },
  ],

  saves: [
    {
      saveId: "550e8400-e29b-41d4-a716-446655440000",
      displayName: "Before the amendment",
      scenarioId: "decree_state",
      currentTurn: 2,
      updatedAt: "2026-08-18T09:14:00Z",
      terminalOutcomeSummary: null,
      loadable: true,
      integrityProblem: null,
    },
    {
      saveId: "6f1a2b3c-4d5e-4f60-8a91-b2c3d4e5f607",
      displayName: "Seed 77 — the lost election",
      scenarioId: "decree_state",
      currentTurn: 11,
      updatedAt: "2026-08-18T10:02:00Z",
      terminalOutcomeSummary: "Defeat — electoral defeat, turn 11",
      loadable: true,
      integrityProblem: null,
    },
    {
      saveId: "7a2b3c4d-5e6f-4071-9b02-c3d4e5f60718",
      displayName: "Hand-edited save",
      scenarioId: "decree_state",
      currentTurn: 4,
      updatedAt: "2026-08-18T10:20:00Z",
      terminalOutcomeSummary: null,
      loadable: false,
      integrityProblem: "entry 3: entry_hash does not match the recomputed digest",
    },
  ],

  dashboard: {
    revision: "3.3",
    turn: 3,
    countryName: "Valdoria",
    governmentForm: "Hereditary monarchy",
    nextElectionLabel: "None scheduled",
    concerns: {
      money: {
        label: "Money",
        headline: "412,000",
        deltaText: "-18,400",
        direction: "down",
        tone: "caution",
        detailScreen: "economy",
      },
      legitimacy: {
        label: "Legitimacy",
        headline: "60.00%",
        deltaText: "0.00pp",
        direction: "unchanged",
        tone: "neutral",
        detailScreen: "government",
      },
      legislature: {
        label: "Legislature",
        headline: "45 of 100",
        deltaText: null,
        direction: "unchanged",
        tone: "negative",
        detailScreen: "legislature",
      },
      constitution: {
        label: "Constitution",
        headline: "Amendable",
        deltaText: null,
        direction: "unchanged",
        tone: "neutral",
        detailScreen: "constitution",
      },
      survival: {
        label: "Survival",
        headline: "Coup risk 0.52%",
        deltaText: null,
        direction: "unchanged",
        tone: "caution",
        detailScreen: "government",
      },
    },
    politicalCapital: {
      current: 500,
      capacity: 1000,
      committedThisTurn: 0,
      display: "500 / 1,000",
    },
    alerts: [
      {
        id: "amendment-opportunity",
        severity: "info",
        headline: "A constitutional amendment could pass this turn.",
        detail: "Opposition support has been bought up over two turns of investment.",
        screen: "decisions",
      },
      {
        id: "fiscal-deficit",
        severity: "warning",
        headline: "The budget is running a deficit.",
        detail: "Spending exceeds revenue this turn.",
        screen: "economy",
      },
      {
        id: "coup-risk",
        severity: "info",
        headline: "Coup risk is low but non-zero.",
        detail: null,
        screen: "government",
      },
    ],
    goal: {
      headline: "Your priority: put the constitutional amendment to a vote.",
      detail: "Two turns of relationship investment have made the seats reachable.",
    },
    map: {
      presentationOnly: true,
      tintMetricLabel: "Legitimacy",
      tintValueBps: 6000,
      note: "This map shows national identity only. No province-level mechanics exist.",
    },
    terminal: null,
  },

  decisionOptions: {
    revision: "3.3",
    openingCapital: 500,
    policySlot: {
      selected: "amendment",
      options: [
        {
          kind: "budget",
          label: "Budget proposal",
          available: true,
          unavailableReason: null,
          routes: [
            { route: "legislative", available: true, capitalCost: 0, costText: "Bargaining cost" },
            { route: "decree", available: true, capitalCost: 250, costText: "250 political capital" },
          ],
        },
        {
          kind: "amendment",
          label: "Constitutional amendment",
          available: true,
          unavailableReason: null,
          routes: [
            { route: "legislative", available: true, capitalCost: 0, costText: "Bargaining cost" },
            { route: "decree", available: true, capitalCost: 400, costText: "400 political capital" },
          ],
        },
      ],
    },
    relationshipInvestment: {
      perBlocMin: 1,
      perBlocMax: 200,
      blocs: [
        {
          partyId: "opposition_party",
          blocId: "main",
          displayName: "Opposition — Main bloc",
          relationshipText: "-27.74%",
          baselineText: "-80.00%",
        },
        {
          partyId: "governing_party",
          blocId: "core",
          displayName: "Governing party — Core",
          relationshipText: "+60.00%",
          baselineText: "+60.00%",
        },
      ],
    },
    affordability: {
      committedText: "300",
      openingText: "500",
      committedRatioBps: 6000,
      affordable: true,
      verdictText: "300 of 500 political capital committed",
    },
  },

  turnResult: {
    revision: "3.3",
    turn: 3,
    outcomeHeadline: "Amendment passed, 67 of 100 seats (67 required).",
    outcomeTone: "positive",
    drivers: [
      {
        reasonId: "constitutional_amendment_resolved",
        label: "Five constitutional axes changed by legislative vote.",
      },
      {
        reasonId: "legislative_vote_resolved",
        label: "67 supporting seats against a required 67 — carried by one seat.",
      },
      {
        reasonId: "bloc_relationship_resolved",
        label: "Opposition — Main bloc stood at -27.74% when the vote was scored.",
      },
      {
        reasonId: "transition_pressure_raised",
        label: "Regime transition pressure rose sharply after the amendment.",
      },
    ],
    ledger: [
      {
        label: "Amendment influence",
        target: "opposition_party/main",
        amountText: "300",
        effectText: "Committed and spent",
      },
      {
        label: "Relationship investment",
        target: "opposition_party/main",
        amountText: "0",
        effectText: "None this turn",
      },
    ],
    unchanged: [
      "Tax rates are unchanged.",
      "Spending allocations are unchanged.",
      "No election has been scheduled before this turn.",
    ],
    trace: [
      {
        label: "Supporting seats",
        valueText: "67",
        sourceField: "ConstitutionalAmendmentReport.chamber.supporting_seats",
      },
      {
        label: "Required seats",
        valueText: "67",
        sourceField: "ConstitutionalAmendmentReport.chamber.required_yes_seats",
      },
      {
        label: "Total seats",
        valueText: "100",
        sourceField: "ConstitutionalAmendmentReport.chamber.total_seats",
      },
      {
        label: "Committed political capital",
        valueText: "300",
        sourceField: "PoliticalCapitalReport.expenditures[].political_capital",
      },
      {
        label: "Next election turn",
        valueText: "11",
        sourceField: "PoliticalState.next_election_turn",
      },
      {
        label: "Coup risk",
        valueText: "10.52%",
        sourceField: "CoupUnrestReport.coup_attempt_risk_bps",
      },
    ],
    terminal: null,
  },

  history: [
    { turn: 1, outcomeLine: "Invested 85 political capital in the opposition.", tone: "neutral" },
    { turn: 2, outcomeLine: "Invested 118 political capital in the opposition.", tone: "neutral" },
    { turn: 3, outcomeLine: "Amendment passed, 67 of 100 seats.", tone: "positive" },
  ],

  historyDetail: {
    1: {
      revision: "1.1",
      turn: 1,
      outcomeHeadline: "Opposition — Main bloc improved to -53.85%.",
      outcomeTone: "positive",
      drivers: [
        {
          reasonId: "bloc_relationship_resolved",
          label: "85 political capital bought a large first move.",
        },
        {
          reasonId: "relationship_decay_resolved",
          label: "No decay applied: the bloc opened at its authored baseline.",
        },
      ],
      ledger: [
        {
          label: "Relationship investment",
          target: "opposition_party/main",
          amountText: "85",
          effectText: "-80.00% to -53.85%",
        },
      ],
      unchanged: ["No proposal was submitted.", "Tax rates are unchanged."],
      trace: [
        {
          label: "Closing relationship",
          valueText: "-5,385 bps",
          sourceField: "PoliticalRelationshipReport.blocs[].closing_relationship_bps",
        },
        {
          label: "Closing political capital",
          valueText: "798",
          sourceField: "PoliticalCapitalReport.closing_political_capital",
        },
      ],
      terminal: null,
    },
    2: {
      revision: "2.2",
      turn: 2,
      outcomeHeadline: "Opposition — Main bloc improved to -27.74%.",
      outcomeTone: "positive",
      drivers: [
        {
          reasonId: "bloc_relationship_resolved",
          label: "118 political capital continued the campaign.",
        },
        {
          reasonId: "relationship_decay_resolved",
          label: "Decay pulled back toward the authored baseline.",
        },
      ],
      ledger: [
        {
          label: "Relationship investment",
          target: "opposition_party/main",
          amountText: "118",
          effectText: "-53.85% to -27.74%",
        },
      ],
      unchanged: ["No proposal was submitted."],
      trace: [
        {
          label: "Closing relationship",
          valueText: "-2,774 bps",
          sourceField: "PoliticalRelationshipReport.blocs[].closing_relationship_bps",
        },
        {
          label: "Closing political capital",
          valueText: "1,000",
          sourceField: "PoliticalCapitalReport.closing_political_capital",
        },
      ],
      terminal: null,
    },
  },

  government: {
    executiveLabel: "Hereditary monarch",
    selectionLabel: "Hereditary succession",
    termLimitLabel: "No term limit",
    survivalHeadline: "The government faces no scheduled contest.",
    riskRows: [
      { label: "Coup attempt risk", valueText: "0.52%", tone: "caution" },
      { label: "Unrest attempt risk", valueText: "1.10%", tone: "caution" },
      { label: "Impeachment risk", valueText: "Not applicable", tone: "neutral" },
      { label: "Transition pressure", valueText: "0", tone: "neutral" },
    ],
    institutions: [
      {
        label: "Armed forces",
        loyaltyText: "72.00%",
        powerText: "80.00%",
        competenceText: "65.00%",
        corruptionText: "30.00%",
      },
      {
        label: "Civil service",
        loyaltyText: "64.00%",
        powerText: "45.00%",
        competenceText: "70.00%",
        corruptionText: "25.00%",
      },
      {
        label: "Judiciary",
        loyaltyText: "58.00%",
        powerText: "40.00%",
        competenceText: "68.00%",
        corruptionText: "22.00%",
      },
    ],
  },

  economy: {
    treasuryText: "412,000",
    balanceText: "-18,400",
    balanceDirection: "down",
    revenue: [
      { label: "Personal income tax", valueText: "96,000", deltaText: null, direction: "unchanged" },
      { label: "Corporate tax", valueText: "54,000", deltaText: null, direction: "unchanged" },
      { label: "Consumption tax", valueText: "41,600", deltaText: null, direction: "unchanged" },
      { label: "Total revenue", valueText: "191,600", deltaText: null, direction: "unchanged" },
    ],
    spending: [
      { label: "Defence", valueText: "68,000", deltaText: null, direction: "unchanged" },
      { label: "Health", valueText: "52,000", deltaText: null, direction: "unchanged" },
      { label: "Education", valueText: "34,000", deltaText: null, direction: "unchanged" },
      { label: "Infrastructure", valueText: "24,000", deltaText: null, direction: "unchanged" },
      { label: "Welfare", valueText: "18,000", deltaText: null, direction: "unchanged" },
      { label: "Administration", valueText: "9,000", deltaText: null, direction: "unchanged" },
      { label: "Debt service", valueText: "5,000", deltaText: null, direction: "unchanged" },
      { label: "Total spending", valueText: "210,000", deltaText: null, direction: "unchanged" },
    ],
  },

  legislature: {
    chambers: [
      {
        chamberId: "national_assembly",
        displayName: "National Assembly",
        totalSeats: 100,
        governmentSeats: 45,
        oppositionSeats: 55,
        supportingSeats: 67,
        requiredSeats: 67,
      },
    ],
    blocs: [
      {
        partyId: "governing_party",
        blocId: "core",
        displayName: "Governing party — Core",
        seats: 45,
        relationshipText: "+60.00%",
        baselineText: "+60.00%",
        disciplineText: "High",
      },
      {
        partyId: "opposition_party",
        blocId: "main",
        displayName: "Opposition — Main bloc",
        seats: 55,
        relationshipText: "-27.74%",
        baselineText: "-80.00%",
        disciplineText: "Moderate",
      },
    ],
  },

  constitution: {
    digestText: "b7f4c2a1e9d80356",
    amendmentDifficultyLabel: "Supermajority",
    thresholdText: "67 of 100 seats required",
    axes: [
      { axis: "Decree authority", currentLabel: "Unlimited", amendable: true },
      { axis: "Executive selection", currentLabel: "Hereditary", amendable: true },
      { axis: "Executive system", currentLabel: "Monarchy", amendable: true },
      { axis: "Executive term limit", currentLabel: "None", amendable: true },
      { axis: "National election interval", currentLabel: "None", amendable: true },
      { axis: "Legislature", currentLabel: "Unicameral, 100 seats", amendable: false },
      { axis: "Judicial review", currentLabel: "Absent", amendable: false },
      { axis: "Franchise", currentLabel: "Universal adult", amendable: false },
      { axis: "Amendment difficulty", currentLabel: "Supermajority", amendable: false },
    ],
  },

  relationships: [
    {
      partyId: "opposition_party",
      blocId: "main",
      displayName: "Opposition — Main bloc",
      seats: 55,
      relationshipText: "-27.74%",
      baselineText: "-80.00%",
      disciplineText: "Moderate",
    },
    {
      partyId: "governing_party",
      blocId: "core",
      displayName: "Governing party — Core",
      seats: 45,
      relationshipText: "+60.00%",
      baselineText: "+60.00%",
      disciplineText: "High",
    },
  ],

  glossary: [
    {
      term: "Political capital",
      definition:
        "The government's spendable political standing. It regenerates each turn up to a capacity, and is consumed whether a proposal passes or fails.",
    },
    {
      term: "Legitimacy",
      definition:
        "How far the population accepts the government's right to govern. It feeds election support and survival risk.",
    },
    {
      term: "Decree authority",
      definition:
        "A constitutional power to enact policy without a legislative vote, at a flat political-capital cost and a relationship penalty with every seated bloc.",
    },
    {
      term: "Transition pressure",
      definition:
        "Instability generated by changing the constitution. It rises when an amendment passes and decays on its own between amendments.",
    },
    {
      term: "Peaceful liberalization",
      definition:
        "The game's only victory: transition a noncompetitive constitution to a competitive one, then win the first election held under it.",
    },
    {
      term: "Revision token",
      definition:
        "An opaque marker identifying the exact game state a screen was drawn from. The interface echoes it back when resolving, so a stale decision is refused rather than misapplied.",
    },
  ],

  terminalOutcomes: {
    seed77: {
      bucket: "defeat",
      reasonLabel: "electoral_defeat",
      turn: 11,
      headline: "You lost the election with 48.22% (50% required).",
      retrospective: [
        "The amendment passed at turn 3 by exactly one seat.",
        "503 political capital was committed across the campaign.",
        "The polling swing at the authored seed ran against you.",
      ],
    },
    seed0: {
      bucket: "victory",
      reasonLabel: "peaceful_liberalization_completed",
      turn: 11,
      headline: "Peaceful liberalization completed — you won with 58.10%.",
      retrospective: [
        "A hereditary monarchy became a presidential republic with scheduled elections.",
        "The first election under the new constitution confirmed the transition.",
        "503 political capital was committed across the campaign.",
      ],
    },
  },
};
