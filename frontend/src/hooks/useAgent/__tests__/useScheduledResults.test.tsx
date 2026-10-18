/** @vitest-environment jsdom */
import { useState } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useScheduledResults } from "../useScheduledResults";
import {
  mergeScheduledProgress,
  mergeScheduledResult,
  SCHEDULED_PROGRESS_EVENT,
  SCHEDULED_RESULT_EVENT,
} from "../scheduledResults";
import { sessionApi } from "../../../services/api/session";
import type { Message } from "../../../types";

vi.mock("../../../services/api/session", () => ({
  sessionApi: {
    getEvents: vi.fn(),
    getScheduledProgress: vi.fn().mockResolvedValue({ progress: [] }),
  },
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const data = {
  session_id: "parent",
  run_id: "scheduled-1",
  message_id: "scheduled-result:scheduled-1",
  task_id: "task",
  task_name: "Numbers",
  content: "692",
  timestamp: "2026-10-17T19:33:41Z",
};

function useMessages(
  initial: Message[],
  callbacks?: Parameters<typeof useScheduledResults>[5],
) {
  const [messages, setMessages] = useState(initial);
  useScheduledResults(
    "parent",
    "owner",
    setMessages,
    messages,
    undefined,
    callbacks,
  );
  return messages;
}

test("restores completed scheduled execution details from its own run", async () => {
  vi.mocked(sessionApi.getEvents).mockResolvedValue({
    events: [
      {
        id: "instruction",
        event_type: "scheduled:instruction",
        data: { content: "INTERNAL" },
        timestamp: data.timestamp,
      },
      {
        id: "start",
        event_type: "tool:start",
        data: { tool: "execute", tool_call_id: "exec", args: {} },
        timestamp: data.timestamp,
      },
      {
        id: "result",
        event_type: "tool:result",
        data: {
          tool: "execute",
          tool_call_id: "exec",
          result: "692",
          success: true,
        },
        timestamp: data.timestamp,
      },
    ],
  } as Awaited<ReturnType<typeof sessionApi.getEvents>>);
  const { result } = renderHook(() =>
    useMessages(mergeScheduledResult([], data)),
  );
  await waitFor(() =>
    expect(result.current[0].metadata?.scheduledEventsLoaded).toBe(true),
  );
  expect(sessionApi.getEvents).toHaveBeenCalledWith(
    "sch_conversation_task",
    expect.objectContaining({ run_id: "scheduled-1" }),
  );
  expect(result.current[0].parts).toEqual([
    expect.objectContaining({
      type: "tool",
      name: "execute",
      isPending: false,
    }),
    { type: "text", content: "692" },
  ]);
  expect(JSON.stringify(result.current)).not.toContain("INTERNAL");
});

test("live scheduled events update tools without touching a foreground run", () => {
  const foreground: Message = {
    id: "human",
    role: "assistant",
    runId: "human",
    content: "answering",
    timestamp: new Date(),
    isStreaming: true,
  };
  const { result } = renderHook(() => useMessages([foreground]));
  act(() =>
    window.dispatchEvent(
      new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
        detail: {
          ...data,
          content: "",
          status: "running",
          updated_at: data.timestamp,
          events: [
            {
              event_type: "tool:start",
              data: { tool: "execute", tool_call_id: "exec", args: {} },
            },
          ],
        },
      }),
    ),
  );
  expect(result.current.find((message) => message.id === "human")).toBe(
    foreground,
  );
  expect(
    result.current.find((message) => message.id === data.message_id)?.parts,
  ).toEqual([
    expect.objectContaining({ type: "tool", name: "execute", isPending: true }),
  ]);
});

test("scheduled waiting-human progress exposes an actionable approval in the parent", () => {
  const onApprovalRequired = vi.fn();
  const { result } = renderHook(() => useMessages([], { onApprovalRequired }));
  const approval = {
    id: "confirm",
    session_id: "sch_conversation_task",
    type: "form" as const,
    fields: [],
    status: "pending" as const,
    message: "确认执行测试命令",
    metadata: {
      mode: "interrupt",
      scheduled_target_session_id: "parent",
      run_id: "scheduled-1",
    },
  };
  act(() =>
    window.dispatchEvent(
      new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
        detail: {
          ...data,
          content: "",
          status: "waiting_human",
          updated_at: data.timestamp,
          approvals: [approval],
          events: [
            {
              event_type: "tool:start",
              data: { tool: "execute", tool_call_id: "exec", args: {} },
            },
            { event_type: "hitl:suspended", data: {} },
          ],
        },
      }),
    ),
  );
  expect(onApprovalRequired).toHaveBeenCalledWith(approval);
  expect(result.current[0].isStreaming).toBe(false);
  expect(result.current[0].metadata?.scheduledProgressStatus).toBe(
    "waiting_human",
  );
  expect(result.current[0].parts?.[0]).toMatchObject({
    type: "tool",
    isPending: true,
    awaitingConfirmation: true,
  });
});

