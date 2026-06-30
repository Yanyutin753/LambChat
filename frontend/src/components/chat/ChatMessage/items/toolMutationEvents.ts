import {
  dispatchPersonaPresetsChanged,
  type PersonaPresetEventTarget,
  type PersonaPresetsChangedDetail,
} from "../../../../hooks/personaPresetEvents";
import {
  dispatchTeamsChanged,
  type TeamEventTarget,
  type TeamsChangedDetail,
} from "../../../../hooks/teamEvents";

interface PersonaPresetToolMutationResult {
  action?: unknown;
  entity_type?: unknown;
  preset?: {
    id?: unknown;
    name?: unknown;
  } | null;
}

interface TeamToolMutationResult {
  action?: unknown;
  entity_type?: unknown;
  team_id?: unknown;
  team?: {
    id?: unknown;
    name?: unknown;
  } | null;
}

export interface ToolMutationTargets {
  persona?: PersonaPresetEventTarget | null;
  team?: TeamEventTarget | null;
}

function isRecord(
  value: string | Record<string, unknown> | undefined,
): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isMutationAction(
  value: unknown,
): value is "created" | "updated" | "deleted" {
  return value === "created" || value === "updated" || value === "deleted";
}

export function getPersonaPresetMutationDetail(
  result: string | Record<string, unknown> | undefined,
): PersonaPresetsChangedDetail | null {
  if (!isRecord(result)) return null;

  const payload = result as PersonaPresetToolMutationResult;
  if (payload.entity_type !== "persona_preset") return null;
  if (!isMutationAction(payload.action)) return null;

  const detail: PersonaPresetsChangedDetail = {
    action: payload.action,
  };

  if (payload.preset?.id && typeof payload.preset.id === "string") {
    detail.presetId = payload.preset.id;
  }
  if (payload.preset?.name && typeof payload.preset.name === "string") {
    detail.presetName = payload.preset.name;
  }

  return detail;
}

export function getTeamMutationDetail(
  result: string | Record<string, unknown> | undefined,
): TeamsChangedDetail | null {
  if (!isRecord(result)) return null;

  const payload = result as TeamToolMutationResult;
  if (payload.entity_type !== "team") return null;
  if (!isMutationAction(payload.action)) return null;

  const detail: TeamsChangedDetail = {
    action: payload.action,
  };

  if (payload.team?.id && typeof payload.team.id === "string") {
    detail.teamId = payload.team.id;
  } else if (payload.team_id && typeof payload.team_id === "string") {
    detail.teamId = payload.team_id;
  }
  if (payload.team?.name && typeof payload.team.name === "string") {
    detail.teamName = payload.team.name;
  }

  return detail;
}

export function dispatchToolMutationRefresh(
  result: string | Record<string, unknown> | undefined,
  targets: ToolMutationTargets = {},
): boolean {
  const personaDetail = getPersonaPresetMutationDetail(result);
  if (personaDetail) {
    return dispatchPersonaPresetsChanged(personaDetail, targets.persona);
  }

  const teamDetail = getTeamMutationDetail(result);
  if (teamDetail) {
    return dispatchTeamsChanged(teamDetail, targets.team);
  }

  return false;
}
