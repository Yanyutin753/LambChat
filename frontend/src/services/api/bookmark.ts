/**
 * Bookmark API - 消息书签
 * 书签按 (session_id, message_id) 唯一，toggle 语义与会话 pin/favorite 一致。
 */

import { authFetch } from "./fetch";
import { API_BASE } from "./config";

export interface BookmarkItem {
  id: string;
  user_id: string;
  session_id: string;
  message_id: string;
  run_id: string | null;
  label: string | null;
  created_at: string;
  session_name: string | null;
  session_is_active: boolean;
}

export interface BookmarkListResponse {
  items: BookmarkItem[];
  total: number;
}

export interface BookmarkToggleResponse {
  status: string;
  bookmarked: boolean;
  bookmark: BookmarkItem | null;
}

export interface BookmarkToggleOptions {
  run_id?: string | null;
  label?: string | null;
}

export function buildMessageBookmarkUrl(
  sessionId: string,
  messageId: string,
): string {
  return `${API_BASE}/api/sessions/${sessionId}/messages/${messageId}/bookmark`;
}

export function buildMessageBookmarkBody(options?: BookmarkToggleOptions): {
  run_id: string | null;
  label: string | null;
} {
  return {
    run_id: options?.run_id ?? null,
    label: options?.label ?? null,
  };
}

export const bookmarkApi = {
  /** 获取当前用户全部书签（按创建时间倒序，联会话名） */
  async list(): Promise<BookmarkListResponse> {
    return authFetch<BookmarkListResponse>(`${API_BASE}/api/bookmarks/`);
  },

  /** 切换某条消息的书签状态 */
  async toggle(
    sessionId: string,
    messageId: string,
    options?: BookmarkToggleOptions,
  ): Promise<BookmarkToggleResponse> {
    return authFetch<BookmarkToggleResponse>(
      buildMessageBookmarkUrl(sessionId, messageId),
      {
        method: "POST",
        body: JSON.stringify(buildMessageBookmarkBody(options)),
      },
    );
  },
};
