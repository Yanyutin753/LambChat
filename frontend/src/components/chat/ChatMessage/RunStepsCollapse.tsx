import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import clsx from "clsx";
import { ChevronRight, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatElapsedCompact } from "./runStepsCollapse";

/**
 * run 过程折叠行，1:1 对齐 Codex 终端：
 * 流式中显示 `✻ Working… 42s`（实时计时），完成后定格为
 * `─ Worked for 1m 30s · 12 steps ─────` 的暗淡分隔线，整行可点击展开。
 * 折叠时不渲染任何过程内容。
 */
export function RunStepsCollapse({
  steps,
  durationMs,
  startedAtMs = null,
  active = false,
  renderExpanded,
}: {
  steps: number;
  durationMs: number | null;
  startedAtMs?: number | null;
  active?: boolean;
  renderExpanded: () => ReactNode;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  const settledDurationMs =
    durationMs !== null && durationMs > 0 ? durationMs : null;
  const liveDurationMs =
    active && startedAtMs !== null ? Math.max(0, nowMs - startedAtMs) : null;
  const durationLabel = settledDurationMs
    ? formatElapsedCompact(Math.round(settledDurationMs / 1000))
    : liveDurationMs !== null
      ? formatElapsedCompact(Math.round(liveDurationMs / 1000))
      : null;

  return (
    <div className="run-steps-collapse my-1.5">
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={t("chat.message.runStepsToggle")}
        title={t("chat.message.runStepsToggle")}
        onClick={() => setExpanded((value) => !value)}
        className="group/steps flex w-full cursor-pointer items-center gap-2.5 rounded-md py-1 text-left"
      >
        <span
          aria-hidden="true"
          className="h-px w-5 shrink-0 rounded transition-colors duration-200 group-hover/steps:bg-[var(--theme-text-secondary)]/30"
          style={{ backgroundColor: "var(--theme-border)" }}
        />
        {active ? (
          <Loader2
            size={14}
            className="shrink-0 animate-spin text-theme-text-tertiary"
          />
        ) : (
          <ChevronRight
            size={14}
            strokeWidth={2.5}
            className={clsx(
              "shrink-0 text-theme-text-tertiary opacity-70 transition-transform duration-200 group-hover/steps:opacity-100",
              expanded && "rotate-90",
            )}
          />
        )}
        <span
          className={clsx(
            "min-w-0 whitespace-nowrap font-mono leading-none tabular-nums tracking-wide transition-colors duration-200 group-hover/steps:text-theme-text-secondary",
            active
              ? "text-[0.9375rem] text-theme-text-secondary"
              : "text-[0.9375rem] text-theme-text-tertiary",
          )}
        >
          {active
            ? durationLabel
              ? t("chat.message.runStepsWorking", { duration: durationLabel })
              : t("chat.message.runStepsWorkingNoTimer")
            : durationLabel
              ? t("chat.message.runStepsSummary", {
                  count: steps,
                  duration: durationLabel,
                })
              : t("chat.message.runStepsCount", { count: steps })}
        </span>
        <span
          aria-hidden="true"
          className="h-px min-w-6 flex-1 rounded transition-colors duration-200 group-hover/steps:bg-[var(--theme-text-secondary)]/30"
          style={{ backgroundColor: "var(--theme-border)" }}
        />
      </button>
      {expanded && <div className="space-y-3 pt-2">{renderExpanded()}</div>}
    </div>
  );
}
