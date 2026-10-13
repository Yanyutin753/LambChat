/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { vi, afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import en from "../../../i18n/locales/en.json";
const i18n = createInstance();
await i18n.init({ lng: "en", resources: { en: { translation: en } } });
afterEach(cleanup);
import { ActiveGoalBar } from "../ActiveGoalBar";
import type { PersistentGoal } from "../../../services/api/session";

const goal = {
  id: "goal-1", session_id: "s1", user_id: "u1", objective: "Finish verified docs",
  rubric: "tests pass", version: 1, revision: 2, status: "active",
  limits: { max_turns: 10, max_tokens: 100000, max_seconds: 3600 },
  accounting: { turns: 2, tokens: null }, started_at: "2026-10-13T01:00:00Z", current_run_id: "r1",
} as PersistentGoal;

test("shows persistent status and unknown token budget with working pause action", () => {
  const pause = vi.fn();
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar goal={null} persistentGoal={goal} onPause={pause} onClear={() => {}} embedded /></I18nextProvider>);
  expect(screen.getByText("Finish verified docs")).toBeTruthy();
  const button = screen.getByRole("button", { name: /pause|暂停/i });
  fireEvent.click(button);
  expect(pause).toHaveBeenCalledOnce();
  expect(screen.getByText(/2.*10/)).toBeTruthy();
  expect(screen.queryByText(/0.*100000/)).toBeNull();
});

test("paused goal can resume without pretending it completed", () => {
  const resume = vi.fn();
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar goal={null} persistentGoal={{ ...goal, status: "paused" }} onResume={resume} /></I18nextProvider>);
  fireEvent.click(screen.getByRole("button", { name: /resume|继续/i }));
  expect(resume).toHaveBeenCalledOnce();
});


test.each(["cleared", "paused", "completed"] as const)("ordinary goal remains visible beside %s persistent state", (status) => {
  const clearOrdinary = vi.fn();
  const clearPersistent = vi.fn();
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar
    goal={{ objective: "New ordinary task", rubric: "new verification" }}
    persistentGoal={{ ...goal, status }} onClear={clearOrdinary}
    onClearPersistentGoal={clearPersistent} clearLabel="Clear ordinary goal"
  /></I18nextProvider>);
  expect(screen.getByText("New ordinary task")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Clear ordinary goal" }));
  expect(clearOrdinary).toHaveBeenCalledOnce();
  expect(clearPersistent).not.toHaveBeenCalled();
  if (status === "cleared") expect(screen.queryByText(goal.objective)).toBeNull();
  else {
    expect(screen.getByText(goal.objective)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear goal" }));
    expect(clearPersistent).toHaveBeenCalledOnce();
  }
});

test("a paused persistent run projection is not duplicated as an ordinary goal", () => {
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar
    goal={{ objective: goal.objective, rubric: goal.rubric, runId: "r1", _persistent_id: goal.id }}
    persistentGoal={{ ...goal, status: "paused" }}
  /></I18nextProvider>);
  expect(screen.getAllByText(goal.objective)).toHaveLength(1);
});

test("a different rubric is a distinct ordinary goal even with the same objective", () => {
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar
    goal={{ objective: goal.objective, rubric: "different verification", runId: "r2" }}
    persistentGoal={{ ...goal, status: "paused" }}
  /></I18nextProvider>);
  expect(screen.getAllByText(goal.objective)).toHaveLength(2);
});


test("identical ordinary objective and rubric are not persistent authority", () => {
  render(<I18nextProvider i18n={i18n}><ActiveGoalBar
    goal={{ objective: goal.objective, rubric: goal.rubric }}
    persistentGoal={{ ...goal, status: "paused" }}
  /></I18nextProvider>);
  expect(screen.getAllByText(goal.objective)).toHaveLength(2);
});


test("ordinary embedded goal clears immediately when reduced motion disables exit animation", () => {
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  const clear = vi.fn();
  try {
    render(<ActiveGoalBar goal={{ objective: "ordinary", rubric: "verified" }} embedded onClear={clear} />);
    fireEvent.click(screen.getByRole("button", { name: "Clear goal" }));
    expect(clear).toHaveBeenCalledOnce();
  } finally { window.matchMedia = original; }
});
