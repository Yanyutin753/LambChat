/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, MemoryRouter, Route, Routes, useNavigate, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { useSessionSync } from "../useSessionSync";

function Harness({ loadHistory }: { loadHistory: (sessionId: string, runId?: string) => Promise<null> }) {
  const navigate = useNavigate();
  const location = useLocation();
  useSessionSync({ activeTab: "chat", sessionId: "s1", loadHistory, clearMessages: () => undefined });
  return <><button onClick={() => navigate("/chat/s1?run_id=old-run", { state: { externalNavigate: true, scrollToBottom: true } })}>Open old notification</button><output aria-label="Current route">{location.pathname}{location.search}</output><output aria-label="Navigation state">{location.state === null ? "cleared" : "active"}</output></>;
}

test("a different run notification in the current session reaches the history target loader", async () => {
  const loadHistory = vi.fn().mockResolvedValue(null);
  render(<MemoryRouter initialEntries={["/chat/s1"]}><Routes><Route path="/chat/:sessionId" element={<Harness loadHistory={loadHistory} />} /></Routes></MemoryRouter>);
  await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("s1", undefined));
  await act(async () => { await new Promise(done => setTimeout(done, 120)); });
  loadHistory.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Open old notification" }));
  await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("s1", "old-run"));
  expect(loadHistory).toHaveBeenCalledOnce();
});

test("clearing notification navigation state keeps the run query for reload and back links", async () => {
  const loadHistory = vi.fn().mockResolvedValue(null);
  window.history.replaceState({ usr: { externalNavigate: true, scrollToBottom: true }, key: "notification-entry" }, "", "/chat/s1?run_id=old-run");
  render(<BrowserRouter><Routes><Route path="/chat/:sessionId" element={<Harness loadHistory={loadHistory} />} /></Routes></BrowserRouter>);
  await waitFor(() => expect(loadHistory).toHaveBeenCalledWith("s1", "old-run"));
  await act(async () => { await new Promise(done => setTimeout(done, 120)); });
  expect(screen.getByLabelText("Navigation state").textContent).toBe("cleared");
  expect(screen.getByLabelText("Current route").textContent).toBe("/chat/s1?run_id=old-run");
});
