import { Target, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RunModeKey } from "./composerTypes";

const MODE_CHIP_META: Record<
  RunModeKey,
  { labelKey: string; fallback: string; icon: typeof Zap; gradient: string }
> = {
  auto: {
    labelKey: "mode.auto",
    fallback: "Auto",
    icon: Zap,
    gradient: "linear-gradient(135deg, rgb(251, 191, 36), rgb(245, 158, 11))",
  },
  goal: {
    labelKey: "mode.goal",
    fallback: "Goal",
    icon: Target,
    gradient: "linear-gradient(135deg, rgb(96, 165, 250), rgb(99, 102, 241))",
  },
};

interface RunModeChipProps {
  modeKey: RunModeKey;
  onClick?: () => void;
  /** Read-only display (e.g. on sent user messages): no button semantics. */
  readOnly?: boolean;
}

/** Active run-mode chip rendered inline in the composer, styled like a skill chip. */
export function RunModeChip({ modeKey, onClick, readOnly }: RunModeChipProps) {
  const { t } = useTranslation();
  const meta = MODE_CHIP_META[modeKey];
  const label = t(meta.labelKey, meta.fallback);
  const Icon = meta.icon;
  return (
    <span
      className="skill-chip-node run-mode-chip-node"
      {...(readOnly
        ? {}
        : { role: "button", tabIndex: 0 })}
      aria-label={label}
      title={label}
      contentEditable={false}
      onClick={readOnly ? undefined : onClick}
      onKeyDown={
        readOnly
          ? undefined
          : (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
      }
    >
      <span
        className="skill-chip-node-avatar"
        style={{ background: meta.gradient }}
      >
        <Icon size="0.82em" className="text-white" strokeWidth={2.5} />
      </span>
      <span className="skill-chip-node-name font-serif">{label}</span>
    </span>
  );
}
