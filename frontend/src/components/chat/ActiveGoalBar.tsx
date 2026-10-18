import { InteractiveIcon } from "../common/InteractiveIcon";
import { useEffect, useId, useRef, useState } from "react";
import {
  Target,
  X,
  Pause,
  Play,
  Trash2,
  Maximize2,
  Minimize2,
  Pencil,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PersistentGoal } from "../../services/api/session";
import { getGoalControlScope } from "../../hooks/useAgent/goalControlScope";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";
import { Textarea } from "../common/ui/Textarea";
import { Button } from "../common/ui/Button";
import { formatElapsedCompact } from "./ChatMessage/runStepsCollapseUtils";

interface ActiveGoalBarProps {
  goal: ActiveGoalSpec | null;
  persistentGoal?: PersistentGoal | null;
  onClearPersistentGoal?: () => void;
  onUpdatePersistentGoal?: (
    objective: string,
    rubric: string,
    expectedRevision: number,
  ) => Promise<boolean>;
  persistentDisabled?: boolean;
  onPause?: () => void;
  onResume?: () => void;
  onResumeOrdinary?: () => void;
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
  onResumeOrdinary,
  disabled = false,
  className = "",
}: Omit<ActiveGoalBarProps, "embedded"> & {
  goal: NonNullable<ActiveGoalBarProps["goal"]>;
}) {
  const { t } = useTranslation();
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
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded transition-colors hover:text-theme-text disabled:cursor-not-allowed disabled:opacity-20"
          style={{ opacity: 0.4 }}
        >
          <InteractiveIcon>
            <X className="h-3.5 w-3.5" />
          </InteractiveIcon>
        </button>
      )}
      {goal.ended_at && onResumeOrdinary && (
        <button
          type="button"
          onClick={onResumeOrdinary}
          disabled={disabled}
          aria-label={t("chat.goalPersistent.resume", "Resume goal")}
          title={t("chat.goalPersistent.resume", "Resume goal")}
          className="flex size-9 shrink-0 items-center justify-center rounded-md text-theme-text-secondary hover:text-theme-text focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-theme-primary disabled:opacity-40 sm:size-8"
        >
          <InteractiveIcon>
            <Play className="size-3.5" aria-hidden="true" />
          </InteractiveIcon>
        </button>
      )}
    </div>
  );
}

