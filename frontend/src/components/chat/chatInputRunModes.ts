import type { RunModesOptions } from "./richComposer/composerTypes";

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
