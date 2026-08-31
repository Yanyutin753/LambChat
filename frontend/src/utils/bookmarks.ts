/**
 * 消息书签纯工具函数：匹配、摘要、跳转路径推导。
 */

export interface BookmarkIdentity {
  session_id: string;
  message_id: string;
  run_id?: string | null;
}

type BookmarkLike = {
  session_id: string;
  message_id: string;
};

/** 判断某条消息是否已收藏（按 session + message 二元组匹配） */
export function isBookmarked(
  items: readonly BookmarkLike[] | null | undefined,
  sessionId: string,
  messageId: string,
): boolean {
  if (!items) {
    return false;
  }
  return items.some(
    (item) => item.session_id === sessionId && item.message_id === messageId,
  );
}

/** 把消息内容压成单行摘要，超长截断，作为书签列表展示文案 */
export function buildBookmarkLabel(text: string, maxLength = 80): string {
  const collapsed = (text ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!collapsed) {
    return "";
  }
  if (collapsed.length <= maxLength) {
    return collapsed;
  }
  return `${collapsed.slice(0, Math.max(0, maxLength - 1))}…`;
}

const USER_MESSAGE_ID_SUFFIX = ":user";

/** 推导跳转用的 run_id：优先存档值，其次从 "{run_id}:user" 形态剥离 */
export function deriveRunIdForJump(bookmark: BookmarkIdentity): string | null {
  if (bookmark.run_id?.trim()) {
    return bookmark.run_id;
  }
  const messageId = bookmark.message_id;
  if (messageId.endsWith(USER_MESSAGE_ID_SUFFIX)) {
    const runId = messageId.slice(0, -USER_MESSAGE_ID_SUFFIX.length);
    if (runId) {
      return runId;
    }
  }
  return null;
}

/** 书签跳转路径：切到对应会话并携带 run_id 深链（复用外部导航高亮机制） */
export function buildBookmarkNavigatePath(bookmark: BookmarkIdentity): string {
  const runId = deriveRunIdForJump(bookmark);
  const base = `/chat/${encodeURIComponent(bookmark.session_id)}`;
  return runId
    ? `${base}?run_id=${encodeURIComponent(runId)}`
    : base;
}
