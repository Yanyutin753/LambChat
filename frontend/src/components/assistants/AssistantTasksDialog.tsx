import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { assistantApi } from "../../services/api/assistant";
import { sessionApi } from "../../services/api/session";
import { translateApiError } from "../../utils/backendErrors";
import { formatDateTimeShort } from "../../utils/datetime";
import type { Assistant, AssistantTask } from "../../types/assistant";
import { Dialog } from "../common/Dialog";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { Button, FormField, Input, Textarea } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

const PAGE_SIZE = 10;

export function AssistantTasksDialog({
  assistant,
  canWrite,
  onClose,
}: {
  assistant: Assistant;
  canWrite: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
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
      setPage(1);
    });
  const review = (task: AssistantTask, accepted: boolean) =>
    perform(() =>
      assistantApi.reviewTask(assistant.id, task.id, {
        run_id: task.run_id,
        revision: task.review_revision,
        accepted,
      }),
    );

  return (
    <Dialog
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
            total={data?.total ?? 0}
            onChange={(next) => {
              setData(null);
              setPage(next);
            }}
          />
          <Button onClick={() => setRefresh((value) => value + 1)}>
            {t("common.refresh")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {(error || loadError) && (
          <ConfigPanelErrorCallout message={error || loadError} />
        )}
        {canWrite && assistant.status === "active" && (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <fieldset disabled={busy} className="space-y-3">
              <FormField
                label={t("assistants.taskDescription")}
                hint={t("assistants.taskHint")}
              >
                <Textarea
                  required
                  maxLength={20000}
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </FormField>
              <div className="flex flex-wrap items-end gap-3">
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
                  variant="primary"
                  loading={busy}
                  disabled={
                    !description.trim() ||
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
        <p className="text-12 text-theme-text-secondary">
          {t("assistants.taskRoutingHint")}
        </p>
        {!data && !loadError ? (
          <PanelLoadingState />
        ) : data?.tasks.length === 0 ? (
          <p className="text-14 text-theme-text-secondary">
            {t("assistants.noTasks")}
          </p>
        ) : (
          <ul className="divide-y divide-theme-border">
            {data?.tasks.map((task) => (
              <li key={task.id} className="space-y-2 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p
                    className="min-w-0 flex-1 line-clamp-3 break-words font-medium text-theme-text"
                    title={task.description}
                  >
                    {task.description}
                  </p>
                  <span className="text-12 text-theme-text-secondary">
                    {t(`assistants.taskStates.${task.state}`, {
                      defaultValue: task.state,
                    })}
                  </span>
                </div>
                <p className="break-all text-12 text-theme-text-secondary">
                  {t("assistants.taskReference")}{" "}
                  <code className="select-all">{task.id}</code>
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-12 text-theme-text-secondary">
                  {task.authorization && (
                    <span>
                      {t(`assistants.authorization.${task.authorization.kind}`)}
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
                          { defaultValue: task.notification.status },
                        ),
                        transports: task.notification.accepted_transports
                          .map((transport) =>
                            t(`assistants.transports.${transport}`, {
                              defaultValue: transport,
                            }),
                          )
                          .join(", "),
                      },
                    )}
                  </p>
                ) : (
                  [
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
                <div className="flex flex-wrap gap-2">
                  {task.session_id && (
                    <Button
                      onClick={() => {
                        onClose();
                        navigate(
                          `/chat/${encodeURIComponent(task.session_id!)}`,
                        );
                      }}
                    >
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
                            sessionApi.cancel(task.session_id!, task.run_id),
                          )
                        }
                      >
                        {t("assistants.stopTask")}
                      </Button>
                    )}
                  {canWrite &&
                    ["awaiting_review", "needs_revision", "accepted"].includes(
                      task.state,
                    ) && (
                      <>
                        <Button
                          disabled={busy || task.state === "accepted"}
                          onClick={() => void review(task, true)}
                        >
                          {t("assistants.acceptTask")}
                        </Button>
                        <Button
                          disabled={busy || task.state === "needs_revision"}
                          onClick={() => void review(task, false)}
                        >
                          {t("assistants.rejectTask")}
                        </Button>
                      </>
                    )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="text-12 text-theme-text-secondary">
          {t("assistants.taskControlsHint")}
        </p>
        <p className="text-12 text-theme-text-secondary">
          {t("assistants.taskBudgetHint")}
        </p>
        <p className="text-12 text-theme-text-secondary">
          {t("assistants.receiptHint")}
        </p>
      </div>
    </Dialog>
  );
}
