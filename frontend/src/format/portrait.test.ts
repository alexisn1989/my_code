import { describe, expect, it } from "vitest";

import {
  PORTRAIT_GARMENT,
  PORTRAIT_HAIR,
  PORTRAIT_HAIR_SHAPES,
  PORTRAIT_SHOULDERS,
  PORTRAIT_SKIN,
  portraitFeatures,
} from "./portrait";

/** Every reference authored in the three shipped scenarios, as the content actually spells them.
 *
 * Listed rather than derived from the YAML so this file states what it covers: if a scenario
 * gains a character, this list and the backend's own completeness test disagree, and the
 * disagreement is the signal. */
/** Every portrait reference authored in the three shipped scenarios, exactly as the content spells
 * them — 26 authored rows over 24 DISTINCT references.
 *
 * Two refs appear twice: `portrait_leader_governing_party` and `portrait_leader_marnil` are
 * authored in both `decree_state` and `deficit_demo`, because those are different campaigns that
 * each name a character by the same id. That is content working as intended, not a collision — so
 * distinctness below is asserted over the DISTINCT set, and totality over every authored row.
 *
 * `test_the_frontend_portrait_list_matches_the_authored_content` in the backend suite asserts this
 * list equals the authored set exactly, so it cannot drift into fiction: an earlier draft of this
 * file invented three references and omitted one, and passed anyway, because a hand-written list
 * that only tests itself proves nothing. */
const AUTHORED_REFS = [
  // decree_state (8)
  "portrait_edda_thorne",
  "portrait_leader_governing_party",
  "portrait_leader_marnil",
  "portrait_leader_opposition_party",
  "portrait_leader_sorrend",
  "portrait_raul_kesten",
  "portrait_sabine_ord",
  "portrait_yannic_pell",
  // deficit_demo (9) -- shares two refs with decree_state, by design
  "portrait_bela_ronsard",
  "portrait_clara_venn",
  "portrait_dorin_akel",
  "portrait_freya_lund",
  "portrait_leader_citizens_bloc",
  "portrait_leader_governing_party",
  "portrait_leader_independents",
  "portrait_leader_marnil",
  "portrait_leader_tolvane",
  // tiny_valid (9)
  "portrait_hal_verrin",
  "portrait_ilse_marovec",
  "portrait_leader_civic_union",
  "portrait_leader_kessia",
  "portrait_leader_national_front",
  "portrait_leader_rural_alliance",
  "portrait_leader_vetruska",
  "portrait_tomas_bekker",
  "portrait_wren_hollis",
] as const;

const DISTINCT_REFS = [...new Set<string>(AUTHORED_REFS)];

describe("portraitFeatures — the five renderer guarantees", () => {
  it("resolves every authored reference with no fallback", () => {
    // TOTALITY, which is what "no fallback" means: there is no default face to fall back TO, so a
    // reference that failed to resolve would throw rather than render somebody generic.
    expect(AUTHORED_REFS).toHaveLength(26);
    expect(DISTINCT_REFS).toHaveLength(24);
    for (const ref of AUTHORED_REFS) {
      const features = portraitFeatures(ref);
      expect(features.skin).toBeGreaterThanOrEqual(0);
      expect(features.skin).toBeLessThan(PORTRAIT_SKIN.length);
      expect(features.hair).toBeLessThan(PORTRAIT_HAIR.length);
      expect(features.hairStyle).toBeLessThan(PORTRAIT_HAIR_SHAPES.length);
      expect(features.garment).toBeLessThan(PORTRAIT_GARMENT.length);
      expect(features.build).toBeLessThan(PORTRAIT_SHOULDERS.length);
    }
  });

  it("gives an empty reference no portrait at all, rather than a default one", () => {
    // The anti-fallback assertion. A generic face here would let an unauthored character ship
    // silently, which is the failure authoring the field exists to prevent.
    expect(() => portraitFeatures("")).toThrow(/no default portrait/);
  });

  it("produces distinct visual signatures across the authored references", () => {
    // Signatures, not pixels: two refs that agreed on every feature would draw the same person.
    const signatures = DISTINCT_REFS.map((ref) => JSON.stringify(portraitFeatures(ref)));
    expect(new Set(signatures).size).toBe(DISTINCT_REFS.length);
  });

  it("keeps near-identical references visibly different", () => {
    // The case a weak hash gets wrong: refs sharing a long prefix must not share a face.
    const a = portraitFeatures("portrait_leader_kessia");
    const b = portraitFeatures("portrait_leader_vetruska");
    const differing = (["skin", "hair", "hairStyle", "garment", "build"] as const).filter(
      (key) => a[key] !== b[key],
    );
    expect(differing.length).toBeGreaterThanOrEqual(2);
  });

  it("is stable: the same reference yields the same signature on every call", () => {
    // Stability across RERENDER and across SAVE/RELOAD are the same property here, because the
    // features are a pure function of the ref and depend on no clock, no randomness and no
    // module-level state that a reload would reset.
    for (const ref of AUTHORED_REFS) {
      expect(portraitFeatures(ref)).toEqual(portraitFeatures(ref));
    }
    const twice = [portraitFeatures("portrait_hal_verrin"), portraitFeatures("portrait_hal_verrin")];
    expect(twice[0]).toEqual(twice[1]);
  });

  it("derives from the REFERENCE, never from a character id", () => {
    // The rule the whole file exists for: a ref and an id that merely look alike must not collide,
    // and changing only the id must not change the face.
    expect(portraitFeatures("portrait_hal_verrin")).not.toEqual(portraitFeatures("hal_verrin"));
  });
});
