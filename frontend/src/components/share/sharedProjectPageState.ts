import type { SharedProjectContentResponse } from "../../types";

/**
 * 推断项目分享 manifest 是否还有更多会话可加载。
 *
 * 优先使用后端显式返回的 has_more；老数据缺省时，退化为
 * 「已加载会话数 < 会话总数」的兜底判断。
 */
export function computeProjectHasMore(
  manifest: SharedProjectContentResponse | null,
): boolean {
  if (!manifest) {
    return false;
  }
  return (
    manifest.has_more ?? manifest.sessions.length < manifest.sessions_total
  );
}
