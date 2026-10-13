import { selectPersistentGoal } from "../persistentGoalState";
import type { PersistentGoal } from "../../../services/api/session";

const current = { id: "g1", session_id: "s1", revision: 5, current_run_id: "new-run" } as PersistentGoal;

test("late control or polling response cannot restore an older goal/run", () => {
  expect(selectPersistentGoal(current, { ...current, revision: 4, current_run_id: "old-run" }, "s1")).toBe(current);
  expect(selectPersistentGoal(current, { ...current, session_id: "foreign", revision: 6 }, "s1")).toBe(current);
  expect(selectPersistentGoal(current, { ...current, id: "replacement", revision: 6 }, "s1")?.id).toBe("replacement");
});

test("switching sessions never retains the previous goal snapshot", () => {
  expect(selectPersistentGoal(current, { ...current, session_id: "s2", revision: 1 }, "s2")?.session_id).toBe("s2");
});
