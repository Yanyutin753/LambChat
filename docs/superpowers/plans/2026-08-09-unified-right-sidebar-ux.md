# Unified Right Sidebar UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every top-level right-side editor and content panel share one predictable, accessible, responsive workspace with restrained automatic opening.

**Architecture:** Add a small right-panel stack coordinator consumed internally by `EditorSidebar` and `ToolResultPanel`, then move viewport presentation and width calculations into tested shared helpers. Keep specialized editor and tool content unchanged while unifying lifecycle, Back/Close semantics, focus, resizing, layout compression, and subagent auto-open policy.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, CSS/Tailwind, i18next, Vite.

## Global Constraints

- Use TDD: write each focused test first, run it and observe failure, then add the minimum implementation.
- Only one top-level right panel is visible and layout-active at a time.
- Docked mode starts at `1200px`; overlay mode is `640px` through `1199px`; full-screen mode is below `640px`.
- Rich-content width defaults to `48%`; editor width defaults to `34%`.
- Preserve separate existing storage keys: `sidebar-preview-width` and `editor-sidebar-width`.
- Preserve local drafts, loaded content, and scroll position when a hidden panel is restored.
- Automatic subagent and file/project preview panels are docked-wide-screen-only, once per logical key, lane-empty-only, dismissible, and must not steal focus.
- Mobile controls must expose at least a `44px` square hit area; adjacent header actions use at least `8px` spacing.
- Docked panels are non-modal; overlay and full-screen panels use dialog semantics, background blocking, and focus containment.
- Honor `prefers-reduced-motion` for panel entrance, exit, and content-opacity transitions.
- Update all five locales for any new user-facing or accessibility copy.
- Preserve backend APIs and individual editor/preview content behavior.

---

## File Structure

### New files

- `frontend/src/components/common/rightPanelCoordinator.ts`: framework-free stack state, subscription, deliberate-panel occupancy, and active-entry close operations.
- `frontend/src/components/common/useRightPanelEntry.ts`: React registration, opener capture, active-state subscription, and focus restoration for one shared panel renderer.
- `frontend/src/components/common/__tests__/rightPanelCoordinator.test.ts`: stack ordering, duplicate registration, automatic-entry rejection, close idempotence, and occupancy tests.
- `frontend/src/hooks/rightPanelLayout.ts`: breakpoint selection, stored-width sanitation, panel-width clamping, keyboard resizing, and remaining-workspace calculations.
- `frontend/src/hooks/__tests__/rightPanelLayout.test.ts`: pure layout and resize tests.
- `frontend/src/components/common/__tests__/rightPanelShell.test.tsx`: cross-family visibility, Back, Escape, focus, and semantic integration tests.
- `frontend/src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts`: verifies runtime wiring uses coordinated occupancy and keyed auto-open state.
- `frontend/src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts`: verifies file/project automatic previews use the same lane-empty policy and expose automatic intent to the renderer.

### Modified files

- `frontend/src/hooks/useSidebarPanel.ts`: consume presentation/width helpers, apply layout only for the active entry, expose keyboard resize props, and manage modal focus/scroll behavior.
- `frontend/src/hooks/rightPanelWidthEvents.ts`: send an active-panel layout snapshot in the existing event.
- `frontend/src/components/common/EditorSidebar.tsx`: register with the coordinator, keep suspended drafts mounted but expose only the active entry, add Back, shared toolbar controls, semantics, and responsive presentation classes.
- `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx`: register with the coordinator, combine tool and cross-family Back history, use responsive presentation, and expose automatic-opening intent.
- `frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx`: pass `auto` to the shared renderer and reject automatic opens unless the docked lane is empty.
- `frontend/src/components/layout/AppContent/rightPanelAutoCollapse.ts`: replace summed percentages with active docked width and remaining-pixel logic.
- `frontend/src/components/layout/AppContent/index.tsx`: subscribe to the active layout snapshot and scope manual navigation overrides to the current panel stack.
- `frontend/src/components/chat/ChatMessage/subagentPanelControl.ts`: replace the global boolean with keyed dismissed/opened sets.
- `frontend/src/components/chat/ChatMessage/SubagentBlock.tsx`: use panel-keyed state and coordinated lane occupancy.
- `frontend/src/components/common/ui/ToolbarIconButton.tsx`: consistent focus-visible and mobile target behavior.
- `frontend/src/styles/base.css`: compress the app for one active docked lane only; remove combined-width rules.
- `frontend/src/styles/components.css`: shared docked/overlay/full-screen chrome, 44px touch actions, separator states, modal backdrop, and reduced motion.
- `frontend/src/i18n/locales/{en,zh,ja,ko,ru}.json`: localized resize-separator label.
- Existing focused test files listed in the tasks below.

---

### Task 1: Framework-Free Right-Panel Coordinator

**Files:**
- Create: `frontend/src/components/common/rightPanelCoordinator.ts`
- Create: `frontend/src/components/common/__tests__/rightPanelCoordinator.test.ts`

**Interfaces:**
- Produces: `RightPanelKind`, `RightPanelEntry`, `RightPanelSnapshot`, `registerRightPanel(entry): boolean`, `updateRightPanel(entry)`, `unregisterRightPanel(id)`, `getRightPanelSnapshot()`, `subscribeRightPanels(listener)`, `closeActiveRightPanel()`, `hasOpenRightPanel()`, `hasDeliberateRightPanel()`, and `resetRightPanelCoordinator()`.
- Consumes: no React or DOM APIs except the opaque `HTMLElement | null` opener stored in an entry.

- [ ] **Step 1: Write failing coordinator tests**

```ts
import {
  closeActiveRightPanel,
  getRightPanelSnapshot,
  hasOpenRightPanel,
  hasDeliberateRightPanel,
  registerRightPanel,
  resetRightPanelCoordinator,
  unregisterRightPanel,
} from "../rightPanelCoordinator";

beforeEach(resetRightPanelCoordinator);

test("keeps one active entry and reveals the previous entry after unmount", () => {
  const editor = { id: Symbol("editor"), kind: "editor" as const, automatic: false, close: vi.fn(), opener: null };
  const content = { id: Symbol("content"), kind: "content" as const, automatic: false, close: vi.fn(), opener: null };

  expect(registerRightPanel(editor)).toBe(true);
  expect(registerRightPanel(content)).toBe(true);
  expect(getRightPanelSnapshot()).toMatchObject({ activeId: content.id, depth: 2 });

  unregisterRightPanel(content.id);
  expect(getRightPanelSnapshot()).toMatchObject({ activeId: editor.id, depth: 1 });
});

test("updates duplicate owners without duplicating stack history", () => {
  const id = Symbol("editor");
  registerRightPanel({ id, kind: "editor", automatic: false, close: vi.fn(), opener: null });
  registerRightPanel({ id, kind: "editor", automatic: false, close: vi.fn(), opener: null });
  expect(getRightPanelSnapshot().depth).toBe(1);
});

test("rejects automatic entries whenever the lane is occupied", () => {
  registerRightPanel({ id: Symbol("existing"), kind: "content", automatic: true, close: vi.fn(), opener: null });
  expect(registerRightPanel({ id: Symbol("auto"), kind: "content", automatic: true, close: vi.fn(), opener: null })).toBe(false);
  expect(hasOpenRightPanel()).toBe(true);
  expect(hasDeliberateRightPanel()).toBe(false);
});

test("removes an automatic entry when deliberate work opens", () => {
  const closeAuto = vi.fn();
  registerRightPanel({ id: Symbol("auto"), kind: "content", automatic: true, close: closeAuto, opener: null });
  const editorId = Symbol("editor");
  registerRightPanel({ id: editorId, kind: "editor", automatic: false, close: vi.fn(), opener: null });
  expect(closeAuto).toHaveBeenCalledTimes(1);
  expect(getRightPanelSnapshot()).toMatchObject({ activeId: editorId, depth: 1 });
});

test("asks the active owner to close once and waits for unregister", () => {
  const close = vi.fn();
  const id = Symbol("content");
  registerRightPanel({ id, kind: "content", automatic: false, close, opener: null });
  closeActiveRightPanel();
  closeActiveRightPanel();
  expect(close).toHaveBeenCalledTimes(1);
  expect(getRightPanelSnapshot().activeId).toBe(id);
});
```

