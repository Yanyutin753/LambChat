import type { RunModeKey, RunModesOptions } from "./richComposer/composerTypes";

type ToggleHandler = (enabled: boolean) => void;

/** Bridges ChatInput's run-mode props into the composer's chip wiring. */
export function buildRunModesOptions(
  autoEnabled: boolean,
  goalEnabled: boolean,
  onToggleAutoMode?: ToggleHandler,
  onToggleGoalMode?: ToggleHandler,
): RunModesOptions {
  return {
    autoEnabled,
    goalEnabled,
    onToggle: (key, enabled) => {
      if (key === "auto") onToggleAutoMode?.(enabled);
      else onToggleGoalMode?.(enabled);
    },
  };
}

/**
 * Run modes active at send time, derived from the authoritative toggle
 * booleans (the composer chips reconcile from / toggle these same values).
 */
export function collectActiveRunModes(
  autoEnabled: boolean,
  goalEnabled: boolean,
): RunModeKey[] {
  const modes: RunModeKey[] = [];
  if (autoEnabled) modes.push("auto");
  if (goalEnabled) modes.push("goal");
  return modes;
}
