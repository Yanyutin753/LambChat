/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import type { Assistant } from "../../../types/assistant";
import { useAssistantContext } from "../useAssistantContext";

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