- [ ] **Step 2: Run the coordinator test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelCoordinator.test.ts`

Expected: FAIL because `rightPanelCoordinator.ts` does not exist.

- [ ] **Step 3: Implement the coordinator store**

```ts
export type RightPanelKind = "editor" | "content";

export interface RightPanelEntry {
  id: symbol;
  kind: RightPanelKind;
  automatic: boolean;
  close: () => void;
  opener: HTMLElement | null;
}

export interface RightPanelSnapshot {
  activeId: symbol | null;
  activeKind: RightPanelKind | null;
  depth: number;
  hasDeliberatePanel: boolean;
}

let entries: RightPanelEntry[] = [];
let closingId: symbol | null = null;
const listeners = new Set<() => void>();

let snapshot: RightPanelSnapshot = {
  activeId: null,
  activeKind: null,
  depth: 0,
  hasDeliberatePanel: false,
};

function emit() {
  const active = entries.at(-1) ?? null;
  snapshot = {
    activeId: active?.id ?? null,
    activeKind: active?.kind ?? null,
    depth: entries.length,
    hasDeliberatePanel: entries.some((entry) => !entry.automatic),
  };
  listeners.forEach((listener) => listener());
}

export function registerRightPanel(entry: RightPanelEntry): boolean {
  const index = entries.findIndex((candidate) => candidate.id === entry.id);
  if (index >= 0) {
    entries = [...entries.slice(0, index), ...entries.slice(index + 1), entry];
    closingId = null;
    emit();
    return true;
  }
  if (entry.automatic && entries.length > 0) return false;
  if (!entry.automatic) {
    const automaticEntries = entries.filter((candidate) => candidate.automatic);
    entries = entries.filter((candidate) => !candidate.automatic);
    automaticEntries.forEach((candidate) => candidate.close());
  }
  entries = [...entries, entry];
  closingId = null;
  emit();
  return true;
}

export function updateRightPanel(entry: RightPanelEntry): void {
  const index = entries.findIndex((candidate) => candidate.id === entry.id);
  if (index < 0) return;
  entries = entries.map((candidate, candidateIndex) => candidateIndex === index ? entry : candidate);
  emit();
}

export function unregisterRightPanel(id: symbol): void {
  const next = entries.filter((entry) => entry.id !== id);
  if (next.length === entries.length) return;
  entries = next;
  if (closingId === id) closingId = null;
  emit();
}

export function getRightPanelSnapshot(): RightPanelSnapshot {
  return snapshot;
}

