import type { BackendSession } from "../../services/api/session";

export function isSessionPinned(session: BackendSession): boolean {
  return session.metadata?.is_pinned === true;
}
