/**
 * 消息列表跟随状态的轻量信号（模块级，非 React 状态）。
 *
 * useMessageScroll 在跟随/脱钩状态变化时写入；不经过 props 下钻，
 * 供深层组件（如 SubagentBlock 的自动开面板判定）同步读取：
 * 用户正在上滑阅读历史时，自动行为（自动开面板/自动弹预览）不应打断。
 */

interface StreamFollowSignal {
  /** 用户流式中主动上滑脱钩（manualDetachFromStream） */
  detached: boolean;
  /** 视口是否贴着消息底部 */
  nearBottom: boolean;
}

let signal: StreamFollowSignal = { detached: false, nearBottom: true };

export function setStreamFollowSignal(next: Partial<StreamFollowSignal>): void {
  signal = { ...signal, ...next };
}

export function getStreamFollowSignal(): StreamFollowSignal {
  return signal;
}

/** 用户是否正离开底部阅读历史（脱钩或明显不在底部） */
export function isUserReadingHistory(): boolean {
  return signal.detached || !signal.nearBottom;
}

/** 会话切换时重置为默认跟随态 */
export function resetStreamFollowSignal(): void {
  signal = { detached: false, nearBottom: true };
}
