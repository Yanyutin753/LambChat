import { describe, expect, test, vi } from "vitest";
import { buildRunModesOptions } from "../chatInputRunModes";

describe("buildRunModesOptions", () => {
  test("passes the enabled flags through", () => {
    const options = buildRunModesOptions(true, false);
    expect(options.autoEnabled).toBe(true);
    expect(options.goalEnabled).toBe(false);
  });

  test("routes auto toggles to the auto handler", () => {
    const onToggleAutoMode = vi.fn();
    const onToggleGoalMode = vi.fn();
    const options = buildRunModesOptions(
      true,
      true,
      onToggleAutoMode,
      onToggleGoalMode,
    );

    options.onToggle("auto", false);

    expect(onToggleAutoMode).toHaveBeenCalledWith(false);
    expect(onToggleGoalMode).not.toHaveBeenCalled();
  });

  test("routes goal toggles to the goal handler", () => {
    const onToggleAutoMode = vi.fn();
    const onToggleGoalMode = vi.fn();
    const options = buildRunModesOptions(
      true,
      true,
      onToggleAutoMode,
      onToggleGoalMode,
    );

    options.onToggle("goal", true);

    expect(onToggleGoalMode).toHaveBeenCalledWith(true);
    expect(onToggleAutoMode).not.toHaveBeenCalled();
  });
});
