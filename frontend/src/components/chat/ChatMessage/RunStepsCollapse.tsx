import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  formatElapsedCompact,
  formatElapsedHuman,
} from "./runStepsCollapseUtils";
import { useUiExpansionState } from "./uiExpansionStore";

/**
 * run 过程折叠区：状态行「已工作 9 分 57 秒 ›」（右侧 chevron、行下淡分隔线）。
 * 流式过程中状态行只读（工作中不显示展开收起控件），直接展示完整过程详情；
 * 完成后自动收起成一行，点击可展开/收起。展开状态按 stateKey 存入会话级
 * store，虚拟列表滚动卸载后滚回不丢。
 */
export function RunStepsCollapse({
  steps,
  durationMs,
  startedAtMs = null,
  active = false,
  stateKey,
  renderExpanded,
}: {
  steps: number;
  durationMs: number | null;
  startedAtMs?: number | null;
  active?: boolean;
  /** 稳定标识（如 message.id）：跨虚拟化卸载复水展开状态 */
  stateKey?: string;
  renderExpanded: () => ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const [expanded, toggleExpanded, setExpanded] = useUiExpansionState(
    stateKey ? `${stateKey}:run-steps` : undefined,
    active,
  );
  const [nowMs, setNowMs] = useState(() => Date.now());

  const prevActiveRef = useRef(active);
  useEffect(() => {
    const wasActive = prevActiveRef.current;
    prevActiveRef.current = active;
    if (active) {
      if (wasActive) return;
      // 新 run 开始：详情直接可见，结束时走自动收起
      setExpanded(true);
      return;
    }
    // 仅在结束翻转时收起；重挂载的历史消息保持 store 复水的状态
    if (wasActive) setExpanded(false);
  }, [active, setExpanded]);

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

  const statusText = active
    ? durationLabel
      ? t("chat.message.runStepsWorking", { duration: durationLabel })
      : t("chat.message.runStepsWorkingNoTimer")
    : durationLabel
      ? t("chat.message.runStepsSummary", { duration: durationLabel })
      : t("chat.message.runStepsCount", { count: steps });
  const statusClass =
    "min-w-0 truncate leading-6 text-[0.9375rem] max-sm:text-base text-gray-700 dark:text-gray-300";

  if (active) {
    return (
      <div className="run-steps-collapse">
        <div className="flex w-full items-baseline gap-1.5 border-b border-theme-border pb-1.5">
          <span className={statusClass}>{statusText}</span>
        </div>
        <div className="space-y-3 pt-2">{renderExpanded()}</div>
      </div>
    );
  }

  return (
    <div className="run-steps-collapse">
      <button
        type="button"
        aria-expanded={expanded}
        aria-label={t("chat.message.runStepsToggle")}
        onClick={toggleExpanded}
        className={clsx(
          "group/steps flex w-full items-baseline gap-1.5 border-b border-theme-border pb-1.5 text-left",
          "cursor-pointer",
        )}
      >
        <span className={statusClass}>{statusText}</span>
        <ChevronRight
          size={16}
          strokeWidth={2}
          className={clsx(
            "self-center shrink-0 text-theme-text-tertiary opacity-70 transition-transform duration-200 group-hover/steps:opacity-100",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded && <div className="space-y-3 pt-2">{renderExpanded()}</div>}
    </div>
  );
}
