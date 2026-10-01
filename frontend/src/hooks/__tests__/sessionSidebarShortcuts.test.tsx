/** @vitest-environment jsdom */
import { cleanup, fireEvent, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useSessionSidebarEffects } from "../useSessionSidebarEffects";
import { ModalSurface } from "../../components/common/ModalSurface";
import { render } from "@testing-library/react";

afterEach(cleanup);

function setup() {
  window.matchMedia = vi
    .fn()
    .mockReturnValue({
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
  const onNewSession = vi.fn();
  const setIsSearchOpen = vi.fn();
  renderHook(() =>
    useSessionSidebarEffects({
      currentSessionId: null,
      onNewSession,
      setIsSearchOpen,
      setIsProjectsCollapsed: vi.fn(),
      setIsMobile: vi.fn(),
      loadProjects: async () => {},
      uncategorizedList: {
        sessions: [],
        softRefresh: vi.fn(),
        prependSession: vi.fn(),
        updateSession: vi.fn(),
      },
      projectRefs: { current: new Map() },
      scheduledTaskRefs: { current: new Map() },
      getProjectRef: () => null,
      projects: [],
    }),
  );
  return { onNewSession, setIsSearchOpen };
}

test("new chat and search shortcuts yield to an open modal", () => {
  const actions = setup();
  render(
    <ModalSurface open label="Draft" onClose={() => {}}>
      <button>Save draft</button>
    </ModalSurface>,
  );
  for (const key of ["n", "k", "O"]) {
    fireEvent.keyDown(document, {
      key,
      ctrlKey: true,
      metaKey: true,
      shiftKey: key === "O",
    });
  }
  expect(actions.onNewSession).not.toHaveBeenCalled();
  expect(actions.setIsSearchOpen).not.toHaveBeenCalled();
});

test("new chat shortcuts ignore consumed, composing and unrelated modifiers", () => {
  const actions = setup();
  for (const init of [
    { isComposing: true },
    { altKey: true },
    { shiftKey: true },
  ]) {
    fireEvent.keyDown(document, {
      key: "n",
      ctrlKey: true,
      metaKey: true,
      ...init,
    });
  }
  const event = new KeyboardEvent("keydown", {
    key: "n",
    ctrlKey: true,
    metaKey: true,
    cancelable: true,
  });
  event.preventDefault();
  document.dispatchEvent(event);
  expect(actions.onNewSession).not.toHaveBeenCalled();
  fireEvent.keyDown(document, {
    key: "O",
    ctrlKey: true,
    metaKey: true,
    shiftKey: true,
  });
  expect(actions.onNewSession).toHaveBeenCalledOnce();
});
