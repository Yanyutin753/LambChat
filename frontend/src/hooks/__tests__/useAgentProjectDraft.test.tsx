/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useAgent } from "../useAgent";
import { sessionApi } from "../../services/api";

vi.mock("../useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => false }),
}));
vi.mock("../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(
    async () => new Response(JSON.stringify({ agents: [] })),
  ),
}));

test("project drafts expose their destination before sending and reset it for a general chat", async () => {
  const submit = vi.spyOn(sessionApi, "submitChat");
  const { result } = renderHook(() => useAgent());
  await waitFor(() => expect(result.current.agentsLoading).toBe(false));
  act(() => result.current.setPendingProjectId("project-1"));
  expect(result.current.currentProjectId).toBe("project-1");
  expect(result.current.sessionId).toBeNull();
  expect(submit).not.toHaveBeenCalled();
  act(() => result.current.setPendingProjectId("project-2"));
  expect(result.current.currentProjectId).toBe("project-2");
  act(() => result.current.clearMessages());
  expect(result.current.currentProjectId).toBeNull();
  expect(result.current.sessionId).toBeNull();
});
