/**
 * Gate 4A3 UX-4b (U8) — "This turn's draft": every staged player action, in one list.
 *
 * Actions are staged on four screens (Decisions, Government, Relationships, Strategic map), and until
 * now none of them could be seen from the place the turn is resolved. This lists `stagedActions` --
 * the same list the nav count and the resolve confirmation read -- with each entry worded exactly as
 * the screen that staged it words it (the shared helpers in `format.ts`).
 *
 * Names come from the projections the staging screens already use. A name this build cannot find
 * falls back to neutral words, never to a raw identifier.
 */

import type { DecisionOptionsProjection, MilitaryProjection } from "../api/client";
import {
  assistanceStagedLine,
  bargainStagedLine,
  becomesLine,
  investmentStagedLine,
  leftVacantLine,
  movementStagedLine,
  promiseMadeStagedLine,
  promiseReleaseStagedLine,
  proposalStagedLine,
} from "../format/format";
import type { ProposalRoute } from "../state/draft";
import type { StagedAction } from "../state/stagedActions";
import { EmptyNote } from "./components";

function postName(options: DecisionOptionsProjection, post: string): string {
  return options.cabinet_posts.find((row) => row.post === post)?.post_display_name ?? "a cabinet post";
}

function personName(options: DecisionOptionsProjection, characterId: string): string {
  for (const row of options.cabinet_posts) {
    const match = row.candidates.find((candidate) => candidate.character_id === characterId);
    if (match !== undefined) return match.display_name;
  }
  return "the appointee";
}

function cabinetLine(options: DecisionOptionsProjection, post: string, characterId: string | null): string {
  const label = postName(options, post);
  return characterId === null ? leftVacantLine(label) : becomesLine(personName(options, characterId), label);
}

function line(
  action: StagedAction,
  options: DecisionOptionsProjection,
  military: MilitaryProjection | undefined,
  routes: { budget: ProposalRoute; amendment: ProposalRoute },
): string {
  switch (action.kind) {
    case "proposal":
      return proposalStagedLine(action.slot, routes[action.slot]);
    case "cabinet":
      return cabinetLine(options, action.post, action.characterId);
    case "investment": {
      const bloc = options.blocs.find((row) => row.party_id === action.partyId && row.bloc_id === action.blocId);
      return investmentStagedLine(action.politicalCapital, bloc?.bloc_name ?? "a bloc");
    }
    case "bargain": {
      const leader = options.legislative_bargain_counterparties.find(
        (row) => row.character_id === action.characterId,
      );
      return bargainStagedLine(leader?.display_name ?? "A party leader", action.proposalKind);
    }
    case "assistance": {
      const profile = options.foreign_assistance_counterparties.find((row) => row.profile_id === action.profileId);
      return assistanceStagedLine(profile?.display_name ?? "A foreign power");
    }
    case "promise": {
      const promise = action.promise;
      if (promise.action === "make") {
        const row = options.promise_options.find(
          (option) => option.character_id === promise.characterId && option.subject_id === promise.subjectId,
        );
        return promiseMadeStagedLine(row?.character_display_name ?? "a character", row?.subject_display_name ?? "a subject");
      }
      const active = options.active_promises.find((row) => row.promise_id === promise.promiseId);
      return promiseReleaseStagedLine(active?.character_display_name ?? "a character");
    }
    case "movement": {
      const formation = military?.formations.find((row) => row.formation_id === action.formationId);
      const destination = formation?.destination_options.find(
        (row) => row.theater_id === action.destinationTheaterId,
      );
      return movementStagedLine(formation?.display_name ?? "A formation", destination?.display_name ?? "its destination");
    }
  }
}

export function StagedActionsList({
  actions,
  options,
  military,
  routes,
}: {
  actions: readonly StagedAction[];
  options: DecisionOptionsProjection;
  military: MilitaryProjection | undefined;
  routes: { budget: ProposalRoute; amendment: ProposalRoute };
}) {
  if (actions.length === 0) {
    return <EmptyNote>Nothing is staged yet.</EmptyNote>;
  }
  return (
    <ol data-testid="staged-actions" className="flex list-decimal flex-col gap-2 pl-5 text-sm">
      {actions.map((action, index) => (
        <li key={`${index}:${action.kind}`} data-staged-kind={action.kind}>
          {line(action, options, military, routes)}
          {action.kind === "cabinet" && action.consequences.length > 0 ? (
            <ul className="mt-1 list-disc pl-5 text-parchment-200/80">
              {action.consequences.map((consequence) => (
                <li key={consequence.post} data-staged-consequence={consequence.post}>
                  As a result: {cabinetLine(options, consequence.post, consequence.characterId)}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
