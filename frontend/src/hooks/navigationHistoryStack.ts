/**
 * 浏览器式导航历史栈（纯函数，供 useNavigationHistory 的 Provider 驱动）。
 *
 * - PUSH：截断前进分支后追加（浏览器语义）
 * - REPLACE：原位替换当前条目
 * - POP：按位移移动游标（后退/前进都算 POP）
 */

export interface NavHistoryStack {
  keys: string[];
  index: number;
}

export type NavigationAction =
  | { kind: "push"; key: string }
  | { kind: "replace"; key: string }
  | { kind: "pop"; delta: number; key: string };

export function createNavHistoryStack(initialKey: string): NavHistoryStack {
  return { keys: [initialKey], index: 0 };
}

export function applyNavigation(
  stack: NavHistoryStack,
  action: NavigationAction,
): NavHistoryStack {
  switch (action.kind) {
    case "push": {
      const keys = [...stack.keys.slice(0, stack.index + 1), action.key];
      return { keys, index: keys.length - 1 };
    }
    case "replace": {
      const keys = [...stack.keys];
      keys[stack.index] = action.key;
      return { keys, index: stack.index };
    }
    case "pop": {
      // delta 0（key 却变了）按原地替换处理，避免栈与地址不同步
      if (action.delta === 0) {
        return applyNavigation(stack, {
          kind: "replace",
          key: action.key,
        });
      }
      const index = Math.min(
        Math.max(stack.index + action.delta, 0),
        stack.keys.length - 1,
      );
      const keys = [...stack.keys];
      keys[index] = action.key;
      return { keys, index };
    }
  }
}

export function canGoBack(stack: NavHistoryStack): boolean {
  return stack.index > 0;
}

export function canGoForward(stack: NavHistoryStack): boolean {
  return stack.index < stack.keys.length - 1;
}

/** 从 react-router 维护的 history.state.idx 推导 POP 位移；任一侧缺失返回 null */
export function resolvePopDelta(
  prevIdx: number | null,
  nextIdx: number | null,
): number | null {
  if (prevIdx === null || nextIdx === null) return null;
  return nextIdx - prevIdx;
}
