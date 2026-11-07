/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Assistant } from "../../../types/assistant";
import { useAssistantContext } from "../useAssistantContext";

const navigation = vi.hoisted(() => ({
  navigate: vi.fn(),
  pathname: "/chat/one",
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigation.navigate,
  useLocation: () => ({
    pathname: navigation.pathname,
    search: "?run=latest",
    hash: "",
  }),
}));
beforeEach(() => {
  navigation.navigate.mockClear();
  navigation.pathname = "/chat/one";
});
afterEach(cleanup);

test.each([null, undefined])(
  "a new chat has no assistant context (%s)",
  (sessionId) => {
    const { result } = renderHook(() => useAssistantContext(sessionId));
    expect(result.current.assistant).toBeNull();
  },
);

test("a previous conversation cannot lock a newly selected conversation", () => {
  const assistant = { id: "assistant-one" } as Assistant;
  const { result, rerender } = renderHook(
    ({ sessionId }) => useAssistantContext(sessionId),
    {
      initialProps: { sessionId: "one" },
    },
  );
  const resolve = result.current.onAssistantResolved;
  act(() => resolve("one", assistant));
  expect(result.current.assistant).toBe(assistant);
  rerender({ sessionId: "two" });
  expect(result.current.assistant).toBeNull();
  act(() => resolve("one", assistant));
  expect(result.current.assistant).toBeNull();
  expect(result.current.onAssistantResolved).toBe(resolve);
  act(() => resolve("two", assistant));
  expect(result.current.assistant).toBe(assistant);
  act(() => resolve("two", null));
  expect(result.current.assistant).toBeNull();
});

test("a companion opened through ordinary chat returns to its own workspace", () => {
  const { result } = renderHook(() => useAssistantContext("one"));
  act(() =>
    result.current.onAssistantResolved("one", {
      id: "partner",
      session_id: "one",
    } as Assistant),
  );
  expect(navigation.navigate).toHaveBeenCalledWith(
    "/assistants/partner/chat/one?run=latest",
    { replace: true },
  );
});
test("late resolution cannot redirect a different selected conversation", () => {
  navigation.pathname = "/chat/two";
  const { result } = renderHook(() => useAssistantContext("two"));
  act(() =>
    result.current.onAssistantResolved("one", { id: "partner" } as Assistant),
  );
  expect(navigation.navigate).not.toHaveBeenCalled();
});
test("an existing companion workspace does not redirect again", () => {
  navigation.pathname = "/assistants/partner/chat/one";
  const { result } = renderHook(() => useAssistantContext("one"));
  act(() =>
    result.current.onAssistantResolved("one", { id: "partner" } as Assistant),
  );
  expect(navigation.navigate).not.toHaveBeenCalled();
});