function PersistentGoalStrip({
  goal,
  runGoal,
  onUpdate,
  onPause,
  onResume,
  onClear,
  disabled,
  embedded,
  className,
}: {
  goal: PersistentGoal;
  runGoal?: ActiveGoalSpec | null;
  onUpdate?: ActiveGoalBarProps["onUpdatePersistentGoal"];
  onPause?: () => void;
  onResume?: () => void;
  onClear?: () => void;
  disabled: boolean;
  embedded: boolean;
  className: string;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const objectiveId = useId();
  const [editing, setEditing] = useState(false);
  const [draftObjective, setDraftObjective] = useState("");
  const [draftRubric, setDraftRubric] = useState("");
  const [editRevision, setEditRevision] = useState(goal.revision);
  const [saving, setSaving] = useState(false);
  const beginEdit = () => {
    setDraftObjective(goal.objective);
    setDraftRubric(goal.rubric);
    setEditRevision(goal.revision);
    setExpanded(true);
    setEditing(true);
  };
  const saveEdit = async () => {
    if (!onUpdate || saving || !draftObjective.trim() || !draftRubric.trim())
      return;
    setSaving(true);
    try {
      if (
        await onUpdate(draftObjective.trim(), draftRubric.trim(), editRevision)
      )
        setEditing(false);
    } finally {
      setSaving(false);
    }
  };
  const status = goal.status === "budget_limited" ? "paused" : goal.status;
  const canPause = status === "active" || status === "waiting_human";
  const canResume = status === "paused" || status === "blocked";
  const [now, setNow] = useState(Date.now());
  const startedAt = runGoal?.started_at;
  const endedAt = runGoal?.ended_at;
  useEffect(() => {
    if (!startedAt || endedAt || !canPause) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt, endedAt, canPause]);
  const elapsedSeconds =
    startedAt && (endedAt || canPause)
      ? Math.max(
          0,
          Math.floor(
            ((endedAt ? Date.parse(endedAt) : now) - Date.parse(startedAt)) /
              1000,
          ),
        )
      : NaN;
  const duration = Number.isFinite(elapsedSeconds)
    ? formatElapsedCompact(elapsedSeconds)
    : "—";
  const buttonClass =
    "flex size-9 sm:size-8 shrink-0 items-center justify-center rounded-md text-theme-text-tertiary transition-colors hover:text-theme-text focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-theme-primary disabled:cursor-not-allowed disabled:opacity-40";
  if (goal.status === "cleared") return null;
  return (
    <div
      className={`grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 px-3 text-13 leading-5 ${
        embedded
          ? "relative mx-3 -mb-3 rounded-t-xl border border-b-0 pb-3"
          : "mx-auto w-full max-w-[52rem] py-2"
      } ${className}`}
      style={
        embedded
          ? {
              backgroundColor:
                "color-mix(in srgb, var(--theme-bg-card) 85%, var(--theme-bg))",
              borderColor:
                "color-mix(in srgb, var(--theme-border) 60%, transparent)",
            }
          : undefined
      }
    >
      <span className="col-start-1 row-start-1 inline-flex min-h-10 items-center gap-1.5 font-medium text-theme-text-secondary">
        <Target
          className="size-3.5 shrink-0 text-theme-text-tertiary"
          aria-hidden="true"
        />
        {t("chat.goalPersistent.label", "Goal")}
      </span>
      <span
        id={objectiveId}
        className={`min-w-0 text-theme-text-secondary ${
          editing
            ? "hidden"
            : expanded
              ? "col-span-3 row-start-2 max-h-48 overflow-y-auto whitespace-pre-wrap border-t border-theme-border-subtle py-2 text-14 leading-relaxed [overflow-wrap:anywhere]"
              : "col-start-2 row-start-1 truncate"
        }`}
        title={expanded ? undefined : goal.objective}
      >
        {goal.objective}
      </span>
      <div className="col-start-3 row-start-1 flex shrink-0 items-center gap-0.5">
        <span
          className="hidden h-9 min-w-8 items-center justify-end pr-1 text-12 tabular-nums text-theme-text-tertiary sm:flex sm:h-8"
          title={t("chat.goal.duration")}
          aria-label={`${t("chat.goal.duration")}: ${duration}`}
        >
          {duration}
        </span>
        {onUpdate && (
          <button
            type="button"
            onClick={beginEdit}
            disabled={disabled || saving}
            aria-label={t("chat.goalPersistent.edit")}
            title={t("chat.goalPersistent.edit")}
            className={buttonClass}
          >
            <InteractiveIcon>
              <Pencil className="size-3.5" aria-hidden="true" />
            </InteractiveIcon>
          </button>
        )}
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            aria-label={t("chat.goalPersistent.clear", "Clear goal")}
            title={t("chat.goalPersistent.clear", "Clear goal")}
            className={buttonClass}
          >
            <InteractiveIcon>
              <Trash2 className="size-3.5" aria-hidden="true" />
            </InteractiveIcon>
          </button>
        )}
        {canPause && onPause && (
          <button
            type="button"
            onClick={onPause}
            disabled={disabled}
            aria-label={t("chat.goalPersistent.pause", "Pause goal")}
            title={t("chat.goalPersistent.pause", "Pause goal")}
            className={buttonClass}
          >
            <InteractiveIcon>
              <Pause className="size-3.5" aria-hidden="true" />
            </InteractiveIcon>
          </button>
        )}
        {canResume && onResume && (
          <button
            type="button"
            onClick={onResume}
            disabled={disabled}
            aria-label={t("chat.goalPersistent.resume", "Resume goal")}
            title={t("chat.goalPersistent.resume", "Resume goal")}
            className={buttonClass}
          >
            <InteractiveIcon>
              <Play className="size-3.5" aria-hidden="true" />
            </InteractiveIcon>
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setEditing(false);
            setExpanded((value) => !value);
          }}
          aria-label={t(expanded ? "common.collapse" : "common.expand")}
          title={t(expanded ? "common.collapse" : "common.expand")}
          aria-expanded={expanded}
          aria-controls={objectiveId}
          className={buttonClass}
        >
          <InteractiveIcon>
            {expanded ? (
              <Minimize2 className="size-3.5" aria-hidden="true" />
            ) : (
              <Maximize2 className="size-3.5" aria-hidden="true" />
            )}
          </InteractiveIcon>
        </button>
      </div>
      {editing && (
        <div
          className="col-span-3 row-start-2 space-y-3 border-t border-theme-border-subtle py-3"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !saving) {
              event.preventDefault();
              event.stopPropagation();
              setEditing(false);
            }
          }}
        >
          <label className="block space-y-1 text-theme-text-secondary">
            <span>{t("chat.goalPersistent.label")}</span>
            <Textarea
              autoFocus
              rows={3}
              maxLength={8000}
              value={draftObjective}
              disabled={saving}
              onChange={(event) => setDraftObjective(event.target.value)}
            />
          </label>
          <label className="block space-y-1 text-theme-text-secondary">
            <span>{t("chat.goalPersistent.criteria")}</span>
            <Textarea
              rows={2}
              maxLength={16000}
              value={draftRubric}
              disabled={saving}
              onChange={(event) => setDraftRubric(event.target.value)}
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              disabled={saving}
              onClick={() => setEditing(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              loading={saving}
              disabled={
                disabled || !draftObjective.trim() || !draftRubric.trim()
              }
              onClick={() => void saveEdit()}
            >
              {t("common.save")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function OrdinaryGoalBar({
  goal,
  label = "Goal",
  durationLabel,
  clearLabel = "Clear goal",
  onClear,
  onResumeOrdinary,
  disabled = false,
  embedded = false,
  className = "",
}: ActiveGoalBarProps) {
  const { t } = useTranslation();
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
        onResumeOrdinary={onResumeOrdinary}
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
      {goal.ended_at && onResumeOrdinary && (
        <button
          type="button"
          onClick={onResumeOrdinary}
          disabled={disabled}
          aria-label={t("chat.goalPersistent.resume", "Resume goal")}
          title={t("chat.goalPersistent.resume", "Resume goal")}
          className="flex size-9 shrink-0 items-center justify-center rounded-md text-theme-text-secondary hover:text-theme-text focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-theme-primary disabled:opacity-40 sm:size-8"
        >
          <InteractiveIcon>
            <Play className="size-3.5" aria-hidden="true" />
          </InteractiveIcon>
        </button>
      )}
      {onClear && (
        <button
          type="button"
          onClick={onClear}
          disabled={disabled}
          title={clearLabel}
          aria-label={clearLabel}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:text-theme-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          <InteractiveIcon>
            <X className="h-4 w-4" />
          </InteractiveIcon>
        </button>
      )}
    </div>
  );
}

export function ActiveGoalBar(props: ActiveGoalBarProps) {
  const {
    goal,
    persistentGoal,
    disabled = false,
    embedded = false,
    className = "",
  } = props;
  const scope = getGoalControlScope(goal, persistentGoal);
  return (
    <>
      {persistentGoal &&
        !["cleared", "completed"].includes(persistentGoal.status) && (
          <PersistentGoalStrip
            key={persistentGoal.id}
            goal={persistentGoal}
            runGoal={goal?._persistent_id === persistentGoal.id ? goal : null}
            onUpdate={props.onUpdatePersistentGoal}
            onPause={props.onPause}
            onResume={props.onResume}
            onClear={
              props.onClearPersistentGoal ??
              (scope === "persistent" ? props.onClear : undefined)
            }
            disabled={props.persistentDisabled ?? disabled}
            embedded={embedded}
            className={className}
          />
        )}
      {scope === "ordinary" && (
        <OrdinaryGoalBar {...props} goal={goal ?? null} />
      )}
    </>
  );
}
