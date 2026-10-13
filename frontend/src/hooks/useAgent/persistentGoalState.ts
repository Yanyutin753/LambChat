import type { PersistentGoal } from "../../services/api/session";

/** Revision is monotonic across replacement goal IDs within a session. */
export function selectPersistentGoal(
  previous: PersistentGoal | null,
  incoming: PersistentGoal | null,
  sessionId: string | null,
): PersistentGoal | null {
  const current = previous?.session_id === sessionId ? previous : null;
  if (!incoming) return null;
  if (incoming.session_id !== sessionId) return current;
  if (current && incoming.revision < current.revision) return current;
  return incoming;
}
