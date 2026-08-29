export type SidebarSnapshotLocator =
  | { key: string }
  | { path: readonly number[] };

export interface SidebarPanelSnapshot {
  panelKey: string;
  expanded: ReadonlyArray<{
    locator: SidebarSnapshotLocator;
    expanded: boolean;
  }>;
  pressed: ReadonlyArray<{
    locator: SidebarSnapshotLocator;
    pressed: boolean;
  }>;
  details: ReadonlyArray<{
    locator: SidebarSnapshotLocator;
    open: boolean;
  }>;
  scroll: ReadonlyArray<{
    locator: SidebarSnapshotLocator;
    top: number;
    left: number;
  }>;
}

interface ActiveSnapshotTarget {
  panelKey: string;
  root: HTMLElement;
}

let activeTarget: ActiveSnapshotTarget | null = null;
let pendingSnapshot: SidebarPanelSnapshot | null = null;

function locateElement(
  root: HTMLElement,
  element: HTMLElement,
): SidebarSnapshotLocator | null {
  const key = element.dataset.sidebarSnapshotKey;
  if (key) return { key };

  const path: number[] = [];
  let current: HTMLElement | null = element;
  while (current && current !== root) {
    const parent: HTMLElement | null = current.parentElement;
    if (!parent) return null;
    const index = Array.prototype.indexOf.call(
      parent.children,
      current,
    ) as number;
    if (index < 0) return null;
    path.unshift(index);
    current = parent;
  }
  return current === root ? { path } : null;
}

function resolveElement(
  root: HTMLElement,
  locator: SidebarSnapshotLocator,
): HTMLElement | null {
  if ("key" in locator) {
    const candidates = [root, ...root.querySelectorAll<HTMLElement>("*")];
    return (
      candidates.find(
        (element) => element.dataset.sidebarSnapshotKey === locator.key,
      ) ?? null
    );
  }

  let current: Element = root;
  for (const index of locator.path) {
    const next = current.children.item(index);
    if (!next) return null;
    current = next;
  }
  return current instanceof HTMLElement ? current : null;
}

function isScrollable(element: HTMLElement): boolean {
  return (
    element.scrollTop !== 0 ||
    element.scrollLeft !== 0 ||
    element.scrollHeight > element.clientHeight ||
    element.scrollWidth > element.clientWidth
  );
}

function waitForAnimationFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => resolve());
      return;
    }
    setTimeout(resolve, 0);
  });
}

/**
 * 恢复重试的时间窗口：面板内容常为 lazy 加载（DeferredSubagentPanelContent
 * 的 React.lazy）或流式增长，固定 4-5 帧重试会赶不上 DOM 就绪；按截止
 * 时间持续重试（rAF 间隔），覆盖 ~600ms 内陆续就位的节点。
 */
const RESTORE_DEADLINE_MS = 600;

async function restoreUntilDeadline(
  deadlineMs: number,
  pass: () => boolean,
): Promise<void> {
  while (true) {
    const settled = pass();
    if (settled) return;
    if (performance.now() >= deadlineMs) return;
    await waitForAnimationFrame();
  }
}

export function registerActiveSidebarSnapshotTarget(
  panelKey: string,
  root: HTMLElement,
): () => void {
  const target = { panelKey, root };
  activeTarget = target;
  return () => {
    if (activeTarget === target) activeTarget = null;
  };
}

export function captureActiveSidebarPanelSnapshot(): SidebarPanelSnapshot | null {
  if (!activeTarget) return null;
  const { panelKey, root } = activeTarget;

  const expanded = [...root.querySelectorAll<HTMLElement>("[aria-expanded]")]
    .map((element) => {
      const locator = locateElement(root, element);
      if (!locator) return null;
      return {
        locator,
        expanded: element.getAttribute("aria-expanded") === "true",
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  const details = [...root.querySelectorAll<HTMLDetailsElement>("details")]
    .map((element) => {
      const locator = locateElement(root, element);
      if (!locator) return null;
      return { locator, open: element.open };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  const pressed = [...root.querySelectorAll<HTMLElement>("[aria-pressed]")]
    .map((element) => {
      const locator = locateElement(root, element);
      if (!locator) return null;
      return {
        locator,
        pressed: element.getAttribute("aria-pressed") === "true",
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  const scroll = [root, ...root.querySelectorAll<HTMLElement>("*")]
    .filter(isScrollable)
    .map((element) => {
      const locator = locateElement(root, element);
      if (!locator) return null;
      return {
        locator,
        top: element.scrollTop,
        left: element.scrollLeft,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  return { panelKey, expanded, pressed, details, scroll };
}

export function queueSidebarPanelSnapshot(
  snapshot: SidebarPanelSnapshot | null,
): void {
  pendingSnapshot = snapshot;
}

export async function restorePendingSidebarPanelSnapshot(
  panelKey: string,
  root: HTMLElement,
): Promise<boolean> {
  const snapshot = pendingSnapshot;
  if (!snapshot) return false;
  if (snapshot.panelKey !== panelKey) {
    // 其他面板的残留快照直接丢弃，避免之后同 key 面板误吃旧状态
    pendingSnapshot = null;
    return false;
  }
  pendingSnapshot = null;

  const deadlineMs = performance.now() + RESTORE_DEADLINE_MS;

  await restoreUntilDeadline(deadlineMs, () => {
    let needsAnotherPass = false;
    snapshot.expanded.forEach(({ locator, expanded }) => {
      const element = resolveElement(root, locator);
      if (!element) {
        needsAnotherPass = true;
        return;
      }
      const current = element.getAttribute("aria-expanded") === "true";
      if (current !== expanded) {
        element.click();
        needsAnotherPass = true;
      }
    });
    snapshot.pressed.forEach(({ locator, pressed }) => {
      const element = resolveElement(root, locator);
      if (!element) {
        needsAnotherPass = true;
        return;
      }
      const current = element.getAttribute("aria-pressed") === "true";
      if (current !== pressed) {
        element.click();
        needsAnotherPass = true;
      }
    });
    snapshot.details.forEach(({ locator, open }) => {
      const element = resolveElement(root, locator);
      if (!(element instanceof HTMLDetailsElement)) {
        needsAnotherPass = true;
        return;
      }
      element.open = open;
    });
    return !needsAnotherPass;
  });

  await restoreUntilDeadline(deadlineMs, () => {
    let resolvedAny = false;
    snapshot.scroll.forEach(({ locator, top, left }) => {
      const element = resolveElement(root, locator);
      if (!element) return;
      element.scrollTop = top;
      element.scrollLeft = left;
      resolvedAny = true;
    });
    // 滚动容器找到即可结束；内容其后继续增高由各面板自身的贴底逻辑兜底
    return snapshot.scroll.length === 0 || resolvedAny;
  });

  return true;
}

export function clearSidebarPanelSnapshots(): void {
  activeTarget = null;
  pendingSnapshot = null;
}
