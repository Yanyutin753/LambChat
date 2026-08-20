/**
 * Chat submission acceptance/rejection notification helpers (extracted from useAgent)
 */

import type { ChatSubmissionCallbacks } from "./types";

export function notifySubmissionAccepted(
  submissionCallbacks?: ChatSubmissionCallbacks,
): void {
  try {
    submissionCallbacks?.onAccepted();
  } catch (error) {
    console.error("Failed to clear accepted chat draft:", error);
  }
}

export function notifySubmissionRejected(
  submissionCallbacks?: ChatSubmissionCallbacks,
): void {
  try {
    submissionCallbacks?.onRejected?.();
  } catch (error) {
    console.error("Failed to restore rejected chat draft:", error);
  }
}
