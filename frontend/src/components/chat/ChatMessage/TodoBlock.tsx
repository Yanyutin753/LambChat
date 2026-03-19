import { clsx } from "clsx";
import { CheckCircle2, Circle, Loader2, ListTodo } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TodoItem, TodoStatus } from "../../../types";

interface TodoBlockProps {
  items: TodoItem[];
  isStreaming?: boolean;
}

const statusConfig: Record<
  TodoStatus,
  { icon: typeof Circle; colorClass: string; textClass: string }
> = {
  pending: {
    icon: Circle,
    colorClass: "text-stone-400 dark:text-stone-500",
    textClass: "text-stone-500 dark:text-stone-400",
  },
  in_progress: {
    icon: Loader2,
    colorClass: "text-blue-500 dark:text-blue-400",
    textClass: "text-stone-700 dark:text-stone-200 font-medium",
  },
  completed: {
    icon: CheckCircle2,
    colorClass: "text-emerald-500 dark:text-emerald-400",
    textClass: "text-stone-400 dark:text-stone-500 line-through",
  },
};

export function TodoBlock({ items, isStreaming }: TodoBlockProps) {
  const { t } = useTranslation();

  if (!items || items.length === 0) return null;

  const completedCount = items.filter((i) => i.status === "completed").length;
  const totalCount = items.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const isAllDone = completedCount === totalCount && totalCount > 0;

  return (
    <div
      className={clsx(
        "my-1.5 rounded-xl border",
        "border-stone-200 dark:border-stone-700/80",
        "bg-stone-50/80 dark:bg-stone-800/40",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3.5 py-2.5">
        <ListTodo
          size={14}
          className={clsx(
            "shrink-0",
            isAllDone
              ? "text-emerald-500 dark:text-emerald-400"
              : "text-stone-400 dark:text-stone-500",
          )}
        />
        <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
          {t("chat.todo.progress", {
            completed: completedCount,
            total: totalCount,
          })}
        </span>
        {isStreaming && (
          <Loader2
            size={12}
            className="shrink-0 animate-spin text-stone-400 dark:text-stone-500"
          />
        )}
        {/* Progress bar */}
        <div className="ml-auto flex items-center gap-2">
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-700">
            <div
              className={clsx(
                "h-full rounded-full transition-all duration-500 ease-out",
                isAllDone
                  ? "bg-emerald-500 dark:bg-emerald-400"
                  : "bg-blue-500 dark:bg-blue-400",
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-[11px] tabular-nums text-stone-400 dark:text-stone-500">
            {Math.round(progress)}%
          </span>
        </div>
      </div>

      {/* Task list */}
      <div className="space-y-0.5 border-t border-stone-200/60 dark:border-stone-700/50 px-3.5 py-2">
        {items.map((item, index) => (
          <TodoItemRow key={index} item={item} />
        ))}
      </div>
    </div>
  );
}

function TodoItemRow({ item }: { item: TodoItem }) {
  const config = statusConfig[item.status];
  const Icon = config.icon;

  return (
    <div className="flex items-start gap-2.5 py-1">
      <Icon
        size={14}
        className={clsx(
          "shrink-0 mt-0.5",
          config.colorClass,
          item.status === "in_progress" && "animate-spin",
        )}
      />
      <div className="min-w-0 flex-1">
        <p
          className={clsx(
            "text-[13px] leading-snug truncate",
            config.textClass,
            item.status === "in_progress" &&
              "text-stone-800 dark:text-stone-100",
          )}
          title={item.content}
        >
          {item.content}
        </p>
        {item.status === "in_progress" && item.activeForm && (
          <p className="mt-0.5 text-[11px] text-blue-500/70 dark:text-blue-400/70">
            {item.activeForm}
          </p>
        )}
      </div>
    </div>
  );
}
