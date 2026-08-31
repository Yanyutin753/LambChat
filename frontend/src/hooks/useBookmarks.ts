import { useEffect, useSyncExternalStore } from "react";
import {
  ensureBookmarksLoaded,
  getBookmarkStoreState,
  subscribeBookmarks,
} from "../stores/bookmarkStore";

/**
 * 订阅全局书签状态；首次挂载时触发一次列表加载。
 * 仅在已认证场景使用（消息操作栏、书签面板均已做认证门控）。
 */
export function useBookmarks() {
  const state = useSyncExternalStore(
    subscribeBookmarks,
    getBookmarkStoreState,
    getBookmarkStoreState,
  );

  useEffect(() => {
    if (state.status === "idle") {
      void ensureBookmarksLoaded();
    }
  }, [state.status]);

  return state;
}
