/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useApprovals } from "../useApprovals";
import { authFetch } from "../../services/api/fetch";

vi.mock("../../services/api/fetch", () => ({ authFetch: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test("approval response reports the execution session so parent chat cannot reconnect to its run", async () => {
  vi.mocked(authFetch).mockResolvedValueOnce({
    approvals: [
      {
        id: "confirm",
        message: "Test command",
        session_id: "sch_conversation_task",
        type: "form",
        fields: [],
        status: "pending",
        metadata: { scheduled_target_session_id: "parent" },
      },
    ],
  });
  const onInterruptResume = vi.fn();
  const { result } = renderHook(() =>
    useApprovals({ sessionId: "parent", onInterruptResume }),
  );
  await waitFor(() => expect(result.current.approvals).toHaveLength(1));
  vi.mocked(authFetch).mockResolvedValueOnce({
    status: "success",
    hitl_resume: { submitted: true, run_id: "scheduled-1" },
  });
  await act(async () => {
    expect(await result.current.respondToApproval("confirm", {}, true)).toBe(
      true,
    );
  });
  expect(onInterruptResume).toHaveBeenCalledWith(
    "scheduled-1",
    "sch_conversation_task",
  );
  expect(result.current.approvals).toEqual([]);
});
