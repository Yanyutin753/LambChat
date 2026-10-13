import type { ActiveGoalSpec } from "./types";
import type { PersistentGoal } from "../../services/api/session";

/** Persistent projections carry an ID; identical ordinary prompts remain independent. */
export function getGoalControlScope(
  goal: ActiveGoalSpec | null | undefined,
  persistentGoal: PersistentGoal | null | undefined,
): "ordinary" | "persistent" | null {
  if (goal && (!goal._persistent_id || goal._persistent_id !== persistentGoal?.id)) {
    return "ordinary";
  }
  return persistentGoal && persistentGoal.status !== "cleared" ? "persistent" : null;
}


export function getGoalProjectionIdentity(
  incoming: { _persistent_id?: unknown } | undefined,
  previous: ActiveGoalSpec | null | undefined,
): Pick<ActiveGoalSpec, "_persistent_id"> {
  const id = incoming ? incoming._persistent_id : previous?._persistent_id;
  return typeof id === "string" && id ? { _persistent_id: id } : {};
}
