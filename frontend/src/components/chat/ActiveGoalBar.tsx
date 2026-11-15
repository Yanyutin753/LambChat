import { InteractiveIcon } from "../common/InteractiveIcon";
import { useEffect, useId, useState } from "react";
import {
  Target,
  Pause,
  Play,
  Trash2,
  Maximize2,
  Minimize2,
  Pencil,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PersistentGoal } from "../../services/api/session";
import { hasVisiblePersistentGoal } from "./goalVisibility";
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
  clearLabel?: string;
  onClear?: () => void;
  disabled?: boolean;
  /** When true, renders as an embedded strip inside the chat input card (no border/bg of its own). */
  embedded?: boolean;
  className?: string;
}

function GoalStrip({
  goal,
  runGoal,
  onUpdate,
  onPause,
  onResume,
  onClear,
  disabled,
  embedded,
  className,
  clearLabel,
}: {
  goal: PersistentGoal | ActiveGoalSpec;
  runGoal?: ActiveGoalSpec | null;
  onUpdate?: ActiveGoalBarProps["onUpdatePersistentGoal"];
  onPause?: () => void;
  onResume?: () => void;
  onClear?: () => void;
  disabled: boolean;
  embedded: boolean;
  className: string;
  clearLabel?: string;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const objectiveId = useId();
  const [editing, setEditing] = useState(false);
  const [draftObjective, setDraftObjective] = useState("");
  const [draftRubric, setDraftRubric] = useState("");
  const revision = "revision" in goal ? goal.revision : 0;
  const [editRevision, setEditRevision] = useState(revision);
  const [saving, setSaving] = useState(false);
  const beginEdit = () => {
    setDraftObjective(goal.objective);
    setDraftRubric(goal.rubric ?? "");
    setEditRevision(revision);
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
  const status =
    "status" in goal
      ? goal.status === "budget_limited"
        ? "paused"
        : goal.status
      : runGoal?.ended_at
        ? "paused"
        : "active";
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
    : null;
  const buttonClass =
    "flex size-9 sm:size-8 shrink-0 items-center justify-center rounded-md text-theme-text-tertiary transition-colors hover:text-theme-text focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-theme-primary disabled:cursor-not-allowed disabled:opacity-40";
  if (status === "cleared") return null;
  return (
    <div
      className={`grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 px-3 text-13 leading-5 ${
        embedded
          ? "composer-goal-row composer-goal-card"
          : "mx-auto w-full max-w-[52rem] py-2"
      } ${className}`}
    >
      <span className="col-start-1 row-start-1 inline-flex min-h-10 items-center gap-1.5 font-medium text-theme-text-secondary">
        <Target
          className="size-3.5 shrink-0 text-theme-text-tertiary"
          aria-hidden="true"
        />
      </span>
      <span
        id={objectiveId}
        className={`min-w-0 text-theme-text-secondary ${
          editing
            ? "hidden"
            : expanded
              ? "col-span-3 row-start-2 max-h-[min(12rem,30dvh)] overflow-y-auto whitespace-pre-wrap border-t border-theme-border-subtle py-2 text-14 leading-relaxed [overflow-wrap:anywhere]"
              : "composer-goal-summary col-start-2 row-start-1 truncate"
        }`}
        title={expanded ? undefined : goal.objective}
      >
        {goal.objective}
      </span>
      <div className="col-start-3 row-start-1 flex shrink-0 items-center gap-0.5">
        {duration && (
          <span
            className="hidden h-9 min-w-8 items-center justify-end pr-1 text-12 tabular-nums text-theme-text-tertiary sm:flex sm:h-8"
            title={t("chat.goal.duration")}
            aria-label={`${t("chat.goal.duration")}: ${duration}`}
          >
            {duration}
          </span>
        )}
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
              <Pencil size={14} className="size-3.5" aria-hidden="true" />
            </InteractiveIcon>
          </button>
        )}
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            aria-label={
              clearLabel ?? t("chat.goalPersistent.clear", "Clear goal")
            }
            title={clearLabel ?? t("chat.goalPersistent.clear", "Clear goal")}
            className={buttonClass}
          >
            <InteractiveIcon>
              <Trash2 size={14} className="size-3.5" aria-hidden="true" />
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
              <Pause size={14} className="size-3.5" aria-hidden="true" />
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
              <Play size={14} className="size-3.5" aria-hidden="true" />
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
              <Minimize2 size={14} className="size-3.5" aria-hidden="true" />
            ) : (
              <Maximize2 size={14} className="size-3.5" aria-hidden="true" />
            )}
          </InteractiveIcon>
        </button>
      </div>
      {editing && (
        <div
          className="col-span-3 row-start-2 max-h-[min(22rem,40dvh)] space-y-3 overflow-y-auto border-t border-theme-border-subtle py-3"
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
      {persistentGoal && hasVisiblePersistentGoal(persistentGoal) && (
        <GoalStrip
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
      {scope === "ordinary" && goal && (
        <GoalStrip
          goal={goal}
          runGoal={goal}
          onClear={props.onClear}
          clearLabel={props.clearLabel}
          onResume={props.onResumeOrdinary}
          disabled={disabled}
          embedded={embedded}
          className={className}
        />
      )}
    </>
  );
}
