/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const listSessions = vi.fn();

vi.mock("react-intersection-observer", () => ({
  useInView: () => ({ ref: vi.fn(), inView: false }),
}));
vi.mock("../../services/api", () => ({
  sessionApi: {
    list: (...args: unknown[]) => listSessions(...args),
  },
}));

import { useFilteredSessionList } from "../useSession";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  listSessions.mockReset();
});

test("coalesces equivalent reset requests", async () => {
  const pending = deferred<{
    sessions: never[];
    total: number;
    skip: number;
    limit: number;
    has_more: boolean;
  }>();
  listSessions.mockReturnValue(pending.promise);
  const { result } = renderHook(() =>
    useFilteredSessionList({ projectId: "project-1" }),
  );

  await waitFor(() => expect(listSessions).toHaveBeenCalledTimes(1));
  act(() => {
    void result.current.refresh();
    void result.current.refresh();
  });
  expect(listSessions).toHaveBeenCalledTimes(1);

  pending.resolve({
    sessions: [],
    total: 0,
    skip: 0,
    limit: 20,
    has_more: false,
  });
});

test("does not load a disabled session surface until it becomes visible", async () => {
  listSessions.mockResolvedValue({
    sessions: [],
    total: 0,
    skip: 0,
    limit: 20,
    has_more: false,
  });
  const { rerender } = renderHook(
    ({ enabled }) =>
      useFilteredSessionList({ projectId: "project-1" }, undefined, enabled),
    { initialProps: { enabled: false } },
  );

  await act(async () => undefined);
  expect(listSessions).not.toHaveBeenCalled();

  rerender({ enabled: true });
  await waitFor(() => expect(listSessions).toHaveBeenCalledTimes(1));
});
