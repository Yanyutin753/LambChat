import {
  dispatchToolMutationRefresh,
  getPersonaPresetMutationDetail,
  getTeamMutationDetail,
} from "../toolMutationEvents.ts";
import {
  subscribePersonaPresetsChanged,
  type PersonaPresetsChangedDetail,
} from "../../../../../hooks/personaPresetEvents.ts";
import {
  subscribeTeamsChanged,
  type TeamsChangedDetail,
} from "../../../../../hooks/teamEvents.ts";

test("recognizes persona preset mutation payloads from tool results", () => {
  expect(
    getPersonaPresetMutationDetail({
      action: "created",
      entity_type: "persona_preset",
      preset: { id: "preset-1", name: "Planner" },
      message: "Created",
    }),
  ).toEqual({ action: "created", presetId: "preset-1", presetName: "Planner" });
});

test("recognizes team mutation payloads from tool results", () => {
  expect(
    getTeamMutationDetail({
      action: "updated",
      entity_type: "team",
      team_id: "team-1",
      team: { id: "team-1", name: "Research Team" },
    }),
  ).toEqual({ action: "updated", teamId: "team-1", teamName: "Research Team" });
});

test("dispatches matching mutation refresh events", () => {
  const personaTarget = new EventTarget();
  const teamTarget = new EventTarget();
  const seenPersonas: PersonaPresetsChangedDetail[] = [];
  const seenTeams: TeamsChangedDetail[] = [];
  const unsubscribePersonas = subscribePersonaPresetsChanged(
    (detail) => seenPersonas.push(detail),
    personaTarget,
  );
  const unsubscribeTeams = subscribeTeamsChanged(
    (detail) => seenTeams.push(detail),
    teamTarget,
  );

  const dispatchedPersona = dispatchToolMutationRefresh(
    {
      action: "created",
      entity_type: "persona_preset",
      preset: { id: "preset-2", name: "Writer" },
    },
    { persona: personaTarget, team: teamTarget },
  );
  const dispatchedTeam = dispatchToolMutationRefresh(
    {
      action: "updated",
      entity_type: "team",
      team: { id: "team-2", name: "Launch Team" },
    },
    { persona: personaTarget, team: teamTarget },
  );

  unsubscribePersonas();
  unsubscribeTeams();

  expect(dispatchedPersona).toBe(true);
  expect(dispatchedTeam).toBe(true);
  expect(seenPersonas).toEqual([
    { action: "created", presetId: "preset-2", presetName: "Writer" },
  ]);
  expect(seenTeams).toEqual([
    { action: "updated", teamId: "team-2", teamName: "Launch Team" },
  ]);
});
