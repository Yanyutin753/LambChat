/** @vitest-environment jsdom */
import { act, renderHook, cleanup } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useTouchDrag } from "../useTouchDrag";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

function moveTo(element: Element | null) {
  Object.defineProperty(document, "elementFromPoint", {
    configurable: true,
    value: () => element,
  });
  const event = new Event("touchmove", { cancelable: true });
  Object.defineProperty(event, "touches", {
    value: [{ clientX: 20, clientY: 20 }],
  });
  act(() => {
    document.dispatchEvent(event);
  });
}

test("touch release pins the dragged session", () => {
  const drops: string[][] = [];
  const { result } = renderHook(() =>
    useTouchDrag([], (id, target) => drops.push([id, target])),
  );
  const target = document.createElement("div");
  target.setAttribute("data-pinned-drop", "");
  document.body.append(target);
  act(() => {
    result.current.handleDragStartTouch("chat-1", 0, 0);
  });
  moveTo(target);
  expect(result.current.touchDropTarget).toBe("pinned");
  act(() => {
    document.dispatchEvent(new Event("touchend"));
  });
  expect(drops).toEqual([["chat-1", "pinned"]]);
  expect(result.current.draggingSessionId).toBeNull();
});

test("leaving the project clears the drop target", () => {
  const drops: string[][] = [];
  const { result } = renderHook(() =>
    useTouchDrag([], (id, target) => drops.push([id, target])),
  );
  const target = document.createElement("div");
  target.setAttribute("data-project-drop", "");
  target.setAttribute("data-project-id", "project-1");
  document.body.append(target);
  act(() => {
    result.current.handleDragStartTouch("chat-1", 0, 0);
  });
  moveTo(target);
  expect(result.current.touchDropTarget).toBe("project-1");
  moveTo(null);
  expect(result.current.touchDropTarget).toBeNull();
  act(() => {
    document.dispatchEvent(new Event("touchend"));
  });
  expect(drops).toEqual([]);
});

test("cancelling touch drag does not pin", () => {
  const drops: string[][] = [];
  const { result } = renderHook(() =>
    useTouchDrag([], (id, target) => drops.push([id, target])),
  );
  const target = document.createElement("div");
  target.setAttribute("data-pinned-drop", "");
  document.body.append(target);
  act(() => {
    result.current.handleDragStartTouch("chat-1", 0, 0);
  });
  moveTo(target);
  act(() => {
    document.dispatchEvent(new Event("touchcancel"));
  });
  expect(drops).toEqual([]);
  expect(result.current.draggingSessionId).toBeNull();
});
