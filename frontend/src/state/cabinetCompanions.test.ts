/**
 * `reconcileCompanions` -- the function that keeps a staged transfer coherent.
 *
 * Tested as a pure function, without a DOM, because that is what it is and because the properties
 * most worth proving about it (idempotence, immutability, insertion-order independence, and what it
 * does with a malformed record) are awkward to reach through a rendered screen and trivial to reach
 * here.
 */

import { describe, expect, it } from "vitest";

import { reconcileCompanions, type CabinetOrders } from "./cabinetCompanions";

const CoS = "chief_of_staff";
const FM = "foreign_minister";

/** An explicit transfer INTO `destination`, moving its appointee out of `origin`. */
function transfer(characterId: string, origin: string): CabinetOrders[string] {
  return { characterId, origin: "explicit", requiresVacatingPost: origin };
}

function explicit(characterId: string | null): CabinetOrders[string] {
  return { characterId, origin: "explicit" };
}

function companion(generatedBy: string): CabinetOrders[string] {
  return { characterId: null, origin: "generated", generatedBy };
}

/** A stable serialization, so "byte-identical" is a real claim and not key-order luck. */
function canonical(orders: CabinetOrders): string {
  return JSON.stringify(
    Object.keys(orders)
      .sort((a, b) => a.localeCompare(b))
      .map((post) => [post, orders[post]]),
  );
}

describe("reconcileCompanions: purity", () => {
  it("never mutates its argument", () => {
    const input: CabinetOrders = { [CoS]: transfer("ilse", FM) };
    const before = canonical(input);
    const keysBefore = Object.keys(input).length;

    reconcileCompanions(input);

    expect(canonical(input)).toBe(before);
    expect(Object.keys(input)).toHaveLength(keysBefore);
    expect(input[FM]).toBeUndefined();
  });

  it("is idempotent across every fixture shape", () => {
    const fixtures: CabinetOrders[] = [
      {},
      { [CoS]: explicit("wren") },
      { [CoS]: transfer("ilse", FM) },
      { [CoS]: transfer("ilse", FM), [FM]: explicit("hal") },
      { [CoS]: transfer("ilse", FM), [FM]: transfer("hal", CoS) },
      { [FM]: companion(CoS) },
      { [CoS]: explicit("wren"), [FM]: companion(CoS) },
    ];
    for (const fixture of fixtures) {
      const once = reconcileCompanions(fixture);
      expect(canonical(reconcileCompanions(once))).toBe(canonical(once));
    }
  });

  it("reconciles equivalent records to byte-identical output whatever order they were built in", () => {
    const forward: CabinetOrders = {};
    forward[CoS] = transfer("ilse", FM);
    forward["zzz_unknown_post"] = explicit("nobody");

    const backward: CabinetOrders = {};
    backward["zzz_unknown_post"] = explicit("nobody");
    backward[CoS] = transfer("ilse", FM);

    expect(canonical(reconcileCompanions(forward))).toBe(canonical(reconcileCompanions(backward)));
  });
});

