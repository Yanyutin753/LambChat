import { createSingletonStore } from "../components/chat/ChatMessage/items/createSingletonStore";
import { bookmarkApi, type BookmarkItem } from "../services/api/bookmark";
import { isBookmarked } from "../utils/bookmarks";

/**
 * 消息书签全局 store：消息操作栏的书签按钮与书签面板共享同一份数据，
 * 首次使用时懒加载一次列表，toggle 后同步更新。
 */

export type BookmarkStatus = "idle" | "loading" | "ready" | "error";

export interface BookmarkStoreState {
  status: BookmarkStatus;
  items: BookmarkItem[];
}

const store = createSingletonStore<BookmarkStoreState>({
  status: "idle",
  items: [],
});

/** 读取当前快照（useSyncExternalStore 用） */
export function getBookmarkStoreState(): BookmarkStoreState {
  return store.get();
}

/** 订阅书签变化（useSyncExternalStore 用） */
export function subscribeBookmarks(listener: () => void): () => void {
  return store.subscribe(listener);
}

let inflightLoad: Promise<void> | null = null;

/** 确保书签列表已加载；force 时强制刷新 */
export function ensureBookmarksLoaded(force = false): Promise<void> {
  const current = store.get();
  if (!force && (current.status === "loading" || current.status === "ready")) {
    return inflightLoad ?? Promise.resolve();
  }
  if (inflightLoad && current.status === "loading") {
    return inflightLoad;
  }

  inflightLoad = (async () => {
    store.set({ ...store.get(), status: "loading" });
    try {
      const response = await bookmarkApi.list();
      store.set({ status: "ready", items: response.items });
    } catch (error) {
      console.error("Failed to load bookmarks:", error);
      store.set({ ...store.get(), status: "error" });
    } finally {
      inflightLoad = null;
    }
  })();
  return inflightLoad;
}

function bookmarkMatches(item: BookmarkItem, sessionId: string, messageId: string) {
  return item.session_id === sessionId && item.message_id === messageId;
}

export interface ToggleMessageBookmarkParams {
  sessionId: string;
  messageId: string;
  runId?: string | null;
  label?: string | null;
}

/** 切换消息书签：移除时乐观更新，新增时以服务端返回为准 */
export async function toggleMessageBookmark(
  params: ToggleMessageBookmarkParams,
): Promise<{ bookmarked: boolean }> {
  const { sessionId, messageId, runId, label } = params;
  const { items } = store.get();

  if (isBookmarked(items, sessionId, messageId)) {
    store.set({
      ...store.get(),
      items: items.filter((item) => !bookmarkMatches(item, sessionId, messageId)),
    });
    try {
      await bookmarkApi.toggle(sessionId, messageId);
      return { bookmarked: false };
    } catch (error) {
      await ensureBookmarksLoaded(true);
      throw error;
    }
  }

  const response = await bookmarkApi.toggle(sessionId, messageId, {
    run_id: runId ?? null,
    label: label ?? null,
  });
  const currentItems = store.get().items;
  const rest = currentItems.filter(
    (item) => !bookmarkMatches(item, sessionId, messageId),
  );
  store.set({
    ...store.get(),
    items: response.bookmarked && response.bookmark
      ? [response.bookmark, ...rest]
      : rest,
  });
  return { bookmarked: response.bookmarked };
}
