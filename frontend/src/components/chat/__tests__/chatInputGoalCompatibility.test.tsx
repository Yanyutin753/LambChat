/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, test, expect, vi } from "vitest";
import type { PersistentGoal } from "../../../services/api/session";
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
vi.mock("../../../hooks/useFileUpload", () => ({
  useFileUpload: () => ({
    uploadFiles: vi.fn(),
    uploadFile: vi.fn(),
    uploadLimits: null,
    validateCount: () => true,
    cancelUpload: vi.fn(),
  }),
}));
vi.mock("../ChatInputToolbar", () => ({ ChatInputToolbar: () => null }));
vi.mock("../ChatInputSelectors", () => ({ ChatInputSelectors: () => null }));
import { ChatInput } from "../ChatInput";
afterEach(cleanup);

test.each(["cleared", "paused", "completed"] as const)(
  "composer clears ordinary goal rather than %s persistent goal",
  (status) => {
    const clearOrdinary = vi.fn();
    const controlPersistent = vi.fn();
    const persistentGoal: PersistentGoal = {
      id: "old-goal",
      session_id: "s1",
      user_id: "u1",
      objective: "Old objective",
      rubric: "old rubric",
      version: 1,
      revision: 2,
      status,
      accounting: { turns: 1, tokens: 10 },
      started_at: null,
      current_run_id: "old-run",
    };
    render(
      <ChatInput
        onSend={vi.fn()}
        onStop={vi.fn()}
        isLoading={false}
        activeGoal={{ objective: "New ordinary task", rubric: "new rubric" }}
        persistentGoal={persistentGoal}
        onClearActiveGoal={clearOrdinary}
        onControlPersistentGoal={controlPersistent}
        goalClearLabel="Clear ordinary goal"
      />,
    );
    expect(screen.getByText("New ordinary task")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Clear ordinary goal" });
    fireEvent.click(button);
    fireEvent.animationEnd(button.parentElement!);
    expect(clearOrdinary).toHaveBeenCalledOnce();
    expect(controlPersistent).not.toHaveBeenCalled();
  },
);

test("persistent Goal is a compact header above the composer", () => {
  const persistentGoal: PersistentGoal = {
    id: "g",
    session_id: "s",
    user_id: "u",
    objective: "Release checklist",
    rubric: "verified",
    version: 1,
    revision: 1,
    status: "active",
    accounting: { turns: 3, tokens: 131223 },
    started_at: null,
    current_run_id: "r",
  };
  render(
    <ChatInput
      onSend={vi.fn()}
      onStop={vi.fn()}
      isLoading={false}
      persistentGoal={persistentGoal}
      onControlPersistentGoal={vi.fn()}
    />,
  );
  const objective = screen.getByText("Release checklist");
  expect(objective.closest(".chat-input-container")).toBeNull();
  expect(objective.closest("form")).toBeTruthy();
  expect(screen.queryByText(/131223/)).toBeNull();
});
