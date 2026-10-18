/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from "@testing-library/react";
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
  id: "goal-1",
  session_id: "s1",
  user_id: "u1",
  objective: "Finish verified docs",
  rubric: "tests pass",
  version: 1,
  revision: 2,
  status: "active",
  accounting: { turns: 2, tokens: null },
  started_at: "2026-10-13T01:00:00Z",
  current_run_id: "r1",
} as PersistentGoal;

test("shows only the objective with working pause action", () => {
  const pause = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={goal}
        onPause={pause}
        onClear={() => {}}
        embedded
      />
    </I18nextProvider>,
  );
  expect(screen.getByText("Finish verified docs")).toBeTruthy();
  const button = screen.getByRole("button", { name: /pause|暂停/i });
  fireEvent.click(button);
  expect(pause).toHaveBeenCalledOnce();
  expect(screen.queryByText(/2 turns/)).toBeNull();
  expect(screen.queryByText(/\/ 10/)).toBeNull();
  expect(screen.queryByText(/0.*100000/)).toBeNull();
});

test.each(["paused", "blocked"] as const)("%s goal can resume", (status) => {
  const resume = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={{ ...goal, status }}
        onResume={resume}
      />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /resume|继续/i }));
  expect(resume).toHaveBeenCalledOnce();
});

test("shows live run duration and freezes at the recorded end time", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-17T01:00:04Z"));
  const runGoal = {
    objective: goal.objective,
    _persistent_id: goal.id,
    started_at: "2026-10-17T01:00:00Z",
  };
  const view = (ended_at?: string) => (
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar goal={{ ...runGoal, ended_at }} persistentGoal={goal} />
    </I18nextProvider>
  );
  try {
    const { rerender } = render(view());
    expect(screen.getByText("4s")).toBeTruthy();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("5s")).toBeTruthy();
    rerender(view("2026-10-17T01:00:05Z"));
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByText("5s")).toBeTruthy();
  } finally {
    cleanup();
    vi.useRealTimers();
  }
});

test("does not show another ordinary run's duration on the persistent goal", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={{
          objective: "ordinary",
          started_at: "2026-10-17T01:00:00Z",
          ended_at: "2026-10-17T01:00:04Z",
        }}
        persistentGoal={goal}
      />
    </I18nextProvider>,
  );
  expect(screen.queryByText("4s")).toBeNull();
});

test.each([false, true])(
  "completed ordinary goal can continue in embedded=%s mode",
  (embedded) => {
    const resume = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <ActiveGoalBar
          goal={{
            objective: "ordinary",
            started_at: "2026-10-17T01:00:00Z",
            ended_at: "2026-10-17T01:00:04Z",
          }}
          onResumeOrdinary={resume}
          embedded={embedded}
        />
      </I18nextProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Resume goal" }));
    expect(resume).toHaveBeenCalledOnce();
  },
);

test("expands the full goal and collapses it without changing execution", () => {
  const clear = vi.fn();
  const pause = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={goal}
        onClearPersistentGoal={clear}
        onPause={pause}
        embedded
      />
    </I18nextProvider>,
  );
  const objective = screen.getByText(goal.objective);
  expect(objective.classList.contains("truncate")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Expand" }));
  expect(
    screen
      .getByRole("button", { name: "Collapse" })
      .getAttribute("aria-expanded"),
  ).toBe("true");
  expect(objective.classList.contains("truncate")).toBe(false);
  expect(objective.classList.contains("whitespace-pre-wrap")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Collapse" }));
  expect(objective.classList.contains("truncate")).toBe(true);
  expect(clear).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
});

test("busy goal blocks destructive controls but still allows reading full text", () => {
  const clear = vi.fn();
  const pause = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={goal}
        onClearPersistentGoal={clear}
        onPause={pause}
        persistentDisabled
        embedded
      />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Clear goal" }));
  fireEvent.click(screen.getByRole("button", { name: "Pause goal" }));
  fireEvent.click(screen.getByRole("button", { name: "Expand" }));
  expect(screen.getByRole("button", { name: "Collapse" })).toBeTruthy();
  expect(clear).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
});

test.each(["cleared", "paused", "completed"] as const)(
  "ordinary goal remains visible beside %s persistent state",
  (status) => {
    const clearOrdinary = vi.fn();
    const clearPersistent = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <ActiveGoalBar
          goal={{ objective: "New ordinary task", rubric: "new verification" }}
          persistentGoal={{ ...goal, status }}
          onClear={clearOrdinary}
          onClearPersistentGoal={clearPersistent}
          clearLabel="Clear ordinary goal"
        />
      </I18nextProvider>,
    );
    expect(screen.getByText("New ordinary task")).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Clear ordinary goal" }),
    );
    expect(clearOrdinary).toHaveBeenCalledOnce();
    expect(clearPersistent).not.toHaveBeenCalled();
    if (status === "cleared" || status === "completed")
      expect(screen.queryByText(goal.objective)).toBeNull();
    else {
      expect(screen.getByText(goal.objective)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Clear goal" }));
      expect(clearPersistent).toHaveBeenCalledOnce();
    }
  },
);

