/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { authenticatedRequest } from "../../../services/api/authenticatedRequest";
import { useAgentList } from "../agentList";

vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(),
}));
const request = vi.mocked(authenticatedRequest);
const noMessages = () => false;
function response(defaultAgent = "fast") {
  return new Response(
    JSON.stringify({
      agents: ["fast", "search"].map((id) => ({
        id,
        name: id,
        description: "",
        options: {},
      })),
      allowed_model_ids: ["model-1"],
      default_agent: defaultAgent,
    }),
  );
}
beforeEach(() => request.mockReset());
afterEach(cleanup);

test("failed agent refresh exposes retry state while retaining the current choice and model access", async () => {
  request.mockResolvedValueOnce(response());
  const { result } = renderHook(() => useAgentList(noMessages));
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  act(() => result.current.setCurrentAgent("search"));
  request.mockResolvedValueOnce(new Response("unavailable", { status: 503 }));
  await act(async () => {
    await result.current.fetchAgents();
  });
  expect(result.current.agentsError).toBe(true);
  expect(result.current.currentAgent).toBe("search");
  expect(result.current.agents.map((agent) => agent.id)).toEqual([
    "fast",
    "search",
  ]);
  expect(result.current.allowedModelIds).toEqual(["model-1"]);
  request.mockResolvedValueOnce(response());
  await act(async () => {
    await result.current.fetchAgents();
  });
  expect(result.current.agentsError).toBe(false);
  expect(result.current.currentAgent).toBe("search");
});

test("a superseded agent response cannot replace the newer catalog or finish its pending feedback", async () => {
  let finishOld!: (value: Response) => void;
  let finishNew!: (value: Response) => void;
  request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishOld = resolve;
      }),
  );
  const { result } = renderHook(() => useAgentList(noMessages));
  request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishNew = resolve;
      }),
  );
  act(() => {
    void result.current.fetchAgents();
  });
  await act(async () => {
    finishOld(response("fast"));
  });
  expect(result.current.agentsLoading).toBe(true);
  expect(result.current.agents).toEqual([]);
  await act(async () => {
    finishNew(response("search"));
  });
  expect(result.current.currentAgent).toBe("search");
  expect(result.current.agentsLoading).toBe(false);
});

test("preference refresh applies a new default only without active messages and rejects an older refresh", async () => {
  let active = false;
  request.mockResolvedValueOnce(response());
  const hasMessages = () => active;
  const { result } = renderHook(() => useAgentList(hasMessages));
  await waitFor(() => expect(result.current.currentAgent).toBe("fast"));
  let finishOld!: (value: Response) => void;
  request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishOld = resolve;
      }),
  );
  act(() => {
    window.dispatchEvent(new Event("agent-preference-updated"));
  });
  request.mockResolvedValueOnce(response("search"));
  await act(async () => {
    window.dispatchEvent(new Event("agent-preference-updated"));
  });
  expect(result.current.currentAgent).toBe("search");
  await act(async () => {
    finishOld(response("fast"));
  });
  expect(result.current.currentAgent).toBe("search");
  active = true;
  request.mockResolvedValueOnce(response("fast"));
  await act(async () => {
    window.dispatchEvent(new Event("agent-preference-updated"));
  });
  expect(result.current.currentAgent).toBe("search");
});
