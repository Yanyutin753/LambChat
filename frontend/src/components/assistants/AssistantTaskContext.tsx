import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronDown, Square } from "lucide-react";
import { assistantApi } from "../../services/api/assistant";
import { sessionApi } from "../../services/api/session";
import type { AssistantTask } from "../../types/assistant";
import { assistantTaskTitle } from "./assistantTaskTitle";
import { Button } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

// Keep the decision beside the result, using the same run/revision fences as the work list.
export function AssistantTaskContext({
  assistantId,
  taskId,
  sessionId,
  canWrite,
}: {
  assistantId: string;
  taskId: string;
  sessionId: string;
  canWrite: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loaded, setLoaded] = useState<{
    key: string;
    task: AssistantTask;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const sequence = useRef(0);
  const [refresh, setRefresh] = useState(0);
  const key = `${assistantId}:${taskId}:${sessionId}`;
  const task = loaded?.key === key ? loaded.task : null;
  useEffect(() => {
    let active = true;
    let pending = false;
    const load = async () => {
      if (pending || busyRef.current) return;
      pending = true;
      const request = ++sequence.current;
      try {
        const value = await assistantApi.task(assistantId, taskId);
        if (!active || request !== sequence.current) return;
        if (value.id !== taskId || value.session_id !== sessionId) {
          setLoaded(null);
          throw new Error(t("assistants.conversationMismatch"));
        }
        setLoaded({ key, task: value });
        setError("");
      } catch (failure) {
        if (active && request === sequence.current)
          setError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 5000);
    window.addEventListener("focus", load);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, [assistantId, taskId, sessionId, key, refresh, t]);

  const perform = async (action: () => Promise<unknown>) => {
    if (!canWrite || !task || busyRef.current || error) return;
    busyRef.current = true;
    ++sequence.current;
    setBusy(true);
    try {
      await action();
      setRefresh((value) => value + 1);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };
  const running =
    task &&
    [
      "queued",
      "pending",
      "starting",
      "running",
      "recovering",
      "waiting_human",
    ].includes(task.state);
  return (
    <section
      className="assistant-work-context"
      aria-label={t("assistants.workRecords")}
    >
      {error && (
        <div className="flex flex-wrap items-center gap-2">
          <ConfigPanelErrorCallout message={error} />
          <Button
            size="sm"
            disabled={busy}
            onClick={() => setRefresh((value) => value + 1)}
          >
            {t("common.refresh")}
          </Button>
        </div>
      )}
      {task ? (
        <>
          <div className="assistant-work-context-row">
            {task.source_session_id && task.source_session_id !== sessionId && (
              <Button
                size="sm"
                variant="ghost"
                className="assistant-work-context-action"
                aria-label={t("assistants.returnToSource")}
                title={t("assistants.returnToSource")}
                disabled={busy || !!error}
                leftIcon={<ArrowLeft size={16} />}
                onClick={() =>
                  navigate(
                    `/assistants/${encodeURIComponent(
                      task.source_assistant_id || assistantId,
                    )}/chat/${encodeURIComponent(task.source_session_id!)}`,
                  )
                }
              >
                {t("assistants.returnToSource")}
              </Button>
            )}
            <details className="assistant-work-context-details">
              <summary className="assistant-work-context-summary">
                <span className="truncate" title={task.description}>
                  {assistantTaskTitle(task.description)}
                </span>
                <ChevronDown size={16} aria-hidden="true" />
              </summary>
              <div className="assistant-work-context-description">
                {task.state === "completed" && (
                  <span className="text-12 text-theme-text-muted">
                    {t("assistants.taskStates.completed")}
                  </span>
                )}
                <p>{task.description}</p>
              </div>
            </details>
            {task.state !== "completed" && (
              <span
                className="assistant-work-context-state text-12 text-theme-text-secondary"
                aria-live="polite"
              >
                {t(`assistants.taskStates.${task.state}`, {
                  defaultValue: task.state,
                })}
              </span>
            )}
            {canWrite && running && (
              <Button
                size="sm"
                disabled={busy || !!error}
                variant="ghost"
                className="assistant-work-context-action"
                aria-label={t("assistants.stopTask")}
                title={t("assistants.stopTask")}
                leftIcon={<Square size={16} />}
                onClick={() =>
                  void perform(() => sessionApi.cancel(sessionId, task.run_id))
                }
              >
                {t("assistants.stopTask")}
              </Button>
            )}
          </div>
        </>
      ) : (
        !error && (
          <p role="status" className="text-12 text-theme-text-secondary">
            {t("common.loading")}
          </p>
        )
      )}
    </section>
  );
}