test("a paused persistent run projection is not duplicated as an ordinary goal", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={{
          objective: goal.objective,
          rubric: goal.rubric,
          runId: "r1",
          _persistent_id: goal.id,
        }}
        persistentGoal={{ ...goal, status: "paused" }}
      />
    </I18nextProvider>,
  );
  expect(screen.getAllByText(goal.objective)).toHaveLength(1);
});

test("a different rubric is a distinct ordinary goal even with the same objective", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={{
          objective: goal.objective,
          rubric: "different verification",
          runId: "r2",
        }}
        persistentGoal={{ ...goal, status: "paused" }}
      />
    </I18nextProvider>,
  );
  expect(screen.getAllByText(goal.objective)).toHaveLength(2);
});

test("identical ordinary objective and rubric are not persistent authority", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={{ objective: goal.objective, rubric: goal.rubric }}
        persistentGoal={{ ...goal, status: "paused" }}
      />
    </I18nextProvider>,
  );
  expect(screen.getAllByText(goal.objective)).toHaveLength(2);
});

test("ordinary embedded goal clears immediately when reduced motion disables exit animation", () => {
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  const clear = vi.fn();
  try {
    render(
      <ActiveGoalBar
        goal={{ objective: "ordinary", rubric: "verified" }}
        embedded
        onClear={clear}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Clear goal" }));
    expect(clear).toHaveBeenCalledOnce();
  } finally {
    window.matchMedia = original;
  }
});

test.each(["active", "paused", "blocked", "completed"] as const)(
  "%s Goal hides status, usage and run details",
  (status) => {
    render(
      <I18nextProvider i18n={i18n}>
        <ActiveGoalBar
          goal={null}
          persistentGoal={{
            ...goal,
            status,
            stop_reason: "no_progress",
            accounting: { turns: 3, tokens: 131223 },
          }}
        />
      </I18nextProvider>,
    );
    if (status === "completed")
      expect(screen.queryByText(goal.objective)).toBeNull();
    else expect(screen.getByText(goal.objective)).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
    expect(
      screen.queryByText(/131223|3 turns|Working on turn|No new progress/),
    ).toBeNull();
  },
);

test("persistent Goal never displays a wall clock deadline", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar goal={null} persistentGoal={goal} />
    </I18nextProvider>,
  );
  expect(screen.queryByText(/min limit/i)).toBeNull();
});

test("large usage does not prevent a paused Goal from resuming", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={{
          ...goal,
          status: "paused",
          accounting: { turns: 3, tokens: 113774 },
        }}
        onResume={vi.fn()}
      />
    </I18nextProvider>,
  );
  expect(screen.queryByText("Token budget reached")).toBeNull();
  expect(screen.getByRole("button", { name: /resume|继续/i })).toBeTruthy();
});

test("editing preserves the revision snapshot and saves the objective with its criteria", async () => {
  const update = vi.fn().mockResolvedValue(true);
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={goal}
        onUpdatePersistentGoal={update}
        embedded
      />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit goal" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Goal" }), {
    target: { value: "Updated docs" },
  });
  fireEvent.change(
    screen.getByRole("textbox", { name: "Acceptance criteria" }),
    { target: { value: "Updated tests" } },
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
  });
  expect(update).toHaveBeenCalledWith(
    "Updated docs",
    "Updated tests",
    goal.revision,
  );
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("failed edits keep the draft and cancellation never updates the Goal", async () => {
  const update = vi.fn().mockResolvedValue(false);
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={null}
        persistentGoal={goal}
        onUpdatePersistentGoal={update}
        embedded
      />
    </I18nextProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit goal" }));
  const editor = screen.getByRole("textbox", {
    name: "Goal",
  }) as HTMLTextAreaElement;
  fireEvent.change(editor, { target: { value: "Draft stays" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
  });
  expect(editor.value).toBe("Draft stays");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(update).toHaveBeenCalledOnce();
  expect(screen.queryByRole("textbox")).toBeNull();
});

test("completed persistent goal leaves the composer without showing its ended projection", () => {
  render(
    <I18nextProvider i18n={i18n}>
      <ActiveGoalBar
        goal={{
          objective: goal.objective,
          _persistent_id: goal.id,
          ended_at: "2026-10-17T01:00:04Z",
        }}
        persistentGoal={{ ...goal, status: "completed" }}
        embedded
      />
    </I18nextProvider>,
  );
  expect(screen.queryByText(goal.objective)).toBeNull();
  expect(screen.queryByRole("button", { name: /resume|继续/i })).toBeNull();
});
