import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatElapsedCompact, formatElapsedHuman } from "./runStepsCollapse";

/**
 * run 过程折叠区：状态行「已工作 9 分 57 秒 ›」（右侧 chevron、行下淡分隔线）。
 * 流式过程中默认展开并实时计时，直接显示完整过程详情；
 * 完成后自动收起成一行，点击可再展开。
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
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(active);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!active) setExpanded(false);
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  const formatElapsed = (ms: number) => {
    const seconds = Math.round(ms / 1000);
    return i18n.language?.toLowerCase().startsWith("zh")
      ? formatElapsedHuman(seconds)
      : formatElapsedCompact(seconds);
  };

  const settledDurationMs =
    durationMs !== null && durationMs > 0 ? durationMs : null;
  // 流式中优先实时走秒；已完成工具推算出的静态 elapsed 不能盖过 live 计时
  const showLive = active && startedAtMs !== null;
  const liveDurationMs = showLive
    ? Math.max(0, nowMs - (startedAtMs as number))
    : null;
  const durationLabel = showLive
    ? formatElapsed(liveDurationMs as number)
    : settledDurationMs
      ? formatElapsed(settledDurationMs)
      : null;

  return (
    <div className="run-steps-collapse">
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={t("chat.message.runStepsToggle")}
        onClick={() => {
          if (!active) setExpanded((value) => !value);
        }}
        disabled={active}
        className={clsx(
          "group/steps flex w-full items-baseline gap-1.5 border-b pb-1.5 text-left",
          active ? "cursor-default" : "cursor-pointer",
        )}
        style={{
          borderColor:
            "color-mix(in srgb, var(--theme-border) 55%, transparent)",
        }}
      >
        <span
          className={clsx(
            "min-w-0 truncate text-[0.9375rem] leading-6 transition-colors duration-200 group-hover/steps:text-theme-text-secondary",
            active ? "text-theme-text-secondary" : "text-theme-text-tertiary",
          )}
        >
          {active
            ? durationLabel
              ? t("chat.message.runStepsWorking", { duration: durationLabel })
              : t("chat.message.runStepsWorkingNoTimer")
            : durationLabel
              ? t("chat.message.runStepsSummary", { duration: durationLabel })
              : t("chat.message.runStepsCount", { count: steps })}
        </span>
        {!active && (
          <ChevronRight
            size={16}
            strokeWidth={2}
            className={clsx(
              "self-center shrink-0 text-theme-text-tertiary opacity-70 transition-transform duration-200 group-hover/steps:opacity-100",
              expanded && "rotate-90",
            )}
          />
        )}
      </button>
      {expanded && <div className="space-y-3 pt-2">{renderExpanded()}</div>}
    </div>
  );
}
