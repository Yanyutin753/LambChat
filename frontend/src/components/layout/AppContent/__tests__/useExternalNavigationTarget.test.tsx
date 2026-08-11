/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { sessionApi } from "../../../../services/api";
import type { ExternalNavigationState } from "../externalNavigationState";
import { useExternalNavigationTarget } from "../useExternalNavigationTarget";

vi.mock("../../../../services/api", () => ({
  sessionApi: {
    getRuns: vi.fn(),
  },
}));

const getRuns = vi.mocked(sessionApi.getRuns);

function navigationState(traceId?: string): ExternalNavigationState {
  return {
    externalNavigate: true,
    scrollToBottom: true,
    targetFile: {
      fileId: "file-1",
      fileName: "notes.txt",
      traceId,
    },
    targetPreview: {
      kind: "file",
      previewKey: "external-file:file-1",
      filePath: "/tmp/notes.txt",
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

beforeEach(() => {
  getRuns.mockReset();
});

test.each([
  {
    name: "missing session",
    sessionId: null,
    locationState: navigationState("trace-1"),
  },
  {
    name: "missing trace",
    sessionId: "session-1",
    locationState: navigationState(),
  },
])("avoids a run request for $name", ({ sessionId, locationState }) => {
  const { result } = renderHook(() =>
    useExternalNavigationTarget({
      sessionId,
      locationState,
      locationKey: "location-1",
      routeRunId: null,
    }),
  );

  expect(getRuns).not.toHaveBeenCalled();
  expect(result.current.externalNavigationTargetRunId).toBe(null);
  expect(result.current.externalNavigationTargetRunPending).toBe(false);
});

test("resolves a matching trace to its run", async () => {
  getRuns.mockResolvedValue({
    session_id: "session-1",
    count: 1,
    runs: [
      {
        run_id: "run-1",
        trace_id: "trace-1",
        agent_id: "default",
        started_at: "2026-08-11T08:00:00Z",
        completed_at: "2026-08-11T08:00:01Z",
        status: "completed",
        event_count: 3,
        user_message: "show notes",
      },
    ],
  });

  const { result } = renderHook(() =>
    useExternalNavigationTarget({
      sessionId: "session-1",
      locationState: navigationState("trace-1"),
      locationKey: "location-1",
      routeRunId: null,
    }),
  );

  expect(result.current.externalNavigationTargetRunPending).toBe(true);
  await waitFor(() =>
    expect(result.current.externalNavigationTargetRunId).toBe("run-1"),
  );
  expect(result.current.externalNavigationTargetRunPending).toBe(false);
  expect(getRuns).toHaveBeenCalledWith("session-1", {
    trace_id: "trace-1",
  });
});

test("clears pending state when no run matches the trace", async () => {
  getRuns.mockResolvedValue({
    session_id: "session-1",
    count: 1,
    runs: [
      {
        run_id: "run-other",
        trace_id: "trace-other",
        started_at: "2026-08-11T08:00:00Z",
        status: "running",
        event_count: 1,
      },
    ],
  });

  const { result } = renderHook(() =>
    useExternalNavigationTarget({
      sessionId: "session-1",
      locationState: navigationState("trace-1"),
      locationKey: "location-1",
      routeRunId: null,
    }),
  );

  await waitFor(() =>
    expect(result.current.externalNavigationTargetRunPending).toBe(false),
  );
  expect(result.current.externalNavigationTargetRunId).toBe(null);
});

test("clears pending state when run resolution fails", async () => {
  const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  getRuns.mockRejectedValue(new Error("network unavailable"));

  const { result } = renderHook(() =>
    useExternalNavigationTarget({
      sessionId: "session-1",
      locationState: navigationState("trace-1"),
      locationKey: "location-1",
      routeRunId: null,
    }),
  );

  await waitFor(() =>
    expect(result.current.externalNavigationTargetRunPending).toBe(false),
  );
  expect(result.current.externalNavigationTargetRunId).toBe(null);
  expect(warning).toHaveBeenCalledOnce();
  warning.mockRestore();
});

test("ignores a stale trace response after navigation changes", async () => {
  const firstRequest = deferred<Awaited<ReturnType<typeof sessionApi.getRuns>>>();
  const secondRequest = deferred<
    Awaited<ReturnType<typeof sessionApi.getRuns>>
  >();
  getRuns
    .mockReturnValueOnce(firstRequest.promise)
    .mockReturnValueOnce(secondRequest.promise);

  const { result, rerender } = renderHook(
    ({ traceId }) =>
      useExternalNavigationTarget({
        sessionId: "session-1",
        locationState: navigationState(traceId),
        locationKey: traceId,
        routeRunId: null,
      }),
    { initialProps: { traceId: "trace-old" } },
  );

  await waitFor(() => expect(getRuns).toHaveBeenCalledTimes(1));
  rerender({ traceId: "trace-new" });
  await waitFor(() => expect(getRuns).toHaveBeenCalledTimes(2));
  await act(async () => {
    secondRequest.resolve({
      session_id: "session-1",
      count: 1,
      runs: [
        {
          run_id: "run-new",
          trace_id: "trace-new",
          started_at: "2026-08-11T08:01:00Z",
          status: "running",
          event_count: 1,
        },
      ],
    });
    await secondRequest.promise;
  });
  expect(result.current.externalNavigationTargetRunId).toBe("run-new");

  await act(async () => {
    firstRequest.resolve({
      session_id: "session-1",
      count: 1,
      runs: [
        {
          run_id: "run-old",
          trace_id: "trace-old",
          started_at: "2026-08-11T08:00:00Z",
          status: "completed",
          event_count: 2,
        },
      ],
    });
    await firstRequest.promise;
  });
  expect(result.current.externalNavigationTargetRunId).toBe("run-new");
});

test("cleanup prevents a removed target from being restored by its response", async () => {
  const request = deferred<Awaited<ReturnType<typeof sessionApi.getRuns>>>();
  getRuns.mockReturnValue(request.promise);

  const { result, rerender } = renderHook(
    ({ locationState }) =>
      useExternalNavigationTarget({
        sessionId: "session-1",
        locationState,
        locationKey: "location-1",
        routeRunId: null,
      }),
    {
      initialProps: {
        locationState: navigationState("trace-1") as
          | ExternalNavigationState
          | null,
      },
    },
  );

  await waitFor(() => expect(getRuns).toHaveBeenCalledOnce());
  rerender({ locationState: null });
  expect(result.current.externalNavigationTargetRunPending).toBe(false);

  await act(async () => {
    request.resolve({
      session_id: "session-1",
      count: 1,
      runs: [
        {
          run_id: "run-stale",
          trace_id: "trace-1",
          started_at: "2026-08-11T08:00:00Z",
          status: "completed",
          event_count: 2,
        },
      ],
    });
    await request.promise;
  });

  expect(result.current.externalNavigationTargetRunId).toBe(null);
  expect(result.current.externalNavigationTargetRunPending).toBe(false);
});

test("keeps the trimmed route run id as the trace-resolution fallback", async () => {
  const request = deferred<Awaited<ReturnType<typeof sessionApi.getRuns>>>();
  getRuns.mockReturnValue(request.promise);

  const { result } = renderHook(() =>
    useExternalNavigationTarget({
      sessionId: "session-1",
      locationState: navigationState("trace-1"),
      locationKey: "location-1",
      routeRunId: "  run-route  ",
    }),
  );

  expect(result.current.externalNavigationTargetRunPending).toBe(true);
  expect(result.current.externalNavigationTargetRunId).toBe("run-route");

  await act(async () => {
    request.resolve({ session_id: "session-1", count: 0, runs: [] });
    await request.promise;
  });

  expect(result.current.externalNavigationTargetRunPending).toBe(false);
  expect(result.current.externalNavigationTargetRunId).toBe("run-route");
});