describe("reconcileCompanions: companion validity", () => {
  it("creates a companion for a live transfer whose origin is empty", () => {
    const result = reconcileCompanions({ [CoS]: transfer("ilse", FM) });
    expect(result[FM]).toEqual(companion(CoS));
  });

  it("removes an ORPHAN companion whose transfer no longer exists", () => {
    const result = reconcileCompanions({ [FM]: companion(CoS) });
    expect(result).toEqual({});
  });

  it("removes a companion whose destination order stopped being a transfer", () => {
    // `requiresVacatingPost` gone: the appointment is still there, but it no longer moves anybody
    // out of the ministry, so a dismissal there is no longer its consequence.
    const result = reconcileCompanions({ [CoS]: explicit("wren"), [FM]: companion(CoS) });
    expect(result).toEqual({ [CoS]: explicit("wren") });
  });

  it("removes a MISMATCHED companion whose transfer vacates a different post", () => {
    // `generatedBy` names a live transfer -- but that transfer leaves `zzz_elsewhere`, not this
    // post. Keeping it would empty a post no transfer is leaving.
    const result = reconcileCompanions({
      [CoS]: transfer("ilse", "zzz_elsewhere"),
      [FM]: companion(CoS),
    });
    expect(result[FM]).toBeUndefined();
    expect(result["zzz_elsewhere"]).toEqual(companion(CoS));
  });

  it("leaves no orphan or mismatched generated entry in any reconciled result", () => {
    const fixtures: CabinetOrders[] = [
      { [FM]: companion(CoS) },
      { [CoS]: explicit("wren"), [FM]: companion(CoS) },
      { [CoS]: transfer("ilse", "zzz_elsewhere"), [FM]: companion(CoS) },
      { [CoS]: transfer("ilse", FM), [FM]: companion("zzz_nothing") },
      { [CoS]: transfer("ilse", FM), [FM]: explicit("hal") },
    ];
    for (const fixture of fixtures) {
      const result = reconcileCompanions(fixture);
      const transfers = new Map(
        Object.entries(result)
          .filter(([, order]) => order.origin === "explicit" && order.requiresVacatingPost)
          .map(([post, order]) => [post, order.requiresVacatingPost]),
      );
      for (const [post, order] of Object.entries(result)) {
        if (order.origin !== "generated") {
          continue;
        }
        expect(order.generatedBy).toBeDefined();
        expect(transfers.get(order.generatedBy as string)).toBe(post);
      }
    }
  });
});

describe("reconcileCompanions: explicit orders are never overwritten", () => {
  it("preserves an explicit order sitting on a live transfer's origin", () => {
    const result = reconcileCompanions({ [CoS]: transfer("ilse", FM), [FM]: explicit("hal") });
    expect(result[FM]).toEqual(explicit("hal"));
  });

  it("preserves an explicit DISMISSAL on a live transfer's origin", () => {
    const result = reconcileCompanions({ [CoS]: transfer("ilse", FM), [FM]: explicit(null) });
    expect(result[FM]).toEqual(explicit(null));
    expect(result[FM]?.origin).toBe("explicit");
  });

  it("restores a companion when a live transfer's explicit origin order is removed", () => {
    // The case a rules-in-each-action design misses: without restoration the draft would carry a
    // transfer with nobody leaving, seating one person in two posts.
    const edited: CabinetOrders = { [CoS]: transfer("ilse", FM), [FM]: explicit("hal") };
    const { [FM]: _removed, ...afterRemoval } = edited;
    expect(reconcileCompanions(afterRemoval)[FM]).toEqual(companion(CoS));
  });

  it("does nothing at all to a draft with no transfers", () => {
    const plain: CabinetOrders = { [CoS]: explicit("wren"), [FM]: explicit(null) };
    expect(canonical(reconcileCompanions(plain))).toBe(canonical(plain));
  });
});

describe("reconcileCompanions: the two-way swap", () => {
  const swap: CabinetOrders = { [CoS]: transfer("ilse", FM), [FM]: transfer("hal", CoS) };

  it("needs no companion while both sides are explicit", () => {
    const result = reconcileCompanions(swap);
    expect(canonical(result)).toBe(canonical(swap));
    expect(Object.values(result).every((order) => order.origin === "explicit")).toBe(true);
  });

  it("cancelling the chief-of-staff side leaves the remaining transfer plus its companion", () => {
    const { [CoS]: _removed, ...rest } = swap;
    const result = reconcileCompanions(rest);
    expect(result[FM]).toEqual(transfer("hal", CoS));
    expect(result[CoS]).toEqual(companion(FM));
  });

  it("cancelling the foreign-minister side does the same, in the other direction", () => {
    const { [FM]: _removed, ...rest } = swap;
    const result = reconcileCompanions(rest);
    expect(result[CoS]).toEqual(transfer("ilse", FM));
    expect(result[FM]).toEqual(companion(CoS));
  });
});
