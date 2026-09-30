/** Align fixed panel chrome with its independently scrolling content. */
export function observePanelWidths(root: HTMLElement): () => void {
  if (typeof ResizeObserver === "undefined") return () => {};
  const scopes = new Map<HTMLElement, HTMLElement>();
  const update = () => {
    let maxGutter = 0;
    for (const [body, scope] of scopes) {
      const border = getComputedStyle(body);
      const gutter =
        body.offsetWidth -
        body.clientWidth -
        (parseFloat(border.borderLeftWidth) || 0) -
        (parseFloat(border.borderRightWidth) || 0);
      maxGutter = Math.max(maxGutter, gutter);
      scope.style.setProperty("--panel-scrollbar", `${Math.max(0, gutter)}px`);
    }
    root.style.setProperty("--panel-scrollbar", `${maxGutter}px`);
  };
  const resize = new ResizeObserver(update);
  const sync = () => {
    for (const [body, scope] of scopes) {
      if (!root.contains(body)) {
        resize.unobserve(body);
        scope.style.removeProperty("--panel-scrollbar");
        scopes.delete(body);
      }
    }
    for (const body of root.querySelectorAll<HTMLElement>(
      ".panel-body.overflow-y-auto, .panel-scroll, .editor-sidebar-body",
    )) {
      if (!scopes.has(body) && body.parentElement) {
        scopes.set(body, body.parentElement);
        resize.observe(body);
      }
    }
    update();
  };
  const mutations = new MutationObserver(sync);
  mutations.observe(root, { childList: true, subtree: true });
  sync();
  return () => {
    mutations.disconnect();
    resize.disconnect();
    root.style.removeProperty("--panel-scrollbar");
    for (const scope of scopes.values())
      scope.style.removeProperty("--panel-scrollbar");
  };
}
