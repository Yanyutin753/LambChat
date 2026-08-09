/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { useSessionSync } from "../useSessionSync";

function SessionSyncHarness({
  loadHistory,
}: {
  loadHistory: (sessionId: string) => Promise<void>;
}) {
  const [sessionId, setSessionId] = useState<string | null>("session-a");
  const { handleSelectSession } = useSessionSync({
    activeTab: "chat",
    sessionId,
    loadHistory: async (targetSessionId) => {
      await loadHistory(targetSessionId);
      setSessionId(targetSessionId);
      return null;
    },
    clearMessages: () => undefined,
  });

  return (
    <button type="button" onClick={() => void handleSelectSession("session-b")}>
      Open session B
    </button>
  );
}

test("keeps the selected session route while its history is still loading", async () => {
  window.history.replaceState(null, "", "/chat/session-a");

  let resolveSessionB: (() => void) | undefined;
  const sessionBHistory = new Promise<void>((resolve) => {
    resolveSessionB = resolve;
  });
  const loadHistory = vi.fn(async (sessionId: string) => {
    if (sessionId === "session-b") {
      await sessionBHistory;
    }
  });

  render(
    <BrowserRouter>
      <Routes>
        <Route
          path="/chat/:sessionId?"
          element={<SessionSyncHarness loadHistory={loadHistory} />}
        />
      </Routes>
    </BrowserRouter>,
  );

  await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("session-a"));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 120));
  });

  fireEvent.click(screen.getByRole("button", { name: "Open session B" }));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(window.location.pathname).toBe("/chat/session-b");

  await act(async () => {
    resolveSessionB?.();
    await sessionBHistory;
  });
});
