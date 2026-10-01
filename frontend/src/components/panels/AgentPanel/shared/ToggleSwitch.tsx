import React from "react";

interface ToggleSwitchProps {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
  ariaLabel?: string;
}

export const ToggleSwitch = React.memo(function ToggleSwitch({
  enabled,
  onToggle,
  disabled,
  ariaLabel,
}: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={onToggle}
      disabled={disabled}
      className="inline-flex h-11 w-12 flex-shrink-0 items-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--theme-ring)] disabled:opacity-50 sm:h-7"
      aria-label={ariaLabel}
    >
      <span
        aria-hidden="true"
        className={`relative h-7 w-12 rounded-full transition-colors duration-200 motion-reduce:transition-none ${
          enabled ? "bg-amber-500" : "bg-stone-300 dark:bg-stone-600"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow-lg transition-transform duration-200 motion-reduce:transition-none ${
            enabled ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </span>
    </button>
  );
});