test("opening the parent restores a task already waiting before the page was mounted", async () => {
  vi.mocked(sessionApi.getEvents).mockResolvedValue({
    events: [],
  } as unknown as Awaited<ReturnType<typeof sessionApi.getEvents>>);
  vi.mocked(sessionApi.getScheduledProgress).mockResolvedValueOnce({
    progress: [
      {
        ...data,
        content: "",
        status: "waiting_human",
        updated_at: data.timestamp,
        events: [
          {
            event_type: "tool:start",
            data: { tool: "execute", tool_call_id: "exec", args: {} },
          },
          { event_type: "hitl:suspended", data: {} },
        ],
      },
    ],
  });
  const { result } = renderHook(() => useMessages([]));
  await waitFor(() =>
    expect(result.current[0]?.metadata?.scheduledProgressStatus).toBe(
      "waiting_human",
    ),
  );
  expect(result.current[0].parts?.[0]).toMatchObject({
    type: "tool",
    name: "execute",
    awaitingConfirmation: true,
  });
});

test("omitted live events catch up from the exact execution run without losing visible details", async () => {
  let resolveCatchup!: (
    value: Awaited<ReturnType<typeof sessionApi.getEvents>>,
  ) => void;
  vi.mocked(sessionApi.getEvents).mockImplementation((source) =>
    source === "execution"
      ? new Promise((resolve) => {
          resolveCatchup = resolve;
        })
      : Promise.resolve({ events: [] } as unknown as Awaited<
          ReturnType<typeof sessionApi.getEvents>
        >),
  );
  const progress = {
    ...data,
    content: "",
    status: "running" as const,
    execution_session_id: "execution",
    updated_at: data.timestamp,
    events: [
      {
        event_type: "tool:start",
        data: { tool: "execute", tool_call_id: "exec", args: {} },
      },
    ],
  };
  const { result } = renderHook(() =>
    useMessages(mergeScheduledProgress([], progress)),
  );
  act(() =>
    window.dispatchEvent(
      new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
        detail: {
          ...progress,
          updated_at: "2026-10-17T19:33:42Z",
          events: undefined,
          events_omitted: true,
        },
      }),
    ),
  );
  expect(result.current[0].parts?.[0]).toMatchObject({
    type: "tool",
    isPending: true,
  });
  expect(sessionApi.getEvents).toHaveBeenCalledWith(
    "execution",
    expect.objectContaining({
      run_id: data.run_id,
      include_active_events: true,
    }),
  );
  await act(async () =>
    resolveCatchup({
      events: [
        ...progress.events,
        {
          event_type: "tool:result",
          data: {
            tool: "execute",
            tool_call_id: "exec",
            result: "692",
            success: true,
          },
        },
      ],
    } as Awaited<ReturnType<typeof sessionApi.getEvents>>),
  );
  expect(result.current[0].parts?.[0]).toMatchObject({
    type: "tool",
    isPending: false,
  });
});

test.each(["newer progress", "final result"])(
  "a delayed catch-up cannot overwrite %s",
  async (settled) => {
    let resolveCatchup!: (
      value: Awaited<ReturnType<typeof sessionApi.getEvents>>,
    ) => void;
    vi.mocked(sessionApi.getEvents).mockImplementation((source) =>
      source === "execution"
        ? new Promise((resolve) => {
            resolveCatchup = resolve;
          })
        : Promise.resolve({ events: [] } as unknown as Awaited<
            ReturnType<typeof sessionApi.getEvents>
          >),
    );
    const { result } = renderHook(() => useMessages([]));
    const progress = {
      ...data,
      content: "",
      status: "running",
      execution_session_id: "execution",
      updated_at: data.timestamp,
      events_omitted: true,
    };
    act(() =>
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_PROGRESS_EVENT, { detail: progress }),
      ),
    );
    act(() =>
      window.dispatchEvent(
        new CustomEvent(
          settled === "final result"
            ? SCHEDULED_RESULT_EVENT
            : SCHEDULED_PROGRESS_EVENT,
          {
            detail:
              settled === "final result"
                ? { ...data, events: [] }
                : {
                    ...progress,
                    content: "Newer",
                    updated_at: "2026-10-17T19:33:43Z",
                    events_omitted: false,
                    events: [
                      { event_type: "thinking", data: { content: "Newer" } },
                    ],
                  },
          },
        ),
      ),
    );
    const before = result.current;
    await act(async () =>
      resolveCatchup({
        events: [{ event_type: "thinking", data: { content: "Old snapshot" } }],
      } as Awaited<ReturnType<typeof sessionApi.getEvents>>),
    );
    expect(result.current).toBe(before);
  },
);

