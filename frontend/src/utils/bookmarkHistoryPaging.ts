/**
 * 书签深跳转的历史翻页：目标消息不在首屏窗口时，
 * 循环加载更早一页直到出现，或确认历史已到头。
 */

export interface LoadUntilFoundControls {
  /** 目标消息是否已在当前列表中 */
  isFound: () => boolean;
  /** 是否还有更早的轮次可加载 */
  hasMore: () => boolean;
  /** 加载更早一页（与滚动到顶的自动预加载同一入口） */
  loadOlder: () => void | Promise<void>;
  /** 每页加载后等待状态落盘 */
  sleep?: (ms: number) => Promise<void>;
}

export interface LoadUntilFoundOptions {
  /** 最多翻多少页，防止超长会话下无限循环 */
  maxPages?: number;
  /** 每页后的等待时长（React 状态提交需要一拍） */
  settleDelayMs?: number;
}

export type LoadUntilFoundResult = "found" | "exhausted";

const DEFAULT_MAX_PAGES = 25;
const DEFAULT_SETTLE_DELAY_MS = 80;

const defaultSleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function loadHistoryUntilMessageFound(
  controls: LoadUntilFoundControls,
  options: LoadUntilFoundOptions = {},
): Promise<LoadUntilFoundResult> {
  const maxPages = options.maxPages ?? DEFAULT_MAX_PAGES;
  const settleDelayMs = options.settleDelayMs ?? DEFAULT_SETTLE_DELAY_MS;
  const sleep = controls.sleep ?? defaultSleep;

  for (let page = 0; page < maxPages; page += 1) {
    if (controls.isFound()) {
      return "found";
    }
    if (!controls.hasMore()) {
      return "exhausted";
    }
    await controls.loadOlder();
    await sleep(settleDelayMs);
  }

  return controls.isFound() ? "found" : "exhausted";
}
