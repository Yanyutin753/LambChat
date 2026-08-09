import { beforeEach, expect, test, vi } from "vitest";

import {
  closeActiveRightPanel,
  getRightPanelSnapshot,
  hasDeliberateRightPanel,
  hasOpenRightPanel,
  registerRightPanel,
  resetRightPanelCoordinator,
  unregisterRightPanel,
} from "../rightPanelCoordinator";

beforeEach(resetRightPanelCoordinator);

test("keeps one active entry and reveals the previous entry after unmount", () => {
  const editor = {
    id: Symbol("editor"),
    kind: "editor" as const,
    automatic: false,
    close: vi.fn(),
    opener: null,
  };
  const content = {
    id: Symbol("content"),
    kind: "content" as const,
    automatic: false,
    close: vi.fn(),
    opener: null,
  };

  expect(registerRightPanel(editor)).toBe(true);
  expect(registerRightPanel(content)).toBe(true);
  expect(getRightPanelSnapshot()).toMatchObject({
    activeId: content.id,
    depth: 2,
  });

  unregisterRightPanel(content.id);
  expect(getRightPanelSnapshot()).toMatchObject({
    activeId: editor.id,
    depth: 1,
  });
});

test("updates duplicate owners without duplicating stack history", () => {
  const id = Symbol("editor");
  registerRightPanel({
    id,
    kind: "editor",
    automatic: false,
    close: vi.fn(),
    opener: null,
  });
  registerRightPanel({
    id,
    kind: "editor",
    automatic: false,
    close: vi.fn(),
    opener: null,
  });

  expect(getRightPanelSnapshot().depth).toBe(1);
});

test("rejects automatic entries whenever the lane is occupied", () => {
  registerRightPanel({
    id: Symbol("existing"),
    kind: "content",
    automatic: true,
    close: vi.fn(),
    opener: null,
  });

  expect(
    registerRightPanel({
      id: Symbol("auto"),
      kind: "content",
      automatic: true,
      close: vi.fn(),
      opener: null,
    }),
  ).toBe(false);
  expect(hasOpenRightPanel()).toBe(true);
  expect(hasDeliberateRightPanel()).toBe(false);
});

test("removes an automatic entry when deliberate work opens", () => {
  const closeAuto = vi.fn();
  registerRightPanel({
    id: Symbol("auto"),
    kind: "content",
    automatic: true,
    close: closeAuto,
    opener: null,
  });
  const editorId = Symbol("editor");
  registerRightPanel({
    id: editorId,
    kind: "editor",
    automatic: false,
    close: vi.fn(),
    opener: null,
  });

  expect(closeAuto).toHaveBeenCalledTimes(1);
  expect(getRightPanelSnapshot()).toMatchObject({
    activeId: editorId,
    depth: 1,
  });
});

test("asks the active owner to close once and waits for unregister", () => {
  const close = vi.fn();
  const id = Symbol("content");
  registerRightPanel({
    id,
    kind: "content",
    automatic: false,
    close,
    opener: null,
  });

  closeActiveRightPanel();
  closeActiveRightPanel();

  expect(close).toHaveBeenCalledTimes(1);
  expect(getRightPanelSnapshot().activeId).toBe(id);
});
