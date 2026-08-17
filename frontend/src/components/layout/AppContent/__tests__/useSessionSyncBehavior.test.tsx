/** @vitest-environment jsdom */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { BrowserRouter, Route, Routes, useNavigate } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { useSessionSync } from "../useSessionSync";
import type { SessionConfig } from "../../../../hooks/useAgent/types";

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

function CorrelatedSessionSyncHarness({
  loadHistory,
  onSessionLoadStart,
  onConfigRestored,
}: {
  loadHistory: (sessionId: string) => Promise<SessionConfig | null>;
  onSessionLoadStart: (loadId: number) => void;
  onConfigRestored: (config: SessionConfig, loadId: number) => void;
}) {
  const { handleSelectSession } = useSessionSync({
    activeTab: "chat",
    sessionId: "session-a",
    loadHistory,
    clearMessages: () => undefined,
    onSessionLoadStart,
    onConfigRestored,
  });

  return (
    <button type="button" onClick={() => void handleSelectSession("session-b")}>
      Load session B
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

test("does not replace URL back to old session while browser-back load is in progress (infinite redirect fix)", async () => {
  window.history.replaceState(null, "", "/chat/session-a");

  const loadHistoryCalls: string[] = [];
  let resolveSessionA: (() => void) | undefined;

  // Simulate a slow load for session-a (triggered by browser back)
  const sessionALoad = new Promise<void>((resolve) => {
    resolveSessionA = resolve;
  });

  const loadHistory = vi.fn(async (sessionId: string) => {
    loadHistoryCalls.push(sessionId);
    if (sessionId === "session-a") await sessionALoad;
  });

  // Harness: starts on session-a, then navigates to session-b, then back
  function BackNavHarness() {
    const [sessionId, setSessionId] = useState<string | null>("session-a");
    const navigate = useNavigate();
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
      <>
        <button
          type="button"
          onClick={() => void handleSelectSession("session-b")}
        >
          Open session B
        </button>
        <button
          type="button"
          onClick={() => {
            // Simulate browser back by pushing session-a into history
            window.history.pushState(null, "", "/chat/session-a");
            window.dispatchEvent(new PopStateEvent("popstate"));
          }}
        >
          Go Back
        </button>
      </>
    );
  }

  render(
    <BrowserRouter>
      <Routes>
        <Route path="/chat/:sessionId?" element={<BackNavHarness />} />
      </Routes>
    </BrowserRouter>,
  );

  // Wait for initial mount sync to complete
  await waitFor(() => expect(loadHistoryCalls).toContain("session-a"));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 120));
  });

  // User selects session-b (internal navigation → push)
  fireEvent.click(screen.getByRole("button", { name: "Open session B" }));
  await waitFor(() => expect(loadHistoryCalls).toContain("session-b"));
  expect(window.location.pathname).toBe("/chat/session-b");

  // Simulate browser back → URL changes to session-a
  fireEvent.click(screen.getByRole("button", { name: "Go Back" }));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });

  // The URL should show session-a (from back), NOT be replaced back to session-b
  // by the URL-sync effect while the load is in progress.
  expect(window.location.pathname).toBe("/chat/session-a");

  // Let the slow session-a load complete
  await act(async () => {
    resolveSessionA?.();
    await sessionALoad;
  });

  // After load completes, URL should still be session-a
  expect(window.location.pathname).toBe("/chat/session-a");

  // session-a should only have been loaded a reasonable number of times.
  // The bug would cause 3+ loads (mount → select-b → back → sync replaces → load → …).
  const sessionALoadCount = loadHistoryCalls.filter(
    (id) => id === "session-a",
  ).length;
  expect(sessionALoadCount).toBeLessThanOrEqual(2);
});

test("pairs each history load start and restore with the same load ID", async () => {
  window.history.replaceState(null, "", "/chat/session-a");
  const events: string[] = [];

  const loadHistory = vi.fn(async (sessionId: string) => {
    events.push(`load:${sessionId}`);
    return { agent_id: sessionId };
  });

  render(
    <BrowserRouter>
      <Routes>
        <Route
          path="/chat/:sessionId?"
          element={
            <CorrelatedSessionSyncHarness
              loadHistory={loadHistory}
              onSessionLoadStart={(loadId) => {
                events.push(`start:${loadId}`);
              }}
              onConfigRestored={(config, loadId) => {
                events.push(`restore:${config.agent_id}:${loadId}`);
              }}
            />
          }
        />
      </Routes>
    </BrowserRouter>,
  );

  await waitFor(() => {
    expect(events.slice(0, 3)).toEqual([
      "start:1",
      "load:session-a",
      "restore:session-a:1",
    ]);
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 120));
  });

  fireEvent.click(screen.getByRole("button", { name: "Load session B" }));

  await waitFor(() => {
    expect(events.slice(3)).toEqual([
      "start:2",
      "load:session-b",
      "restore:session-b:2",
    ]);
  });
});

test("keeps overlapping history load IDs correlated when an older load finishes late", async () => {
  window.history.replaceState(null, "", "/chat/session-a");
  const events: string[] = [];
  let resolveSessionA: ((config: SessionConfig | null) => void) | undefined;
  const sessionAHistory = new Promise<SessionConfig | null>((resolve) => {
    resolveSessionA = resolve;
  });

  const loadHistory = vi.fn(async (sessionId: string) => {
    events.push(`load:${sessionId}`);
    if (sessionId === "session-a") return sessionAHistory;
    return { agent_id: sessionId };
  });

  render(
    <BrowserRouter>
      <Routes>
        <Route
          path="/chat/:sessionId?"
          element={
            <CorrelatedSessionSyncHarness
              loadHistory={loadHistory}
              onSessionLoadStart={(loadId) => {
                events.push(`start:${loadId}`);
              }}
              onConfigRestored={(config, loadId) => {
                events.push(`restore:${config.agent_id}:${loadId}`);
              }}
            />
          }
        />
      </Routes>
    </BrowserRouter>,
  );

  await waitFor(() => {
    expect(events).toEqual(["start:1", "load:session-a"]);
  });

  fireEvent.click(screen.getByRole("button", { name: "Load session B" }));
  await waitFor(() => {
    expect(events).toContain("restore:session-b:2");
  });

  await act(async () => {
    resolveSessionA?.({ agent_id: "session-a" });
    await sessionAHistory;
  });

  expect(events).toEqual([
    "start:1",
    "load:session-a",
    "start:2",
    "load:session-b",
    "restore:session-b:2",
    "restore:session-a:1",
  ]);
});
