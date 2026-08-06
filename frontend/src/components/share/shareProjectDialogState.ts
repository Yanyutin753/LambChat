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

export function resolveSessionTitle(item: SessionTitleSource): string {
  if (typeof item.name === "string") {
    return item.name;
  }
  const meta = (item.metadata ?? {}) as Record<string, unknown>;
  return typeof meta.title === "string" ? meta.title : "";
}
