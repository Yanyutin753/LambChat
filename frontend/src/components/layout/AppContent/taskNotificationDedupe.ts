/**
 * Cross-channel task notification dedupe.
 *
 * Live websocket delivery (`task:complete`) and resume-time catch-up both
 * surface the same run; the shared key space keeps users from getting
 * double-notified for one completion.
 */

const notifiedKeys = new Set<string>();

export function markTaskNotified(dedupeKey: string): void {
  notifiedKeys.add(dedupeKey);
}

export function hasTaskNotified(dedupeKey: string): boolean {
  return notifiedKeys.has(dedupeKey);
}

export function clearTaskNotificationDedupe(): void {
  notifiedKeys.clear();
}
