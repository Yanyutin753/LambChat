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

import { useFilteredSessionList, useProjectSessionList } from "../useSession";

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

test("recent chats exclude companion sessions on fetch, refresh and live insertion", async () => {
  listSessions.mockResolvedValue({
    sessions: [],
    total: 0,
    skip: 0,
    limit: 20,
    has_more: false,
  });
  const { result } = renderHook(() => useProjectSessionList("none"));
  await waitFor(() => expect(listSessions).toHaveBeenCalledTimes(1));
  expect(listSessions.mock.calls[0][0]).toMatchObject({
    exclude_assistants: true,
  });
  const base = {
    agent_id: "search",
    created_at: "",
    updated_at: "",
    is_active: true,
  };
  act(() => {
    result.current.prependSession({ ...base, id: "normal", metadata: {} });
    result.current.prependSession({
      ...base,
      id: "chief",
      metadata: { assistant_id: "chief" },
    });
    result.current.prependSession({
      ...base,
      id: "discussion",
      metadata: { assistant_discussion_id: "group" },
    });
  });
  expect(result.current.sessions.map((item) => item.id)).toEqual(["normal"]);
  act(() =>
    result.current.updateSession({
      ...base,
      id: "normal",
      metadata: { assistant_id: "converted" },
    }),
  );
  expect(result.current.sessions).toEqual([]);
  await act(() => result.current.softRefresh());
  expect(listSessions.mock.lastCall?.[0]).toMatchObject({
    exclude_assistants: true,
  });
});
