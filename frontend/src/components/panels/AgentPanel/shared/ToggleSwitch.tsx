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
      role="switch"
      aria-checked={enabled}
      onClick={onToggle}
      disabled={disabled}
      className={`relative h-7 w-12 flex-shrink-0 rounded-full transition-all duration-200 ease-out ${
        enabled
          ? "bg-amber-500 dark:bg-amber-500"
          : "bg-stone-300 dark:bg-stone-600"
      }`}
      aria-label={ariaLabel}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow-lg transition-transform duration-200 ${
          enabled ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
});
