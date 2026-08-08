/**
 * 解析会话展示名，优先级与 getSessionTitle 对齐：
 * 顶层 name → metadata.title → 空串。
 *
 * 仅当顶层 name 为字符串时采用（即便为空串），否则回退到
 * metadata.title；均不可用时返回空串，由调用方走兜底文案。
 */
export interface SessionTitleSource {
  name?: unknown;
  metadata?: unknown;
}

export const PROJECT_SHARE_SESSION_LIMIT = 50;

export function buildInitialProjectSessionSelection(
  sessionIds: string[],
): string[] {
  return [...new Set(sessionIds.filter(Boolean))].slice(
    0,
    PROJECT_SHARE_SESSION_LIMIT,
  );
}

export function toggleProjectSessionSelection(
  selected: string[],
  sessionId: string,
): { selected: string[]; limitReached: boolean } {
  if (selected.includes(sessionId)) {
    return {
      selected: selected.filter((id) => id !== sessionId),
      limitReached: false,
    };
  }
  if (!sessionId || selected.length >= PROJECT_SHARE_SESSION_LIMIT) {
    return { selected, limitReached: true };
  }
  return { selected: [...selected, sessionId], limitReached: false };
}

export function resolveSessionTitle(item: SessionTitleSource): string {
  if (typeof item.name === "string") {
    return item.name;
  }
  const meta = (item.metadata ?? {}) as Record<string, unknown>;
  return typeof meta.title === "string" ? meta.title : "";
}
