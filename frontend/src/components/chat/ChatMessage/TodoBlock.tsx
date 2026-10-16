import { InteractiveIcon } from "../../common/InteractiveIcon";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { clsx } from "clsx";
import {
  CheckCircle2,
  ChevronRight,
  Circle,
  ListTodo,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TodoItem, TodoStatus } from "../../../types";
import { useUiExpansionState } from "./uiExpansionStore";

interface TodoBlockProps {
  items: TodoItem[];
  isStreaming?: boolean;
  /** 稳定标识（messageId:partIndex）：折叠状态跨虚拟化卸载保留 */
  stateKey?: string;
}

const statusConfig: Record<
  TodoStatus,
  {
    icon: typeof Circle | typeof LoadingSpinner;
    colorClass: string;
    textClass: string;
  }
> = {
  pending: {
    icon: Circle,
    colorClass: "text-theme-text-tertiary",
    textClass: "text-theme-text-secondary",
  },
  in_progress: {
    icon: LoadingSpinner,
    colorClass: "text-[var(--theme-primary)]",
    textClass: "text-theme-text font-medium",
  },
  completed: {
    icon: CheckCircle2,
    colorClass: "text-theme-success",
    textClass: "text-theme-text-tertiary line-through",
  },
  cancelled: {
    icon: XCircle,
    colorClass: "text-theme-text-tertiary",
    textClass: "text-theme-text-tertiary line-through",
  },
};

export function TodoBlock({ items, isStreaming, stateKey }: TodoBlockProps) {
  const { t } = useTranslation();
  // 长会话翻阅时可收起整块清单（默认展开；状态存会话级 store，
  // 虚拟列表滚动卸载后滚回不丢）
  const [collapsed, toggleCollapsed] = useUiExpansionState(
    stateKey ? `${stateKey}:todo-collapsed` : undefined,
    false,
  );

  if (!items || items.length === 0) return null;

  const completedCount = items.filter((i) => i.status === "completed").length;
  const totalCount = items.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const isAllDone = completedCount === totalCount && totalCount > 0;

  return (
    <div
      className={clsx(
        "chat-process-todo my-1.5 min-w-0 rounded-xl border border-theme-border",
        "bg-theme-bg-card",
      )}
    >
      {/* Header（点击折叠/展开） */}
      <button
        type="button"
        aria-expanded={!collapsed}
        aria-label={t("chat.todo.toggle")}
        onClick={() => toggleCollapsed()}
        className="group/todo flex w-full cursor-pointer font-sans items-center gap-2 min-h-11 px-3.5 py-2.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
      >
        <InteractiveIcon>
          <ListTodo
            size={14}
            className={clsx(
              "shrink-0",
              isAllDone ? "text-theme-success" : "text-theme-text-tertiary",
            )}
          />
        </InteractiveIcon>
        <span className="text-12 font-medium text-theme-text-secondary">
          {t("chat.todo.progress", {
            completed: completedCount,
            total: totalCount,
          })}
        </span>
        {isStreaming && (
          <LoadingSpinner
            color="text-current"
            size={12}
            className="shrink-0 text-theme-text-tertiary"
          />
        )}
        {/* Progress bar */}
        <div className="ml-auto flex items-center gap-2">
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-theme-border">
            <div
              className={clsx(
                "h-full rounded-full transition-all duration-500 ease-out",
                isAllDone ? "bg-theme-success" : "bg-theme-text-tertiary",
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-11 tabular-nums text-theme-text-tertiary">
            {Math.round(progress)}%
          </span>
          <InteractiveIcon>
            <ChevronRight
              size={14}
              className={clsx(
                "shrink-0 text-theme-text-tertiary opacity-70 transition-transform duration-200 group-hover/todo:opacity-100",
                !collapsed && "rotate-90",
              )}
            />
          </InteractiveIcon>
        </div>
      </button>

      {/* Task list */}
      {!collapsed && (
        <div className="space-y-0.5 border-t border-theme-border/60 px-3.5 py-2 max-h-60 overflow-y-auto">
          {items.map((item, index) => (
            <TodoItemRow key={index} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export function TodoItemRow({
  item,
  wrap = false,
}: {
  item: TodoItem;
  wrap?: boolean;
}) {
  const { t } = useTranslation();
  const config = statusConfig[item.status];
  const Icon = config.icon;

  return (
    <div className="relative flex items-start gap-2.5 py-1">
      <Icon size={14} className={clsx("shrink-0 mt-0.5", config.colorClass)} />
      <div className="min-w-0 flex-1">
        <p
          className={clsx(
            "text-13 leading-snug",
            wrap
              ? "whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
              : "truncate",
            config.textClass,
          )}
          title={item.content}
        >
          {item.content}
          <span className="sr-only left-0 top-0">
            {" "}
            — {t(`chat.todo.${item.status}`)}
          </span>
        </p>
      </div>
    </div>
  );
}
