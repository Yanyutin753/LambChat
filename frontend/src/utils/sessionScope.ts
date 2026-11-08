import type { BackendSession } from "../services/api/session";

export function isCompanionSession(
  session: Pick<BackendSession, "metadata">,
): boolean {
  return [
    session.metadata?.assistant_id,
    session.metadata?.assistant_discussion_id,
  ].some((value) => typeof value === "string" && value.length > 0);
}