// The progress endpoint only returns finished runs when the caller names its visible runs.
test.each(["visibility", "timer"])(
  "%s catch-up removes a quiet run after its terminal websocket event was missed",
  async (trigger) => {
    vi.useFakeTimers();
    vi.mocked(sessionApi.getEvents).mockResolvedValue({
      events: [],
    } as unknown as Awaited<ReturnType<typeof sessionApi.getEvents>>);
    vi.mocked(sessionApi.getScheduledProgress).mockImplementation(
      async (_session, _signal, runIds) => ({
        progress: runIds?.includes(data.run_id)
          ? [
              {
                ...data,
                content: "",
                status: "quiet",
                updated_at: "2026-10-17T19:33:43Z",
              },
            ]
          : [],
      }),
    );
    try {
      const { result } = renderHook(() => useMessages([]));
      await act(async () => {});
      act(() =>
        window.dispatchEvent(
          new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
            detail: {
              ...data,
              content: "checking",
              status: "running",
              updated_at: data.timestamp,
            },
          }),
        ),
      );
      expect(result.current[0].isStreaming).toBe(true);
      await act(async () => {
        if (trigger === "visibility")
          document.dispatchEvent(new Event("visibilitychange"));
        else await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(result.current).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  },
);

test("visibility catch-up settles an empty failed run without removing another active run", async () => {
  vi.mocked(sessionApi.getEvents).mockResolvedValue({
    events: [],
  } as unknown as Awaited<ReturnType<typeof sessionApi.getEvents>>);
  vi.mocked(sessionApi.getScheduledProgress).mockImplementation(
    async (_session, _signal, runIds) => ({
      progress: runIds?.includes(data.run_id)
        ? [
            {
              ...data,
              content: "",
              status: "failed",
              updated_at: "2026-10-17T19:33:43Z",
              events: [],
            },
          ]
        : [],
    }),
  );
  const { result } = renderHook(() => useMessages([]));
  await act(async () => {});
  act(() => {
    for (const [runId, messageId] of [
      [data.run_id, data.message_id],
      ["scheduled-2", "scheduled-result:scheduled-2"],
    ]) {
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
          detail: {
            ...data,
            run_id: runId,
            message_id: messageId,
            content: "",
            status: "running",
            updated_at: data.timestamp,
            events: [
              {
                event_type: "tool:start",
                data: { tool: "execute", tool_call_id: runId, args: {} },
              },
            ],
          },
        }),
      );
    }
  });
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  const failed = result.current.find(
    (message) => message.id === data.message_id,
  );
  expect(failed?.isStreaming).toBe(false);
  expect(failed?.metadata?.scheduledProgressStatus).toBe("failed");
  expect(failed?.parts?.[0]).toMatchObject({ type: "tool", isPending: false });
  expect(
    result.current.find((message) => message.runId === "scheduled-2")
      ?.isStreaming,
  ).toBe(true);
});

test("catch-up batches more than one hundred known runs without discarding absent rows", async () => {
  vi.mocked(sessionApi.getEvents).mockResolvedValue({
    events: [],
  } as unknown as Awaited<ReturnType<typeof sessionApi.getEvents>>);
  vi.mocked(sessionApi.getScheduledProgress).mockResolvedValue({
    progress: [],
  });
  const initial = Array.from(
    { length: 101 },
    (_, index) =>
      mergeScheduledProgress([], {
        ...data,
        run_id: `scheduled-${index}`,
        message_id: `scheduled-result:scheduled-${index}`,
        content: "",
        status: "running",
        updated_at: data.timestamp,
      })[0],
  );
  const { result } = renderHook(() => useMessages(initial));
  await act(async () => {});
  expect(
    vi
      .mocked(sessionApi.getScheduledProgress)
      .mock.calls.map((call) => call[2]?.length),
  ).toEqual([100, 1]);
  expect(result.current).toHaveLength(101);
  expect(result.current.every((message) => message.isStreaming)).toBe(true);
});
