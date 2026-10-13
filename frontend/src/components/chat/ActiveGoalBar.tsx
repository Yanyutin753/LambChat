import { useEffect, useRef, useState } from "react";
import { Target, X, Pause, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PersistentGoal } from "../../services/api/session";
import { getGoalControlScope } from "../../hooks/useAgent/goalControlScope";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";

interface ActiveGoalBarProps {
  goal: ActiveGoalSpec | null;
  persistentGoal?: PersistentGoal | null;
  onClearPersistentGoal?: () => void;
  persistentDisabled?: boolean;
  onPause?: () => void;
  onResume?: () => void;
  label?: string;
  durationLabel?: string;
  clearLabel?: string;
  onClear?: () => void;
  disabled?: boolean;
  /** When true, renders as an embedded strip inside the chat input card (no border/bg of its own). */
  embedded?: boolean;
  className?: string;
}

/** Format seconds into MM:SS string. */
function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(
    2,
    "0",
  )}`;
}

function EmbeddedGoalBar({
  goal,
  label,
  durationLabel,
  clearLabel = "Clear goal",
  onClear,
  disabled = false,
  className = "",
}: Omit<ActiveGoalBarProps, "embedded"> & {
  goal: NonNullable<ActiveGoalBarProps["goal"]>;
}) {
  const [now, setNow] = useState(Date.now());
  const [exiting, setExiting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const isRunning = !!goal.started_at && !goal.ended_at;

  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  const durationText = (() => {
    if (!goal.started_at) return null;
    const start = new Date(goal.started_at).getTime();
    const end = goal.ended_at ? new Date(goal.ended_at).getTime() : now;
    const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
    return formatDuration(totalSeconds);
  })();

  const handleClear = () => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      onClear?.();
      return;
    }
    setExiting(true);
    const el = containerRef.current;
    if (el) {
      el.addEventListener("animationend", () => onClear?.(), { once: true });
    } else {
      onClear?.();
    }
  };

  return (
    <div
      ref={containerRef}
      className={[
        "flex items-center gap-3 p-3 text-14",
        exiting ? "animate-goal-exit" : "animate-goal-enter",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{
        borderBottom: "1px solid var(--theme-border)",
        color: "var(--theme-text-tertiary)",
      }}
    >
      <Target
        className="size-4 shrink-0"
        style={{ color: "var(--theme-text-tertiary)" }}
      />

      <span
        className="shrink-0 font-medium"
        style={{ color: "var(--theme-text-secondary)" }}
      >
        {label}
      </span>

      <span className="min-w-0 flex-1 truncate" title={goal.objective}>
        {goal.objective}
      </span>

      {durationLabel && durationText && (
        <span className="shrink-0 tabular-nums" style={{ opacity: 0.5 }}>
          {durationText}
        </span>
      )}

      {onClear && (
        <button
          type="button"
          onClick={handleClear}
          disabled={disabled}
          title={clearLabel}
          aria-label={clearLabel}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded transition-colors hover:bg-[var(--theme-bg-hover,rgba(128,128,128,0.08))] disabled:cursor-not-allowed disabled:opacity-20"
          style={{ opacity: 0.4 }}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function PersistentGoalStrip({ goal, onPause, onResume, onClear, disabled, embedded, className }: {
  goal: PersistentGoal; onPause?: () => void; onResume?: () => void; onClear?: () => void;
  disabled: boolean; embedded: boolean; className: string;
}) {
  const { t } = useTranslation();
  const canPause = goal.status === "active" || goal.status === "waiting_human";
  const canResume = goal.status === "paused" || goal.status === "blocked" || goal.status === "budget_limited";
  const buttonClass = "flex size-9 shrink-0 items-center justify-center rounded hover:bg-theme-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-theme-primary disabled:opacity-40";
  if (goal.status === "cleared") return null;
  return <div className={`flex min-w-0 flex-wrap items-center gap-2 px-3 py-2 text-14 ${embedded ? "border-b border-theme-border" : "mx-auto w-full max-w-[52rem]"} ${className}`}>
    <Target className="size-4 shrink-0 text-theme-text-secondary" aria-hidden="true" />
    <div className="min-w-0 flex-1 basis-40">
      <p className="truncate text-theme-text-secondary" title={goal.objective}>{goal.objective}</p>
      <p className="text-12 text-theme-text-tertiary" role="status" aria-live="polite">
        {t(`chat.goalPersistent.status.${goal.status}`, goal.status)} · {t("chat.goalPersistent.turns", { count: goal.accounting.turns, max: goal.limits.max_turns, defaultValue: "{{count}} / {{max}} turns" })} · {goal.accounting.tokens === null ? t("chat.goalPersistent.tokensUnknown", "Token usage unknown") : t("chat.goalPersistent.tokens", { count: goal.accounting.tokens, max: goal.limits.max_tokens, defaultValue: "{{count}} / {{max}} tokens" })} · {t("chat.goalPersistent.timeLimit", { minutes: Math.ceil(goal.limits.max_seconds / 60), defaultValue: "{{minutes}} min limit" })}
      </p>
    </div>
    {canPause && onPause && <button type="button" onClick={onPause} disabled={disabled} aria-label={t("chat.goalPersistent.pause", "Pause goal")} title={t("chat.goalPersistent.pause", "Pause goal")} className={buttonClass}><Pause className="size-4" aria-hidden="true" /></button>}
    {canResume && onResume && <button type="button" onClick={onResume} disabled={disabled} aria-label={t("chat.goalPersistent.resume", "Resume goal")} title={t("chat.goalPersistent.resume", "Resume goal")} className={buttonClass}><Play className="size-4" aria-hidden="true" /></button>}
    {onClear && <button type="button" onClick={onClear} disabled={disabled} aria-label={t("chat.goalPersistent.clear", "Clear goal")} title={t("chat.goalPersistent.clear", "Clear goal")} className={buttonClass}><X className="size-4" aria-hidden="true" /></button>}
  </div>;
}

function OrdinaryGoalBar({
  goal,
  label = "Goal",
  durationLabel,
  clearLabel = "Clear goal",
  onClear,
  disabled = false,
  embedded = false,
  className = "",
}: ActiveGoalBarProps) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!goal?.started_at || goal.ended_at) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [goal?.started_at, goal?.ended_at]);

  const durationText = (() => {
    if (!goal?.started_at) return null;
    const start = new Date(goal.started_at).getTime();
    const end = goal.ended_at ? new Date(goal.ended_at).getTime() : now;
    const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
    return formatDuration(totalSeconds);
  })();

  if (!goal) return null;

  if (embedded) {
    return (
      <EmbeddedGoalBar
        goal={goal}
        label={label}
        durationLabel={durationLabel}
        clearLabel={clearLabel}
        onClear={onClear}
        disabled={disabled}
        className={className}
      />
    );
  }

  return (
    <div
      className={`mx-auto flex w-full max-w-[52rem] min-w-0 items-center gap-2 rounded-md border px-3 py-2 text-14 shadow-sm ${className}`}
      style={{
        borderColor: "var(--theme-border)",
        backgroundColor: "var(--theme-primary-bg, rgba(245,158,11,0.08))",
        color: "var(--theme-text-secondary)",
      }}
    >
      <Target
        className="h-4 w-4 shrink-0"
        style={{ color: "var(--theme-primary)" }}
      />
      <span className="shrink-0 font-medium">{label}</span>
      <span className="min-w-0 flex-1 truncate" title={goal.objective}>
        {goal.objective}
      </span>
      {durationLabel && durationText && (
        <span className="shrink-0 text-12" style={{ opacity: 0.6 }}>
          {durationLabel} {durationText}
        </span>
      )}
      {onClear && (
        <button
          type="button"
          onClick={onClear}
          disabled={disabled}
          title={clearLabel}
          aria-label={clearLabel}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-[var(--theme-bg-hover,rgba(128,128,128,0.08))] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}


export function ActiveGoalBar(props: ActiveGoalBarProps) {
  const { goal, persistentGoal, disabled = false, embedded = false, className = "" } = props;
  const scope = getGoalControlScope(goal, persistentGoal);
  return <>
    {persistentGoal && persistentGoal.status !== "cleared" && <PersistentGoalStrip
      goal={persistentGoal} onPause={props.onPause} onResume={props.onResume}
      onClear={props.onClearPersistentGoal ?? (scope === "persistent" ? props.onClear : undefined)}
      disabled={props.persistentDisabled ?? disabled} embedded={embedded} className={className}
    />}
    {scope === "ordinary" && <OrdinaryGoalBar {...props} goal={goal ?? null} />}
  </>;
}
