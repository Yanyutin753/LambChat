import { useEffect, useMemo, useSyncExternalStore } from "react";
import { CheckCircle2, ChevronRight, ListTodo } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Message } from "../../types";
import { getSessionTodo } from "./sessionTodo";
import { TodoItemRow } from "./ChatMessage/TodoBlock";
import {
  closePersistentToolPanel,
  isPersistentToolPanelActive,
  openPersistentToolPanel,
  updatePersistentToolPanel,
} from "./ChatMessage/items/persistentToolPanelState";
import { subscribeRightPanels } from "../common/rightPanelCoordinator";

export function SessionTodoDock({
  sessionId,
  messages,
  currentRunId,
  running,
}: {
  sessionId: string | null;
  messages: Message[];
  currentRunId?: string | null;
  running: boolean;
}) {
  const { t } = useTranslation();
  const todo = useMemo(
    () => (running ? getSessionTodo(messages, currentRunId) : null),
    [messages, currentRunId, running],
  );
  const panelKey = `session-todos:${sessionId}`;
  const active = useSyncExternalStore(subscribeRightPanels, () =>
    isPersistentToolPanelActive(panelKey),
  );
  const items = todo?.items ?? [];
  const completed = items.filter((item) => item.status === "completed").length;
  const cancelled = items.filter((item) => item.status === "cancelled").length;
  const current =
    items.find((item) => item.status === "in_progress") ??
    items.find((item) => item.status === "pending");
  const progress = t("chat.todo.progress", { completed, total: items.length });
  const summary = current
    ? current.status === "in_progress"
      ? current.activeForm || current.content
      : current.content
    : cancelled
      ? t("chat.todo.cancelledCount", { count: cancelled })
      : t("chat.todo.allCompleted");
  const panel = useMemo(
    () => ({
      panelKey,
      title: t("chat.todo.toggle"),
      icon: <ListTodo size={16} />,
      status: "idle" as const,
      subtitle: progress,
      mobileFillViewport: true,
      children: (
        <div className="px-4 py-4">
          <ul className="space-y-3" aria-label={t("chat.todo.toggle")}>
            {todo?.items.map((item, index) => (
              <li key={index}>
                <TodoItemRow item={item} wrap />
              </li>
            ))}
          </ul>
        </div>
      ),
    }),
    [panelKey, progress, t, todo],
  );

  useEffect(() => () => closePersistentToolPanel(panelKey), [panelKey]);
  useEffect(() => {
    if (!sessionId || !todo) {
      closePersistentToolPanel(panelKey);
      return;
    }
    updatePersistentToolPanel(
      (previous) => ({ ...previous, ...panel }),
      panelKey,
    );
  }, [panel, panelKey, sessionId, todo]);

  if (!sessionId || !todo) return null;
  const Icon = completed === items.length ? CheckCircle2 : ListTodo;
  return (
    <div className="shrink-0 px-2 sm:px-8">
      <div className="mx-auto max-w-4xl lg:max-w-5xl xl:max-w-6xl">
        <div className="w-fit max-w-full">
          <button
            type="button"
            aria-label={t("chat.todo.openPanel")}
            aria-expanded={active}
            onClick={() =>
              active
                ? closePersistentToolPanel(panelKey)
                : openPersistentToolPanel(panel)
            }
            className={`mb-1 flex min-h-11 w-full max-w-full min-w-0 items-center gap-2 rounded-lg border border-transparent px-5 py-2 text-left text-12 text-theme-text-secondary transition-colors hover:text-theme-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]`}
          >
            <Icon
              size={16}
              className="shrink-0 text-[var(--theme-primary)]"
              aria-hidden="true"
            />
            <span className="shrink-0 tabular-nums">{progress}</span>
            {(current || cancelled > 0) && (
              <span
                className="min-w-0 max-w-[20ch] truncate text-theme-text-tertiary"
                title={summary}
              >
                {summary}
              </span>
            )}
            <ChevronRight size={16} className="shrink-0" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