export function subscribeRightPanels(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function hasDeliberateRightPanel(): boolean {
  return getRightPanelSnapshot().hasDeliberatePanel;
}

export function hasOpenRightPanel(): boolean {
  return getRightPanelSnapshot().depth > 0;
}

export function closeActiveRightPanel(): void {
  const active = entries.at(-1);
  if (!active || closingId === active.id) return;
  closingId = active.id;
  active.close();
}

export function resetRightPanelCoordinator(): void {
  entries = [];
  closingId = null;
  emit();
}
```

Keep the cached `snapshot` object stable between mutations so React's
`useSyncExternalStore` does not observe a new object on every read.

- [ ] **Step 4: Run the coordinator test and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelCoordinator.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the coordinator**

```bash
git add frontend/src/components/common/rightPanelCoordinator.ts frontend/src/components/common/__tests__/rightPanelCoordinator.test.ts
git commit -m "feat(ui): coordinate right panel stack"
```

---

### Task 2: Responsive Presentation and Width Math

**Files:**
- Create: `frontend/src/hooks/rightPanelLayout.ts`
- Create: `frontend/src/hooks/__tests__/rightPanelLayout.test.ts`
- Modify: `frontend/src/hooks/rightPanelWidthEvents.ts:1-7`

**Interfaces:**
- Produces: `RightPanelPresentation`, `RightPanelLayoutSnapshot`, `getRightPanelPresentation(viewportWidth)`, `shouldAllowAutomaticRightPanel({ presentation, laneOccupied })`, `sanitizePanelWidthPct(raw, fallback)`, `clampPanelWidthPct(options)`, `resizePanelWidthPct(options)`, and `notifyRightPanelWidthChanged(snapshot?, target?)`.
- Consumes: `RightPanelKind` from Task 1.

- [ ] **Step 1: Write failing layout tests**

```ts
import {
  clampPanelWidthPct,
  getRightPanelPresentation,
  resizePanelWidthPct,
  sanitizePanelWidthPct,
  shouldAllowAutomaticRightPanel,
} from "../rightPanelLayout";

test("selects docked overlay and fullscreen presentations", () => {
  expect(getRightPanelPresentation(1200)).toBe("docked");
  expect(getRightPanelPresentation(1199)).toBe("overlay");
  expect(getRightPanelPresentation(640)).toBe("overlay");
  expect(getRightPanelPresentation(639)).toBe("fullscreen");
});

test("allows automatic panels only in an empty docked lane", () => {
  expect(shouldAllowAutomaticRightPanel({ presentation: "docked", laneOccupied: false })).toBe(true);
  expect(shouldAllowAutomaticRightPanel({ presentation: "docked", laneOccupied: true })).toBe(false);
  expect(shouldAllowAutomaticRightPanel({ presentation: "overlay", laneOccupied: false })).toBe(false);
  expect(shouldAllowAutomaticRightPanel({ presentation: "fullscreen", laneOccupied: false })).toBe(false);
});

test("sanitizes and clamps stored widths to preserve panel and workspace", () => {
  expect(sanitizePanelWidthPct("nope", 48)).toBe(48);
  expect(clampPanelWidthPct({ requestedPct: 75, viewportWidth: 1200, minPanelPx: 320, minMainPx: 560 })).toBe(53);
  expect(clampPanelWidthPct({ requestedPct: 10, viewportWidth: 1440, minPanelPx: 360, minMainPx: 560 })).toBe(25);
});

test("resizes with normal and shifted keyboard steps and resets home", () => {
  const base = { currentPct: 48, viewportWidth: 1440, minPanelPx: 360, minMainPx: 560, defaultPct: 48 };
  expect(resizePanelWidthPct({ ...base, key: "ArrowLeft", shiftKey: false })).toBe(47);
  expect(resizePanelWidthPct({ ...base, key: "ArrowRight", shiftKey: true })).toBe(53);
  expect(resizePanelWidthPct({ ...base, currentPct: 60, key: "Home", shiftKey: false })).toBe(48);
});
```

- [ ] **Step 2: Run the layout test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/rightPanelLayout.test.ts`

Expected: FAIL because `rightPanelLayout.ts` does not exist.

- [ ] **Step 3: Implement pure layout helpers and typed event detail**

```ts
export type RightPanelPresentation = "docked" | "overlay" | "fullscreen";

export interface RightPanelLayoutSnapshot {
  open: boolean;
  kind: "editor" | "content" | null;
  presentation: RightPanelPresentation | null;
  widthPct: number;
  widthPx: number;
  viewportWidth: number;
}

export function getRightPanelPresentation(viewportWidth: number): RightPanelPresentation {
  if (viewportWidth < 640) return "fullscreen";
  if (viewportWidth < 1200) return "overlay";
  return "docked";
}

export function shouldAllowAutomaticRightPanel({ presentation, laneOccupied }: {
  presentation: RightPanelPresentation;
  laneOccupied: boolean;
}): boolean {
  return presentation === "docked" && !laneOccupied;
}

export function sanitizePanelWidthPct(raw: string | null | undefined, fallback: number): number {
  const parsed = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function clampPanelWidthPct({ requestedPct, viewportWidth, minPanelPx, minMainPx }: {
  requestedPct: number; viewportWidth: number; minPanelPx: number; minMainPx: number;
}): number {
  const minimum = Math.ceil((minPanelPx / viewportWidth) * 100);
  const maximum = Math.floor(((viewportWidth - minMainPx) / viewportWidth) * 100);
  return Math.round(Math.min(Math.max(requestedPct, minimum), Math.max(minimum, maximum)));
}

export function resizePanelWidthPct(options: {
  currentPct: number; viewportWidth: number; minPanelPx: number; minMainPx: number;
  defaultPct: number; key: string; shiftKey: boolean;
}): number | null {
  const step = options.shiftKey ? 5 : 1;
  const requested = options.key === "Home" ? options.defaultPct
    : options.key === "ArrowLeft" ? options.currentPct - step
    : options.key === "ArrowRight" ? options.currentPct + step : null;
  return requested === null ? null : clampPanelWidthPct({ ...options, requestedPct: requested });
}
```

Change the event to carry `RightPanelLayoutSnapshot | null`:

```ts
export function notifyRightPanelWidthChanged(
  detail: RightPanelLayoutSnapshot | null = null,
  target: EventTarget = window,
): void {
  target.dispatchEvent(new CustomEvent(RIGHT_PANEL_WIDTH_CHANGED_EVENT, { detail }));
}
```

- [ ] **Step 4: Run layout and existing auto-collapse tests**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/rightPanelLayout.test.ts src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts`

Expected: new tests PASS; existing tests may remain unchanged until Task 6 but must still compile.

- [ ] **Step 5: Commit layout helpers**

```bash
git add frontend/src/hooks/rightPanelLayout.ts frontend/src/hooks/rightPanelWidthEvents.ts frontend/src/hooks/__tests__/rightPanelLayout.test.ts
git commit -m "feat(ui): add responsive right panel layout policy"
```

---

### Task 3: Shared React Registration and Panel Hook

**Files:**
- Create: `frontend/src/components/common/useRightPanelEntry.ts`
- Modify: `frontend/src/hooks/useSidebarPanel.ts:1-244`
- Test: `frontend/src/components/common/__tests__/rightPanelShell.test.tsx`
- Test: `frontend/src/hooks/__tests__/resourceCleanupSource.test.ts`

**Interfaces:**
- Consumes: coordinator APIs from Task 1 and layout APIs from Task 2.
- Produces: `useRightPanelEntry({ open, onClose, kind, automatic })` returning `{ ownerId, active, hasPrevious, openerRef }`; `useRightPanelFocus({ active, automatic, presentation, panelRef, openerRef })`; expanded `useSidebarPanel` return containing `presentation`, `resizeSeparatorProps`, and `resetSidebarWidth`.

- [ ] **Step 1: Write failing hook behavior tests**

```tsx
/** @vitest-environment jsdom */
import { useState, type ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { resetRightPanelCoordinator } from "../rightPanelCoordinator";
import { useRightPanelEntry } from "../useRightPanelEntry";

function installMatchMedia(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("min-width: 1200px") ? width >= 1200
      : query.includes("max-width: 639px") ? width <= 639 : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

beforeEach(() => {
  resetRightPanelCoordinator();
  localStorage.clear();
  installMatchMedia(1440);
});

function TestPanel({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const entry = useRightPanelEntry({ open, onClose, kind: "editor" });
  if (!open) return null;
  return <section data-right-panel-root hidden={!entry.active} inert={!entry.active ? true : undefined} aria-label={title}>{children}</section>;
}

test("exposes only the top registered entry and restores the prior entry", async () => {
  const firstClose = vi.fn();
  const secondClose = vi.fn();
  const view = render(<><TestPanel open onClose={firstClose} title="First">first</TestPanel><TestPanel open onClose={secondClose} title="Second">second</TestPanel></>);
  expect(screen.getByText("first").closest("[data-right-panel-root]")).toHaveAttribute("hidden");
  expect(screen.getByText("second")).toBeInTheDocument();
  view.rerender(<><TestPanel open onClose={firstClose} title="First">first</TestPanel><TestPanel open={false} onClose={secondClose} title="Second">second</TestPanel></>);
  expect((await screen.findByText("first")).closest("[data-right-panel-root]")).not.toHaveAttribute("hidden");
});

test("keeps hidden editor DOM mounted so draft state survives Back", async () => {
  function Draft() {
    const [value, setValue] = useState("");
    return <input aria-label="draft" value={value} onChange={(event) => setValue(event.target.value)} />;
  }
  const user = userEvent.setup();
  const view = render(<><TestPanel open onClose={vi.fn()} title="First"><Draft /></TestPanel><TestPanel open={false} onClose={vi.fn()} title="Second">second</TestPanel></>);
  await user.type(screen.getByRole("textbox", { name: "draft" }), "kept");
  view.rerender(<><TestPanel open onClose={vi.fn()} title="First"><Draft /></TestPanel><TestPanel open onClose={vi.fn()} title="Second">second</TestPanel></>);
  view.rerender(<><TestPanel open onClose={vi.fn()} title="First"><Draft /></TestPanel><TestPanel open={false} onClose={vi.fn()} title="Second">second</TestPanel></>);
  expect(screen.getByRole("textbox", { name: "draft" })).toHaveValue("kept");
});
```

- [ ] **Step 2: Run the hook test and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx`

Expected: FAIL because `useRightPanelEntry.ts` does not exist.

- [ ] **Step 3: Implement `useRightPanelEntry`**

```ts
import { useEffect, useLayoutEffect, useRef, useSyncExternalStore, type RefObject } from "react";
import type { RightPanelPresentation } from "../../hooks/rightPanelLayout";
import {
  getRightPanelSnapshot,
  registerRightPanel,
  subscribeRightPanels,
  unregisterRightPanel,
  updateRightPanel,
  type RightPanelKind,
} from "./rightPanelCoordinator";

export function useRightPanelEntry({ open, onClose, kind, automatic = false }: {
  open: boolean; onClose: () => void; kind: RightPanelKind; automatic?: boolean;
}) {
  const ownerId = useRef(Symbol(`right-panel:${kind}`)).current;
  const openerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef(onClose);
  const automaticRef = useRef(automatic);
  closeRef.current = onClose;
  automaticRef.current = automatic;
  const snapshot = useSyncExternalStore(subscribeRightPanels, getRightPanelSnapshot, getRightPanelSnapshot);

  useLayoutEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const accepted = registerRightPanel({ id: ownerId, kind, automatic: automaticRef.current, close: () => closeRef.current(), opener: openerRef.current });
    if (!accepted) return;
    return () => unregisterRightPanel(ownerId);
  }, [open, ownerId, kind]);

  useLayoutEffect(() => {
    if (!open || snapshot.activeId !== ownerId) return;
    updateRightPanel({ id: ownerId, kind, automatic, close: () => closeRef.current(), opener: openerRef.current });
  }, [open, ownerId, kind, automatic, snapshot.activeId]);

  return {
    ownerId,
    active: open && snapshot.activeId === ownerId,
    hasPrevious: open && snapshot.activeId === ownerId && snapshot.depth > 1,
    openerRef,
  };
}
```

Add `useRightPanelFocus` in the same file. Use separate effects for activation
focus, modal containment, and close restoration so crossing the `1200px`
breakpoint never restores focus spuriously:

```ts
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function useRightPanelFocus({ active, automatic, presentation, panelRef, openerRef }: {
  active: boolean;
  automatic: boolean;
  presentation: RightPanelPresentation;
  panelRef: RefObject<HTMLElement | null>;
  openerRef: RefObject<HTMLElement | null>;
}) {
  const wasActive = useRef(false);

  useEffect(() => {
    if (active && !wasActive.current && !automatic) {
      queueMicrotask(() => {
        const panel = panelRef.current;
        const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
        (first ?? panel)?.focus({ preventScroll: true });
      });
    }
    if (!active && wasActive.current) {
      requestAnimationFrame(() => {
        if (openerRef.current?.isConnected) openerRef.current.focus({ preventScroll: true });
      });
    }
    wasActive.current = active;
  }, [active, automatic, openerRef, panelRef]);

  useEffect(() => () => {
    if (!wasActive.current) return;
    requestAnimationFrame(() => {
      if (openerRef.current?.isConnected) openerRef.current.focus({ preventScroll: true });
    });
  }, [openerRef]);

  useEffect(() => {
    if (!active || presentation === "docked") return;
    const root = document.getElementById("root");
    const previousInert = root?.inert ?? false;
    if (root) root.inert = true;
    const trapTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusable = [...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])]
        .filter((element) => !element.hidden && element.tabIndex >= 0);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", trapTab);
    return () => {
      document.removeEventListener("keydown", trapTab);
      if (root) root.inert = previousInert;
    };
  }, [active, presentation, panelRef]);
}
```

- [ ] **Step 4: Refactor `useSidebarPanel` around active presentation**

Replace `isMobile` as the primary branch with `presentation`. Add an optional
`presentationOverride?: "overlay" | "fullscreen"` input for explicit content
focus modes. Set compression data attributes only for `presentation ===
"docked"`; lock body scroll only for overlay/full-screen. Clamp stored values
without persisting on mount, publish the active layout snapshot, cancel pointer
resize on breakpoint changes, and expose separator props:

```ts
const resizeSeparatorProps = {
  role: "separator" as const,
  tabIndex: 0,
  "aria-orientation": "vertical" as const,
  "aria-valuemin": minimumPct,
  "aria-valuemax": maximumPct,
  "aria-valuenow": sidebarWidth,
  onKeyDown: handleResizeKeyDown,
  onDoubleClick: resetSidebarWidth,
};
```

Keep Escape registered only when `open` is the active-renderer value. Keep native document fullscreen precedence. Disable swipe-to-close because mobile top-level panels are now full-screen.

Both shared renderers must keep their portal subtree mounted while `open` is
true but `active` is false. Apply `hidden`, `aria-hidden="true"`, and `inert` to
the same stable panel root instead of returning `null`; pass `open: active` into
`useSidebarPanel` so suspended entries own no global listeners or layout state.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx src/hooks/__tests__/rightPanelLayout.test.ts src/hooks/__tests__/resourceCleanupSource.test.ts`

Expected: PASS with no leaked mouse listeners or resize capture element.

- [ ] **Step 6: Commit shared React lifecycle**

```bash
git add frontend/src/components/common/useRightPanelEntry.ts frontend/src/hooks/useSidebarPanel.ts frontend/src/components/common/__tests__/rightPanelShell.test.tsx frontend/src/hooks/__tests__/resourceCleanupSource.test.ts
git commit -m "feat(ui): share right panel lifecycle"
```

---

### Task 4: Migrate `EditorSidebar` to the Unified Lane

**Files:**
- Modify: `frontend/src/components/common/EditorSidebar.tsx:1-148`
- Modify: `frontend/src/components/common/__tests__/rightPanelShell.test.tsx`
- Modify: `frontend/src/__tests__/appSafeAreaSurfaces.test.ts`

**Interfaces:**
- Consumes: `useRightPanelEntry` and expanded `useSidebarPanel` from Task 3.
- Produces: coordinated editor panels with shared Back, Close, separator, presentation classes, and semantics.

- [ ] **Step 1: Add failing editor semantics and navigation tests**

```tsx
test("editor uses complementary semantics when docked", () => {
  render(<EditorSidebar open onClose={vi.fn()} title="Model editor">body</EditorSidebar>);
  expect(screen.getByRole("complementary", { name: "Model editor" })).toHaveAttribute("data-panel-presentation", "docked");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("editor close is labelled and resize rail is keyboard accessible", () => {
  render(<EditorSidebar open onClose={vi.fn()} title="Model editor">body</EditorSidebar>);
  expect(screen.getByRole("button", { name: /close/i })).toBeVisible();
  expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow");
});

test("editor uses modal dialog semantics in overlay and fullscreen modes", () => {
  installMatchMedia(1024);
  const view = render(<EditorSidebar open onClose={vi.fn()} title="Overlay editor">body</EditorSidebar>);
  expect(screen.getByRole("dialog", { name: "Overlay editor" })).toHaveAttribute("aria-modal", "true");
  view.unmount();
  installMatchMedia(390);
  render(<EditorSidebar open onClose={vi.fn()} title="Mobile editor">body</EditorSidebar>);
  expect(screen.getByRole("dialog", { name: "Mobile editor" })).toHaveAttribute("data-panel-presentation", "fullscreen");
});

test("manual close restores focus to the opening trigger", async () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return <><button onClick={() => setOpen(true)}>Open editor</button><EditorSidebar open={open} onClose={() => setOpen(false)} title="Editor">body</EditorSidebar></>;
  }
  const user = userEvent.setup();
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Open editor" });
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: /close/i }));
  await waitFor(() => expect(trigger).toHaveFocus());
});
```

- [ ] **Step 2: Run the editor tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx`

Expected: FAIL because the editor has no labelled region semantics and its close button has no accessible name.

- [ ] **Step 3: Implement editor coordination and shared header actions**

Use `useId()` for a title ID, `useTranslation()` for Back/Close labels,
`ToolbarIconButton` for both header actions, and `BackIcon` when `hasPrevious` is
true. Pass the active value to `useSidebarPanel`. Keep the stable panel DOM
mounted with `hidden={!entry.active}`, `aria-hidden={!entry.active}`, and
`inert={!entry.active ? true : undefined}` so form drafts and scroll positions
survive restoration. Change `DEFAULT_WIDTH` from `30` to `34`.

```tsx
const entry = useRightPanelEntry({ open, onClose, kind: "editor" });
const shell = useSidebarPanel({ open: entry.active, onClose, widthStorageKey, widthCssVar: CSS_VAR, defaultWidthPct, dataAttr: "data-editor-sidebar", panelKind: "editor" });
useRightPanelFocus({ active: entry.active, automatic: false, presentation: shell.presentation, panelRef: shell.panelRef, openerRef: entry.openerRef });
if (!open) return null;

<div
  data-right-panel-root
  hidden={!entry.active}
  inert={!entry.active ? true : undefined}
  role={shell.presentation === "docked" ? "complementary" : "dialog"}
  aria-modal={shell.presentation === "docked" ? undefined : true}
  aria-labelledby={titleId}
  data-panel-presentation={shell.presentation}
>
```

Back calls `onClose`, revealing the prior registered owner. Close also calls `onClose`; the coordinator prevents duplicate Escape listeners from closing more than one entry.

- [ ] **Step 4: Run editor and safe-area tests**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx src/__tests__/appSafeAreaSurfaces.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit editor migration**

```bash
git add frontend/src/components/common/EditorSidebar.tsx frontend/src/components/common/__tests__/rightPanelShell.test.tsx frontend/src/__tests__/appSafeAreaSurfaces.test.ts
git commit -m "feat(ui): unify editor sidebar behavior"
```

---

### Task 5: Migrate Tool and Persistent Content Panels

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx:1-614`
- Modify: `frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx:15-137`
- Modify: `frontend/src/components/chat/ChatMessage/items/sidebarHistoryStore.ts:1-61`
- Create: `frontend/src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts`
- Modify: `frontend/src/components/common/__tests__/rightPanelShell.test.tsx`

**Interfaces:**
- Consumes: unified coordinator/hook, presentation, and resize props.
- Produces: `automatic?: boolean` on `ToolResultPanelProps`; persistent host passes `panel.auto`; Back resolves explicit callback, tool history, then cross-family stack.

- [ ] **Step 1: Add failing cross-family and automatic-panel tests**

```tsx
test("a tool panel hides an editor and closing it restores the editor", async () => {
  const toolClose = vi.fn();
  const view = render(<><EditorSidebar open onClose={vi.fn()} title="Editor">draft</EditorSidebar><ToolResultPanel open onClose={toolClose} title="Preview">preview</ToolResultPanel></>);
  expect(screen.queryByText("draft")).not.toBeInTheDocument();
  expect(screen.getByText("preview")).toBeInTheDocument();
  view.rerender(<><EditorSidebar open onClose={vi.fn()} title="Editor">draft</EditorSidebar><ToolResultPanel open={false} onClose={toolClose} title="Preview">preview</ToolResultPanel></>);
  expect(await screen.findByText("draft")).toBeInTheDocument();
});

test("automatic tool panels do not replace a deliberate editor", () => {
  render(<><EditorSidebar open onClose={vi.fn()} title="Editor">draft</EditorSidebar><ToolResultPanel open automatic onClose={vi.fn()} title="Auto">auto</ToolResultPanel></>);
  expect(screen.getByText("draft")).toBeInTheDocument();
  expect(screen.getByText("auto").closest("[data-right-panel-root]")).toHaveAttribute("hidden");
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts`

Expected: FAIL because `ToolResultPanel` does not participate in the shared coordinator.

- [ ] **Step 3: Register `ToolResultPanel` and combine Back sources**

Add `automatic?: boolean`, call `useRightPanelEntry({ open, onClose:
handleUserClose, kind: "content", automatic })`, and use the entry's active
value for `useSidebarPanel`. Keep the same panel DOM mounted but hidden and
inert while another renderer is active. Change `DEFAULT_WIDTH_PCT` from `60` to
`48`. Call `useRightPanelFocus` with the entry's `automatic` flag so automatic
content never steals focus. Compute Back in this order:

```ts
const effectiveOnBack = onBack
  ?? (historyAvailable ? goBackSidebar : undefined)
  ?? (entry.hasPrevious ? handleUserClose : undefined);
```

Use the same region/dialog semantics as the editor. Make every mobile panel full-screen regardless of the legacy `mobileFillViewport` hint; retain that prop temporarily for source compatibility. Preserve center and native fullscreen view modes as explicit content-focused overrides.

Pass `presentationOverride={isFullscreen ? "fullscreen" : isCenter ?
"overlay" : undefined}` into `useSidebarPanel`. This prevents center or native
fullscreen content from reserving docked app width while retaining Escape,
scroll lock, and modal focus behavior.

- [ ] **Step 4: Make persistent automatic opens coordination-aware**

Before mutating the persistent store:

```ts
if (
  panel.auto &&
  !shouldAllowAutomaticRightPanel({
    presentation: getRightPanelPresentation(window.innerWidth),
    laneOccupied: hasOpenRightPanel(),
  })
) return;
```

Pass `automatic={panel.auto}` into `ToolResultPanel`. Keep current content-to-content history capture and make `clearSidebarHistory()` run only for explicit Close, not Back.

- [ ] **Step 5: Add explicit legacy history tests**

```ts
import {
  clearSidebarHistory,
  getSidebarHistoryLength,
  goBackSidebar,
  pushCurrentPanelToHistory,
  registerPanelCapture,
} from "../sidebarHistoryStore";

test("restores the latest captured legacy preview and clears history", () => {
  clearSidebarHistory();
  const restore = vi.fn();
  registerPanelCapture(() => ({ restore }));
  pushCurrentPanelToHistory();
  expect(getSidebarHistoryLength()).toBe(1);
  expect(goBackSidebar()).toBe(true);
  expect(restore).toHaveBeenCalledOnce();
  clearSidebarHistory();
  expect(getSidebarHistoryLength()).toBe(0);
});
```

- [ ] **Step 6: Run tool, history, and shell tests**

Run: `cd frontend && pnpm exec vitest run src/components/common/__tests__/rightPanelShell.test.tsx src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts src/components/chat/ChatMessage/items/__tests__/sidebarHistoryStore.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit tool migration**

```bash
git add frontend/src/components/chat/ChatMessage/items/ToolResultPanel.tsx frontend/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx frontend/src/components/chat/ChatMessage/items/sidebarHistoryStore.ts frontend/src/components/chat/ChatMessage/items/__tests__ frontend/src/components/common/__tests__/rightPanelShell.test.tsx
git commit -m "feat(ui): unify tool panel behavior"
```

---

### Task 6: Active-Width App Layout and Navigation Collapse

**Files:**
- Modify: `frontend/src/components/layout/AppContent/rightPanelAutoCollapse.ts:1-82`
- Modify: `frontend/src/components/layout/AppContent/index.tsx:1-163`
- Modify: `frontend/src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts:1-108`
- Modify: `frontend/src/styles/base.css:1-100`
- Modify: `frontend/src/styles/__tests__/editorSidebarChromeSource.test.ts:35-85`

**Interfaces:**
- Consumes: `RightPanelLayoutSnapshot` events from Tasks 2-5.
- Produces: `shouldTemporarilyCollapseNavigation({ layout, minimumWorkspaceWithNavigationPx, userOverrode })` and single-lane CSS compression.

- [ ] **Step 1: Replace percentage-sum tests with active-layout tests**

```ts
import { shouldTemporarilyCollapseNavigation } from "../rightPanelAutoCollapse";

const docked = { open: true, kind: "content" as const, presentation: "docked" as const, widthPct: 48, widthPx: 691, viewportWidth: 1440 };

test("collapses navigation only when active docked width leaves too little room", () => {
  expect(shouldTemporarilyCollapseNavigation({ layout: docked, minimumWorkspaceWithNavigationPx: 820, userOverrode: false })).toBe(true);
  expect(shouldTemporarilyCollapseNavigation({ layout: { ...docked, widthPx: 500 }, minimumWorkspaceWithNavigationPx: 820, userOverrode: false })).toBe(false);
  expect(shouldTemporarilyCollapseNavigation({ layout: { ...docked, presentation: "overlay" }, minimumWorkspaceWithNavigationPx: 820, userOverrode: false })).toBe(false);
  expect(shouldTemporarilyCollapseNavigation({ layout: docked, minimumWorkspaceWithNavigationPx: 820, userOverrode: true })).toBe(false);
});
```

- [ ] **Step 2: Run auto-collapse tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts`

Expected: FAIL because the current implementation sums two stored percentages.

- [ ] **Step 3: Implement active-layout navigation calculation**

```ts
export function shouldTemporarilyCollapseNavigation({ layout, minimumWorkspaceWithNavigationPx, userOverrode }: {
  layout: RightPanelLayoutSnapshot | null;
  minimumWorkspaceWithNavigationPx: number;
  userOverrode: boolean;
}): boolean {
  if (!layout?.open || layout.presentation !== "docked" || userOverrode) return false;
  return layout.viewportWidth - layout.widthPx < minimumWorkspaceWithNavigationPx;
}
```

In `AppContent`, store the latest event detail instead of reading two DOM attributes and storage keys. Reset the manual override when the coordinator depth reaches zero. Keep metadata persistence limited to explicit user navigation changes.

- [ ] **Step 4: Replace combined-width CSS with one active lane**

Set one `--right-panel-active-width` variable from the active hook. Gate `#root`, `[data-yields-sidebar]`, toaster, and help-menu offsets with `html[data-right-panel-presentation="docked"]`. Delete selectors that add preview and editor widths. Keep the family-specific width variables only for the panel element itself.

- [ ] **Step 5: Run layout and source tests**

Run: `cd frontend && pnpm exec vitest run src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts src/styles/__tests__/editorSidebarChromeSource.test.ts src/components/layout/AppContent/__tests__/appToastLayout.test.ts`

Expected: PASS and no test expects combined `60% + 30%` compression.

- [ ] **Step 6: Commit app layout changes**

```bash
git add frontend/src/components/layout/AppContent/rightPanelAutoCollapse.ts frontend/src/components/layout/AppContent/index.tsx frontend/src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts frontend/src/styles/base.css frontend/src/styles/__tests__/editorSidebarChromeSource.test.ts
git commit -m "fix(ui): preserve workspace beside right panels"
```

---

### Task 7: Unified, Keyed Automatic-Opening Policy

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/subagentPanelControl.ts:1-38`
- Modify: `frontend/src/components/chat/ChatMessage/SubagentBlock.tsx:104-268`
- Modify: `frontend/src/components/chat/ChatMessage/__tests__/subagentPanelControl.test.ts:1-70`
- Create: `frontend/src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts`
- Modify: `frontend/src/components/layout/AppContent/useRevealPreview.ts:29-300`
- Modify: `frontend/src/components/layout/AppContent/ChatView.tsx:220-235,544-550`
- Modify: `frontend/src/components/chat/ChatMessage/items/RevealPreviewHost.tsx:382-430`
- Modify: `frontend/src/components/documents/useDocumentPreviewState.ts:52-69,500-515`
- Modify: `frontend/src/components/documents/DocumentPreview.tsx:11-48`
- Create: `frontend/src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts`
- Create: `frontend/src/components/chat/ChatMessage/items/__tests__/fileRevealAutoOpen.test.ts`
- Create: `frontend/src/components/chat/ChatMessage/items/__tests__/projectRevealAutoOpen.test.ts`

**Interfaces:**
- Consumes: `hasOpenRightPanel()`, `getRightPanelPresentation()`, and `shouldAllowAutomaticRightPanel()`.
- Produces: `markSubagentPanelAutoOpened(panelKey)`, `hasSubagentPanelAutoOpened(panelKey)`, `dismissSubagentPanelAutoOpen(panelKey)`, `isSubagentPanelAutoOpenDismissed(panelKey)`, `resetSubagentPanelAutoOpenState(panelKey)`, keyed `shouldAutoOpenSubagentPanel` input, and `activePreviewAutomatic` from `useRevealPreview` through `RevealPreviewHost` to `ToolResultPanel`.

- [ ] **Step 1: Replace global subagent state tests with keyed policy tests**

```ts
test("tracks automatic opening and dismissal per subagent panel key", () => {
  resetSubagentPanelAutoOpenState("subagent:a");
  resetSubagentPanelAutoOpenState("subagent:b");
  markSubagentPanelAutoOpened("subagent:a");
  dismissSubagentPanelAutoOpen("subagent:a");
  expect(hasSubagentPanelAutoOpened("subagent:a")).toBe(true);
  expect(isSubagentPanelAutoOpenDismissed("subagent:a")).toBe(true);
  expect(hasSubagentPanelAutoOpened("subagent:b")).toBe(false);
  expect(isSubagentPanelAutoOpenDismissed("subagent:b")).toBe(false);
});

test("allows a running subagent only once while the lane is empty", () => {
  expect(shouldAutoOpenSubagentPanel({ status: "running", laneOccupied: false, alreadyAutoOpened: false, autoOpenDismissed: false })).toBe(true);
  expect(shouldAutoOpenSubagentPanel({ status: "running", laneOccupied: false, alreadyAutoOpened: true, autoOpenDismissed: false })).toBe(false);
  expect(shouldAutoOpenSubagentPanel({ status: "running", laneOccupied: true, alreadyAutoOpened: false, autoOpenDismissed: false })).toBe(false);
});
```

- [ ] **Step 2: Run subagent control tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/ChatMessage/__tests__/subagentPanelControl.test.ts`

Expected: FAIL because the current state is one global boolean and has no once-per-key marker.

- [ ] **Step 3: Implement keyed sets and pure subagent policy**

```ts
const autoOpenedKeys = new Set<string>();
const dismissedKeys = new Set<string>();

export const markSubagentPanelAutoOpened = (key: string) => { autoOpenedKeys.add(key); };
export const hasSubagentPanelAutoOpened = (key: string) => autoOpenedKeys.has(key);
export const dismissSubagentPanelAutoOpen = (key: string) => { dismissedKeys.add(key); };
export const isSubagentPanelAutoOpenDismissed = (key: string) => dismissedKeys.has(key);
export function resetSubagentPanelAutoOpenState(key: string) {
  autoOpenedKeys.delete(key);
  dismissedKeys.delete(key);
}

export function shouldAutoOpenSubagentPanel({ status, laneOccupied, alreadyAutoOpened, autoOpenDismissed }: {
  status: SubagentPanelStatus; laneOccupied: boolean; alreadyAutoOpened: boolean; autoOpenDismissed: boolean;
}) {
  return status === "running" && !laneOccupied && !alreadyAutoOpened && !autoOpenDismissed;
}
```

- [ ] **Step 4: Wire `SubagentBlock` to shared wide-screen occupancy**

Use `panelKey` in every manual reset, dismissal callback, and policy lookup.
Require both the pure subagent policy and
`shouldAllowAutomaticRightPanel({ presentation:
getRightPanelPresentation(window.innerWidth), laneOccupied:
hasOpenRightPanel() })`. Mark the key before `openPersistentToolPanel`. Preserve
`auto: true` as a renderer-level fallback. Manual opening clears only that
panel key's suppression and remains available.

- [ ] **Step 5: Add failing automatic-opening wiring assertions**

In `subagentPanelAutoOpenSource.test.ts`:

```ts
import { readFileSync } from "node:fs";

test("subagent auto-open uses keyed state and the shared empty-lane gate", () => {
  const source = readFileSync(new URL("../SubagentBlock.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/hasOpenRightPanel/);
  expect(source).toMatch(/shouldAllowAutomaticRightPanel/);
  expect(source).toMatch(/hasSubagentPanelAutoOpened\(panelKey\)/);
  expect(source).toMatch(/markSubagentPanelAutoOpened\(panelKey\)[\s\S]*openPersistentToolPanel/);
  expect(source).toMatch(/auto:\s*true/);
});
```

In `revealPreviewAutoOpenSource.test.ts`:

```ts
import { readFileSync } from "node:fs";

test("automatic reveal previews require an empty docked lane", () => {
  const hook = readFileSync(new URL("../useRevealPreview.ts", import.meta.url), "utf8");
  expect(hook).toMatch(/shouldAllowAutomaticRightPanel/);
  expect(hook).toMatch(/hasOpenRightPanel/);
  expect(hook).toMatch(/source === "auto"/);
});

test("automatic reveal intent reaches both file and project panel renderers", () => {
  const chatView = readFileSync(new URL("../ChatView.tsx", import.meta.url), "utf8");
  const host = readFileSync(new URL("../../../chat/ChatMessage/items/RevealPreviewHost.tsx", import.meta.url), "utf8");
  const documentPreview = readFileSync(new URL("../../../documents/DocumentPreview.tsx", import.meta.url), "utf8");
  expect(chatView).toMatch(/automatic=\{activePreviewAutomatic\}/);
  expect(host).toMatch(/automatic=\{automatic\}/g);
  expect(documentPreview).toMatch(/automatic=\{state\.automatic\}/);
});
```

Also lock the existing logical-key once-only guarantees. In
`fileRevealAutoOpen.test.ts`:

```ts
import {
  clearFileRevealAutoOpenState,
  markFileRevealPreviewAutoOpened,
  shouldAutoOpenFileRevealPreview,
} from "../fileRevealAutoOpen";

test("auto-opens each successful file key at most once", () => {
  clearFileRevealAutoOpenState();
  const input = { success: true, filePath: "report.md", isImage: false, showPreview: false, hasClosedPreview: false, isDesktop: true, allowAutoPreview: true, previewKey: "report.md" };
  expect(shouldAutoOpenFileRevealPreview(input)).toBe(true);
  markFileRevealPreviewAutoOpened("report.md");
  expect(shouldAutoOpenFileRevealPreview(input)).toBe(false);
});
```

In `projectRevealAutoOpen.test.ts`:

```ts
import {
  clearProjectRevealAutoOpenState,
  markProjectRevealPreviewAutoOpened,
  shouldAutoOpenProjectRevealPreview,
} from "../projectRevealAutoOpen";

test("auto-opens each successful project key at most once", () => {
  clearProjectRevealAutoOpenState();
  const input = { success: true, showFullPreview: false, hasClosedPreview: false, isDesktop: true, allowAutoPreview: true, previewKey: "project-a" };
  expect(shouldAutoOpenProjectRevealPreview(input)).toBe(true);
  markProjectRevealPreviewAutoOpened("project-a");
  expect(shouldAutoOpenProjectRevealPreview(input)).toBe(false);
});
```

- [ ] **Step 6: Run automatic-opening wiring tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts`

Expected: FAIL because active preview source is not exposed to the renderer and reveal auto-open ignores the shared lane.

- [ ] **Step 7: Route automatic preview intent through the reveal flow**

In `useRevealPreview`, compute:

```ts
const activePreviewAutomatic =
  activePreviewStateRef.current?.source === "auto" &&
  !activePreviewStateRef.current.userInteracted;
```

Before `handleOpenPreview(nextPreview, "auto")`, require the shared
wide-screen/empty-lane helper. Return `activePreviewAutomatic` from the hook.
Pass it from `ChatView` as `automatic` to `RevealPreviewHost`. Add `automatic?:
boolean` to that host, `ProjectRevealPreviewPanel`, and `DocumentPreviewProps`;
pass it to each underlying `ToolResultPanel`. Return `automatic` from
`useDocumentPreviewState` for `DocumentPreview`.

When `handlePreviewInteraction` marks an automatic preview as interacted, the
new `automatic={false}` prop updates the coordinator entry in place to
deliberate state, so a later automatic event cannot replace it.

- [ ] **Step 8: Run all automatic-opening tests**

Run: `cd frontend && pnpm exec vitest run src/hooks/__tests__/rightPanelLayout.test.ts src/components/chat/ChatMessage/__tests__/subagentPanelControl.test.ts src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts src/components/chat/ChatMessage/items/__tests__/fileRevealAutoOpen.test.ts src/components/chat/ChatMessage/items/__tests__/projectRevealAutoOpen.test.ts`

Expected: PASS for subagent, file, and project automatic-opening paths.

- [ ] **Step 9: Commit the unified auto-open policy**

```bash
git add frontend/src/components/chat/ChatMessage/subagentPanelControl.ts frontend/src/components/chat/ChatMessage/SubagentBlock.tsx frontend/src/components/chat/ChatMessage/__tests__/subagentPanelControl.test.ts frontend/src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts frontend/src/components/layout/AppContent/useRevealPreview.ts frontend/src/components/layout/AppContent/ChatView.tsx frontend/src/components/chat/ChatMessage/items/RevealPreviewHost.tsx frontend/src/components/documents/useDocumentPreviewState.ts frontend/src/components/documents/DocumentPreview.tsx frontend/src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts frontend/src/components/chat/ChatMessage/items/__tests__/fileRevealAutoOpen.test.ts frontend/src/components/chat/ChatMessage/items/__tests__/projectRevealAutoOpen.test.ts
git commit -m "fix(ui): unify right panel auto-open policy"
```

---

### Task 8: Shared Chrome, Accessibility, and Reduced Motion

**Files:**
- Modify: `frontend/src/components/common/ui/ToolbarIconButton.tsx:1-43`
- Modify: `frontend/src/styles/components.css:1367-1655,3131-3305,3741-3775`
- Modify: `frontend/src/i18n/locales/en.json:810-825`
- Modify: `frontend/src/i18n/locales/zh.json:810-825`
- Modify: `frontend/src/i18n/locales/ja.json:810-825`
- Modify: `frontend/src/i18n/locales/ko.json:810-825`
- Modify: `frontend/src/i18n/locales/ru.json:810-825`
- Modify: `frontend/src/styles/__tests__/editorSidebarChromeSource.test.ts`
- Modify: `frontend/src/components/common/__tests__/uiPrimitivesSource.test.ts`
- Create: `frontend/src/i18n/__tests__/rightPanelLocaleSource.test.ts`

**Interfaces:**
- Consumes: presentation class/data hooks and separator props from earlier tasks.
- Produces: consistent visual hierarchy, mobile targets, visible focus, reduced motion, and `common.resizePanel` in all locales.

- [ ] **Step 1: Add failing source and locale assertions**

```ts
import { readFileSync } from "node:fs";

const toolbarButtonSource = readFileSync(
  new URL("../ui/ToolbarIconButton.tsx", import.meta.url),
  "utf8",
);
const componentsSource = readFileSync(
  new URL("../../../styles/components.css", import.meta.url),
  "utf8",
);

test("right panel controls are touch-sized and keyboard visible", () => {
  expect(toolbarButtonSource).toMatch(/min-h-\[44px\].*min-w-\[44px\].*sm:size-8/);
  expect(toolbarButtonSource).toMatch(/focus-visible:ring-2/);
});

test("right panel motion respects reduced motion", () => {
  expect(componentsSource).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\.editor-sidebar[\s\S]*animation:\s*none/);
  expect(componentsSource).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\.tool-console-body__content[\s\S]*transition:\s*none/);
});
```

Create the locale test with explicit imports:

```ts
import en from "../locales/en.json";
import ja from "../locales/ja.json";
import ko from "../locales/ko.json";
import ru from "../locales/ru.json";
import zh from "../locales/zh.json";

test.each([en, ja, ko, ru, zh])("defines right panel resize copy", (messages) => {
  expect(messages.common.resizePanel).toBeTruthy();
});
```

- [ ] **Step 2: Run style and locale tests and verify RED**

Run: `cd frontend && pnpm exec vitest run src/styles/__tests__/editorSidebarChromeSource.test.ts src/components/common/__tests__/uiPrimitivesSource.test.ts src/i18n/__tests__/rightPanelLocaleSource.test.ts`

Expected: FAIL for touch sizing, focus-visible styling, reduced motion, and missing locale keys.

- [ ] **Step 3: Implement shared toolbar and presentation chrome**

Factor the shared interaction classes without changing either color variant:

```ts
const shared =
  "flex shrink-0 items-center justify-center min-h-[44px] min-w-[44px] sm:size-8 sm:min-h-0 sm:min-w-0 rounded-xl transition-all duration-200 active:scale-95 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)]/50";

const variants: Record<ToolbarIconButtonVariant, string> = {
  stone: `${shared} text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60`,
  muted: `${shared} text-stone-400 dark:text-stone-500 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60`,
};
```

Use `.right-panel-overlay[data-panel-presentation="docked"] { pointer-events: none; background: transparent; }` and modal backdrops for overlay/full-screen. Make full-screen panels fill the safe-area viewport without rounded bottom-sheet corners or drag handles. Use `gap: 0.5rem` for touch header actions and retain compact desktop spacing. Style `[role="separator"]` hover, focus, active, and reset affordances.

Add the reduced-motion rule:

```css
@media (prefers-reduced-motion: reduce) {
  .editor-sidebar,
  .editor-sidebar-overlay,
  .tool-console-panel,
  .tool-console-body__content,
  [data-yields-sidebar],
  #root {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Add all locale values**

Insert `common.resizePanel` beside the existing `common.close` key in each
locale: English `Resize panel`, Chinese `调整面板宽度`, Japanese `パネル幅を調整`,
Korean `패널 너비 조절`, and Russian `Изменить ширину панели`.

- [ ] **Step 5: Run style, locale, and shell tests**

Run: `cd frontend && pnpm exec vitest run src/styles/__tests__/editorSidebarChromeSource.test.ts src/components/common/__tests__/uiPrimitivesSource.test.ts src/i18n/__tests__/rightPanelLocaleSource.test.ts src/components/common/__tests__/rightPanelShell.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit UX chrome and accessibility**

```bash
git add frontend/src/components/common/ui/ToolbarIconButton.tsx frontend/src/styles/components.css frontend/src/styles/__tests__/editorSidebarChromeSource.test.ts frontend/src/components/common/__tests__/uiPrimitivesSource.test.ts frontend/src/i18n/locales frontend/src/i18n/__tests__/rightPanelLocaleSource.test.ts
git commit -m "feat(ui): polish accessible right panel chrome"
```

---

### Task 9: Coverage Audit and Integrated Verification

**Files:**
- Verify: shared implementation files from Tasks 1-8.
- Test: all focused tests named below.
- Reference: `docs/superpowers/specs/2026-08-09-unified-right-sidebar-ux-design.md`

**Interfaces:**
- Consumes: complete unified panel implementation.
- Produces: verified cross-family behavior and an evidence-backed completion audit.

- [ ] **Step 1: Audit every top-level right-panel consumer**

Run:

```bash
rg -n "<EditorSidebar|<ToolResultPanel|openPersistentToolPanel" frontend/src --glob '!**/__tests__/**'
```

Confirm every `EditorSidebar` and `ToolResultPanel` reaches the coordinator
through its shared renderer. Confirm persistent calls reach it through
`PersistentToolPanelHost`. The expected result is no additional top-level
right-side portal outside these two renderers; a contrary result fails the audit
and reopens the responsible migration task rather than being waived.

- [ ] **Step 2: Run the complete focused regression set**

Run:

```bash
cd frontend && pnpm exec vitest run \
  src/components/common/__tests__/rightPanelCoordinator.test.ts \
  src/hooks/__tests__/rightPanelLayout.test.ts \
  src/components/common/__tests__/rightPanelShell.test.tsx \
  src/components/chat/ChatMessage/items/__tests__/ToolResultPanel.test.ts \
  src/components/chat/ChatMessage/items/__tests__/persistentToolPanelState.test.ts \
  src/components/chat/ChatMessage/__tests__/subagentPanelControl.test.ts \
  src/components/chat/ChatMessage/__tests__/subagentPanelAutoOpenSource.test.ts \
  src/components/layout/AppContent/__tests__/revealPreviewAutoOpenSource.test.ts \
  src/components/chat/ChatMessage/items/__tests__/fileRevealAutoOpen.test.ts \
  src/components/chat/ChatMessage/items/__tests__/projectRevealAutoOpen.test.ts \
  src/components/layout/AppContent/__tests__/rightPanelAutoCollapse.test.ts \
  src/styles/__tests__/editorSidebarChromeSource.test.ts \
  src/__tests__/appSafeAreaSurfaces.test.ts
```

Expected: all focused tests PASS.

- [ ] **Step 3: Run full frontend tests**

Run: `cd frontend && pnpm test`

Expected: all Vitest projects PASS. Investigate any sidebar, portal, safe-area, source-pattern, or timing regression rather than weakening assertions.

- [ ] **Step 4: Run lint and production build**

Run: `cd frontend && pnpm run lint && pnpm run build`

Expected: ESLint exits 0 and Vite production build exits 0.

- [ ] **Step 5: Perform responsive runtime checks**

Start the existing source frontend with `make frontend-dev`. At widths 1440px, 1024px, and 390px, validate one consumer from every group:

- tool result and file preview;
- message outline and subagent;
- model or agent editor;
- skill editor and marketplace preview;
- MCP detail;
- scheduled-task form;
- memory detail;
- persona preview.

For each width, verify single visible lane, Back restoration, Escape affecting only the active entry, correct docked/overlay/full-screen presentation, focus return, usable chat width, safe areas, light/dark theme contrast, and keyboard-only operation. On 390px verify all header controls are comfortably tappable and no bottom-sheet drag handle remains.

- [ ] **Step 6: Run final diff and requirement audit**

Run:

```bash
git diff --check 4e3e7bc7..HEAD
git status --short
```

Compare evidence against every section in the design spec: architecture, responsive policy, width/navigation, opening/navigation, auto-open, header/actions, focus/semantics/motion, failure handling, and representative consumer coverage. Do not claim completion while any section lacks direct test or runtime evidence.

- [ ] **Step 7: Record the final verified commit range**

Run: `git log --oneline 4e3e7bc7..HEAD`

Expected: each implementation task that changed code has a focused commit, and
`git status --short` is empty. Any correction discovered during verification is
made inside the task whose acceptance criteria failed, that task's focused tests
are rerun, and the correction is committed with that task's file scope before
the complete verification sequence is repeated.
