import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowUp,
  ChevronDown,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Plus,
  RefreshCw,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { EmptyState } from "../common/EmptyState";
import { useNavigate } from "react-router-dom";
import { assistantApi } from "../../services/api/assistant";
import { sessionApi } from "../../services/api/session";
import { translateApiError } from "../../utils/backendErrors";
import { formatDateTimeShort } from "../../utils/datetime";
import type { Assistant, AssistantTask } from "../../types/assistant";
import { assistantTaskTitle } from "./assistantTaskTitle";
import { AssistantSurface } from "./AssistantSurface";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { Button, FormField, Input, Textarea } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

const PAGE_SIZE = 10;
const TASK_GROUPS = ["attention", "active", "history"] as const;
const GROUP_ICONS = {
  attention: CircleAlert,
  active: Clock3,
  history: CheckCircle2,
};
function taskGroup(state: string) {
  if (
    [
      "queued",
      "pending",
      "starting",
      "running",
      "recovering",
      "cancelling",
    ].includes(state)
  )
    return "active";
  if (["completed", "awaiting_review", "accepted", "cancelled"].includes(state))
    return "history";
  return "attention";
}

export function AssistantTasksDialog({
  assistant,
  canWrite,
  onClose,
  embedded = false,
}: {
  assistant: Assistant;
  canWrite: boolean;
  onClose: () => void;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const formId = useId();
  const [creating, setCreating] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (creating) formRef.current?.querySelector("textarea")?.focus();
  }, [creating]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{
    tasks: AssistantTask[];
    total: number;
  } | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [description, setDescription] = useState("");
  const [minutes, setMinutes] = useState("30");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const admission = useRef<{ signature: string; id: string } | null>(null);

  useEffect(() => {
    let active = true;
    let pending = false;
    const load = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await assistantApi.tasks(
          assistant.id,
          (page - 1) * PAGE_SIZE,
          PAGE_SIZE,
        );
        if (active) {
          setData(result);
          setTotal(result.total);
          setLoadError("");
        }
      } catch (failure) {
        if (active)
          setLoadError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [assistant.id, page, refresh, t]);

  const perform = async (action: () => Promise<unknown>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
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
  const create = () =>
    perform(async () => {
      const input = {
        description: description.trim(),
        timeout_seconds: Math.round(Number(minutes) * 60),
      };
      const signature = JSON.stringify(input);
      if (admission.current?.signature !== signature)
        admission.current = { signature, id: crypto.randomUUID() };
      const result = await assistantApi.createTask(assistant.id, {
        ...input,
        request_id: admission.current.id,
      });
      if (result.status === "error")
        throw new Error(t("assistants.admissionAttention"));
      admission.current = null;
      setDescription("");
      setCreating(false);
      document.getElementById(`${formId}-toggle`)?.focus();
      setPage(1);
      if (result.session_id) {
        onClose();
        navigate(
          `/assistants/${encodeURIComponent(
            assistant.id,
          )}/chat/${encodeURIComponent(result.session_id)}`,
        );
      }
    });

  const openTask = (task: AssistantTask) => {
    if (!task.session_id) return;
    onClose();
    navigate(
      `/assistants/${encodeURIComponent(
        task.assistant_id || assistant.id,
      )}/chat/${encodeURIComponent(task.session_id)}`,
    );
  };

  const taskAction = canWrite && assistant.status === "active" && (
    <Button
      variant={embedded ? "primary" : "secondary"}
      id={`${formId}-toggle`}
      leftIcon={<Plus size={16} />}
      aria-expanded={creating}
      aria-controls={creating ? formId : undefined}
      disabled={busy}
      onClick={() => setCreating((value) => !value)}
    >
      {t("assistants.newTask")}
    </Button>
  );
  return (
    <AssistantSurface
      embedded={embedded}
      open
      onClose={onClose}
      title={t("assistants.tasksTitle", { name: assistant.name })}
      size="lg"
      dismissible={!busy}
      footer={
        <>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={(next) => {
              setData(null);
              setLoadError("");
              setPage(next);
            }}
          />
          <Button
            leftIcon={<RefreshCw size={16} />}
            onClick={() => setRefresh((value) => value + 1)}
          >
            {t("common.refresh")}
          </Button>
        </>
      }
    >
      <div className={embedded ? "assistant-task-page" : "space-y-4"}>
        {(error || loadError) && (
          <ConfigPanelErrorCallout message={error || loadError} />
        )}
        {embedded ? (
          <PanelHeader
            className="!px-0"
            title={t("assistants.workRecords")}
            count={data?.total}
            subtitle={t("assistants.taskHint")}
            actions={taskAction}
          />
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-14 text-theme-text-secondary" aria-live="polite">
              {data
                ? t("assistants.taskCount", { count: data.total })
                : t("assistants.tasks")}
            </p>
            {taskAction}
          </div>
        )}
        {!embedded && (
          <p className="text-13 text-theme-text-secondary">
            {t("assistants.taskHint")}
          </p>
        )}
        {canWrite && assistant.status === "active" && creating && (
          <form
            id={formId}
            ref={formRef}
            className={embedded ? "assistant-task-composer" : "space-y-3"}
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <fieldset disabled={busy} className="space-y-3">
              <FormField
                className={
                  embedded ? "assistant-task-composer-description" : undefined
                }
                label={t("assistants.taskDescription")}
              >
                <Textarea
                  placeholder={
                    embedded ? t("assistants.taskPlaceholder") : undefined
                  }
                  required
                  maxLength={20000}
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </FormField>
              <div
                className={
                  embedded
                    ? "assistant-task-composer-footer"
                    : "flex flex-wrap items-end gap-3"
                }
              >
                <FormField label={t("assistants.taskTimeout")}>
                  <Input
                    type="number"
                    required
                    min={0.5}
                    max={1440}
                    step={0.5}
                    value={minutes}
                    onChange={(event) => setMinutes(event.target.value)}
                  />
                </FormField>
                <Button
                  type="submit"
                  leftIcon={embedded ? <ArrowUp size={16} /> : undefined}
                  variant="primary"
                  loading={busy}
                  disabled={
                    !description.trim() ||
                    !Number.isFinite(Number(minutes)) ||
                    Number(minutes) < 0.5 ||
                    Number(minutes) > 1440
                  }
                >
                  {t("assistants.startTask")}
                </Button>
              </div>
            </fieldset>
          </form>
        )}
        {data && data.total > PAGE_SIZE && (
          <p className="text-12 text-theme-text-secondary">
            {t("assistants.pageGroupingHint")}
          </p>
        )}
        {!data && !loadError ? (
          <PanelLoadingState />
        ) : data?.tasks.length === 0 ? (
          <EmptyState
            illustration="panel-schedule"
            title={t("assistants.noTasks")}
          />
        ) : (
          TASK_GROUPS.map((group) => {
            const tasks =
              data?.tasks.filter((task) => taskGroup(task.state) === group) ??
              [];
            const Icon = GROUP_ICONS[group];
            return (
              tasks.length > 0 && (
                <section
                  key={group}
                  aria-label={t(`assistants.taskGroups.${group}`)}
                >
                  <h3 className="flex items-center gap-2 text-12 font-medium text-theme-text-secondary">
                    <Icon size={16} aria-hidden="true" />
                    {t(`assistants.taskGroups.${group}`)}
                    <span className="tabular-nums">{tasks.length}</span>
                  </h3>
                  <ul
                    className={
                      embedded
                        ? "assistant-task-list"
                        : "divide-y divide-theme-border"
                    }
                  >
                    {tasks.map((task) => (
                      <li
                        key={task.id}
                        className={
                          embedded ? "assistant-task-row" : "space-y-2 py-4"
                        }
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <h4
                            className={
                              embedded
                                ? "assistant-task-title"
                                : "min-w-0 flex-1 line-clamp-3 break-words font-medium text-theme-text"
                            }
                            title={task.description}
                          >
                            {embedded && task.session_id ? (
                              <button
                                type="button"
                                onClick={() => openTask(task)}
                              >
                                {assistantTaskTitle(task.description)}
                              </button>
                            ) : (
                              task.description
                            )}
                          </h4>
                          <span className="text-12 text-theme-text-secondary">
                            {t(`assistants.taskStates.${task.state}`, {
                              defaultValue: task.state,
                            })}
                          </span>
                        </div>
                        {task.error_code && (
                          <p className="text-12 text-theme-error">
                            {translateApiError(
                              task.error_code,
                              t("assistants.taskFailedHint"),
                              undefined,
                              t,
                            )}
                          </p>
                        )}
                        <div className="assistant-task-actions flex flex-wrap gap-2">
                          {!embedded && task.session_id && (
                            <Button onClick={() => openTask(task)}>
                              {t("assistants.inspectTask")}
                            </Button>
                          )}
                          {canWrite &&
                            task.session_id &&
                            [
                              "queued",
                              "pending",
                              "starting",
                              "running",
                              "recovering",
                              "waiting_human",
                            ].includes(task.state) && (
                              <Button
                                disabled={busy}
                                onClick={() =>
                                  void perform(() =>
                                    sessionApi.cancel(
                                      task.session_id!,
                                      task.run_id,
                                    ),
                                  )
                                }
                              >
                                {t("assistants.stopTask")}
                              </Button>
                            )}
                        </div>
                        <details
                          className={
                            embedded
                              ? "assistant-task-details text-12 text-theme-text-secondary"
                              : "text-12 text-theme-text-secondary"
                          }
                        >
                          <summary
                            className={
                              embedded
                                ? "assistant-task-details-toggle"
                                : "w-fit cursor-pointer rounded py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary"
                            }
                          >
                            {embedded && (
                              <time dateTime={task.created_at}>
                                {formatDateTimeShort(task.created_at)}
                              </time>
                            )}
                            <span>
                              {t("assistants.taskDetails")}
                              {embedded && <ChevronDown size={12} />}
                            </span>
                          </summary>
                          <div className="space-y-2 pb-2">
                            <p className="whitespace-pre-wrap break-words text-theme-text">
                              {task.description}
                            </p>

                            <p className="break-all text-12 text-theme-text-secondary">
                              {t("assistants.taskReference")}{" "}
                              <code className="select-all">{task.id}</code>
                            </p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-12 text-theme-text-secondary">
                              {task.authorization && (
                                <span>
                                  {t(
                                    `assistants.authorization.${task.authorization.kind}`,
                                  )}
                                </span>
                              )}
                              <span>
                                {t(
                                  task.environment
                                    ? `assistants.${task.environment}`
                                    : "assistants.inheritEnvironment",
                                )}
                              </span>
                              {task.timeout_seconds != null && (
                                <span>
                                  {t("assistants.taskBudget", {
                                    minutes: task.timeout_seconds / 60,
                                  })}
                                </span>
                              )}
                              <span>
                                {t("assistants.taskAttempts", {
                                  turns: task.authorized_turns ?? 1,
                                  recoveries: task.recovery_attempts ?? 0,
                                })}
                              </span>
                              {task.deadline_at && (
                                <span>
                                  {t("assistants.taskDeadline", {
                                    time: formatDateTimeShort(task.deadline_at),
                                  })}
                                </span>
                              )}
                            </div>
                            {task.notification ? (
                              <p className="text-12 text-theme-text-secondary">
                                {t(
                                  task.notification.accepted_transports.length
                                    ? "assistants.receiptAccepted"
                                    : "assistants.receiptRecorded",
                                  {
                                    state: t(
                                      `assistants.taskStates.${task.notification.status}`,
                                      {
                                        defaultValue: task.notification.status,
                                      },
                                    ),
                                    transports:
                                      task.notification.accepted_transports
                                        .map((transport) =>
                                          t(
                                            `assistants.transports.${transport}`,
                                            {
                                              defaultValue: transport,
                                            },
                                          ),
                                        )
                                        .join(", "),
                                  },
                                )}
                              </p>
                            ) : (
                              [
                                "completed",
                                "awaiting_review",
                                "accepted",
                                "needs_revision",
                                "failed",
                                "cancelled",
                              ].includes(task.state) && (
                                <p className="text-12 text-theme-text-secondary">
                                  {t("assistants.receiptUnknown")}
                                </p>
                              )
                            )}
                          </div>
                        </details>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            );
          })
        )}
        <details className="text-12 text-theme-text-secondary">
          <summary className="w-fit cursor-pointer rounded py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary">
            {t("assistants.taskHelp")}
          </summary>
          <div className="space-y-2">
            <p>{t("assistants.taskRoutingHint")}</p>
            <p>{t("assistants.taskControlsHint")}</p>
            <p className="text-12 text-theme-text-secondary">
              {t("assistants.taskBudgetHint")}
            </p>
            <p className="text-12 text-theme-text-secondary">
              {t("assistants.receiptHint")}
            </p>
          </div>
        </details>
      </div>
    </AssistantSurface>
  );
}
