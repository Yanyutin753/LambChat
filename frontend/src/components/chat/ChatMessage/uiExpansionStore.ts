import { useCallback, useState } from "react";

/**
 * 行内 UI 状态（展开/收起）的会话级内存存储。
 *
 * 消息列表是虚拟列表：行滚出视口即卸载，组件本地 state 随之蒸发，
 * 滚回来后"自己收回去"。react-virtuoso 维护者的官方建议（issue #141/#298）
 * 就是把这类状态存到组件树外部、按稳定 key 键控，重挂载时复水。
 *
 * 生命周期与 store 系列一致：仅内存、按会话清空，不持久化到任何存储。
 */

const expandedStates = new Map<string, boolean>();

export function getUiExpansion(key: string): boolean | undefined {
  return expandedStates.get(key);
}

export function setUiExpansion(key: string, expanded: boolean): void {
  expandedStates.set(key, expanded);
}

export function deleteUiExpansion(key: string): void {
  expandedStates.delete(key);
}

export function clearUiExpansions(): void {
  expandedStates.clear();
}

/**
 * 虚拟化行内展开/收起状态：挂载时从 store 复水，切换时写回。
 * 只有宿主组件读写自己的 key，无需订阅广播。
 */
export function useUiExpansionState(
  key: string | undefined,
  defaultExpanded: boolean,
) {
  const [expanded, setExpanded] = useState(() =>
    key !== undefined
      ? getUiExpansion(key) ?? defaultExpanded
      : defaultExpanded,
  );

  const toggle = useCallback(() => {
    setExpanded((value) => {
      const next = !value;
      if (key !== undefined) setUiExpansion(key, next);
      return next;
    });
  }, [key]);

  const reset = useCallback(
    (next: boolean) => {
      setExpanded(next);
      if (key !== undefined) {
        if (next === defaultExpanded) {
          deleteUiExpansion(key);
        } else {
          setUiExpansion(key, next);
        }
      }
    },
    [key, defaultExpanded],
  );

  // 卸载不清理：状态要跨虚拟化卸载存活，由会话切换统一清空

  return [expanded, toggle, reset] as const;
}
