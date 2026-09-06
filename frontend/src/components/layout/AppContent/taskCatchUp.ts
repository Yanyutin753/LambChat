/**
 * Resume-time catch-up selection for task completion notifications.
 *
 * Mobile clients lose their websocket soon after backgrounding, so
 * `task:complete` never arrives while the user is away. When the app comes
 * back to the foreground we diff the session list against the moment the app
 * went hidden and re-notify for runs that finished in the meantime.
 */

import type { BackendSession } from "../../../services/api/session";

export const CATCH_UP_NOTIFIABLE_STATUSES = [
  "completed",
  "failed",
  "waiting_human",
] as const;

type CatchUpStatus = (typeof CATCH_UP_NOTIFIABLE_STATUSES)[number];

/** 客户端与服务器时钟偏差容忍窗口：完成时间略早于本地 hiddenAt 仍算后台期间完成 */
const CATCH_UP_CLOCK_SKEW_MS = 2 * 60 * 1000;

/** 单次回前台最多补发的通知条数，防止长时间离开后通知轰炸 */
const CATCH_UP_MAX_NOTIFICATIONS = 5;

export interface CatchUpSessionSnapshot {
  id: string;
  task_status?: string | null;
  updated_at: string;
  name?: string;
  unread_count?: number;
  metadata?: Record<string, unknown>;
}

export interface CatchUpCandidate {
  session_id: string;
  run_id?: string;
  status: CatchUpStatus;
  dedupeKey: string;
  sessionName?: string;
  unreadCount?: number;
}

function isNotifiableStatus(status?: string | null): status is CatchUpStatus {
  return (
    !!status &&
    (CATCH_UP_NOTIFIABLE_STATUSES as readonly string[]).includes(status)
  );
}

function currentRunId(metadata?: Record<string, unknown>): string | undefined {
  const value = metadata?.current_run_id;
  return typeof value === "string" && value ? value : undefined;
}

/**
 * 与 websocket 即时通知共享的 dedupe key（`task:<run_id>:<status>`）；
 * 没有 run_id 时退化为会话 + 完成时间戳，保证同一完成事件只补发一次。
 */
export function buildCatchUpDedupeKey(
  session: CatchUpSessionSnapshot,
  status: CatchUpStatus,
): string {
  const runId = currentRunId(session.metadata);
  if (runId) {
    return `task:${runId}:${status}`;
  }
  return `task:catchup:${session.id}:${session.updated_at}:${status}`;
}

export function selectCatchUpCandidates({
  sessions,
  hiddenAt,
  currentSessionId,
  hasNotified,
}: {
  sessions: CatchUpSessionSnapshot[];
  hiddenAt: number;
  currentSessionId: string | null;
  hasNotified: (dedupeKey: string) => boolean;
}): CatchUpCandidate[] {
  const candidates: CatchUpCandidate[] = [];

  for (const session of sessions) {
    if (!isNotifiableStatus(session.task_status)) continue;
    if (session.id === currentSessionId) continue;

    const updatedAt = Date.parse(session.updated_at);
    if (!Number.isFinite(updatedAt)) continue;
    if (updatedAt < hiddenAt - CATCH_UP_CLOCK_SKEW_MS) continue;

    const status = session.task_status;
    const dedupeKey = buildCatchUpDedupeKey(session, status);
    if (hasNotified(dedupeKey)) continue;

    candidates.push({
      session_id: session.id,
      run_id: currentRunId(session.metadata),
      status,
      dedupeKey,
      sessionName: session.name,
      unreadCount: session.unread_count,
    });
    if (candidates.length >= CATCH_UP_MAX_NOTIFICATIONS) break;
  }

  return candidates;
}

export function toCatchUpSnapshot(
  session: BackendSession,
): CatchUpSessionSnapshot {
  return {
    id: session.id,
    task_status: session.task_status,
    updated_at: session.updated_at,
    name: session.name,
    unread_count: session.unread_count,
    metadata: session.metadata,
  };
}
