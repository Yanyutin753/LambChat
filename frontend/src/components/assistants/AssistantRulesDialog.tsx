import { Plus } from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { EmptyState } from "../common/EmptyState";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { assistantApi } from "../../services/api/assistant";
import { scheduledTaskApi } from "../../services/api/scheduledTask";
import type {
  Assistant,
  AssistantRule,
  AssistantRuleCreate,
  AssistantRuleMode,
} from "../../types/assistant";
import { AssistantSurface } from "./AssistantSurface";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import {
  Button,
  FormField,
  Input,
  Select,
  Textarea,
  type SelectOption,
} from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { loadAssistantChoices } from "./assistantChoices";

const initial: AssistantRuleCreate = {
  name: "",
  instructions: "",
  mode: "observe",
  interval_seconds: 3600,
  timeout_seconds: 300,
  max_wakeups: 10,
};
const PAGE_SIZE = 10;

export function AssistantRulesDialog({
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
  const returnFocus = useRef(false);
  useEffect(() => {
    if (creating) formRef.current?.querySelector("input")?.focus();
    else if (returnFocus.current) {
      document.getElementById(`${formId}-toggle`)?.focus();
      returnFocus.current = false;
    }
  }, [creating, formId]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{
    rules: AssistantRule[];
    total: number;
  } | null>(null);
  const [draft, setDraft] = useState<AssistantRuleCreate>(initial);
  const [editing, setEditing] = useState<AssistantRule | null>(null);
  const [eventTrigger, setEventTrigger] = useState(false);
  const [tasks, setTasks] = useState<SelectOption[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const modes = (["off", "observe", "auto"] as const).map((value) => ({
    value,
    label: t(`assistants.ruleModes.${value}`),
  }));
  useEffect(() => {
    let active = true;
    setError("");
    void assistantApi
      .rules(assistant.id, (page - 1) * PAGE_SIZE, PAGE_SIZE)
      .then((value) => {
        if (active) {
          setData(value);
          setTotal(value.total);
        }
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      });
    return () => {
      active = false;
    };
  }, [assistant.id, page, refresh, t]);
  useEffect(() => {
    if (!eventTrigger) return;
    let active = true;
    setTasks(null);
    void loadAssistantChoices(
      async (skip) => {
        const result = await assistantApi.tasks(assistant.id, skip, 100);
        return {
          items: result.tasks.map((task) => ({
            id: task.id,
            name: task.description,
          })),
          total: result.total,
        };
      },
      () => active,
    )
      .then((items) => {
        if (active) setTasks(items);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      });
    return () => {
      active = false;
    };
  }, [assistant.id, eventTrigger, refresh, t]);
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
  const save = () =>
    perform(async () => {
      const payload = {
        ...draft,
        event_task_id: eventTrigger ? draft.event_task_id : null,
      };
      if (editing) {
        const { name, instructions, interval_seconds, ...policy } = payload;
        await scheduledTaskApi.update(editing.id, {
          name,
          trigger_type: "interval",
          trigger_config: { seconds: interval_seconds },
          enabled: policy.mode !== "off",
          input_payload: {
            message: instructions,
            assistant_rule: { assistant_id: assistant.id, ...policy },
          },
        });
        if (policy.mode !== "off" && editing.status === "paused")
          await scheduledTaskApi.resume(editing.id);
      } else await assistantApi.createRule(assistant.id, payload);
      setEditing(null);
      setDraft(initial);
      setEventTrigger(false);
      setCreating(false);
    });
  const setMode = (rule: AssistantRule, mode: AssistantRuleMode) =>
    perform(async () => {
      await scheduledTaskApi.update(rule.id, {
        input_payload: {
          ...rule.input_payload,
          assistant_rule: { ...rule.input_payload.assistant_rule, mode },
        },
        enabled: mode !== "off",
      });
      if (mode !== "off" && rule.status === "paused")
        await scheduledTaskApi.resume(rule.id);
    });
  const createAction = canWrite && !creating && (
    <Button
      id={`${formId}-toggle`}
      variant="primary"
      leftIcon={<Plus size={16} />}
      aria-expanded={creating}
      aria-controls={creating ? formId : undefined}
      disabled={busy}
      onClick={() => {
        returnFocus.current = true;
        setError("");
        setCreating(true);
      }}
    >
      {t("assistants.createRule")}
    </Button>
  );
  return (
    <AssistantSurface
      embedded={embedded}
      open
      onClose={onClose}
      title={t("assistants.rulesTitle", { name: assistant.name })}
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
        {error && <ConfigPanelErrorCallout message={error} />}
        {embedded ? (
          <PanelHeader
            className="!px-0"
            title={t("assistants.rules")}
            actions={createAction}
          />
        ) : (
          createAction
        )}
        <p className="text-12 leading-relaxed text-theme-text-secondary">
          {t("assistants.rulesHint")}
        </p>
        {canWrite && creating && (
          <form
            id={formId}
            ref={formRef}
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <fieldset disabled={busy} className="space-y-3">
              <FormField label={t("assistants.ruleName")}>
                <Input
                  required
                  maxLength={80}
                  value={draft.name}
                  onChange={(event) =>
                    setDraft({ ...draft, name: event.target.value })
                  }
                />
              </FormField>
              <FormField label={t("assistants.ruleInstructions")}>
                <Textarea
                  required
                  rows={3}
                  maxLength={18000}
                  value={draft.instructions}
                  onChange={(event) =>
                    setDraft({ ...draft, instructions: event.target.value })
                  }
                />
              </FormField>
              <div className="assistant-rule-fields grid gap-3">
                <FormField label={t("assistants.ruleMode")}>
                  <Select
                    ariaLabel={t("assistants.ruleMode")}
                    options={modes}
                    value={draft.mode}
                    onChange={(mode) =>
                      setDraft({ ...draft, mode: mode as AssistantRuleMode })
                    }
                  />
                </FormField>
                <FormField label={t("assistants.ruleTrigger")}>
                  <Select
                    ariaLabel={t("assistants.ruleTrigger")}
                    value={eventTrigger ? "event" : "timer"}
                    options={[
                      { value: "timer", label: t("assistants.ruleTimer") },
                      { value: "event", label: t("assistants.ruleEvent") },
                    ]}
                    onChange={(value) => setEventTrigger(value === "event")}
                  />
                </FormField>
                {eventTrigger && (
                  <FormField label={t("assistants.ruleSourceTask")}>
                    <Select
                      ariaLabel={t("assistants.ruleSourceTask")}
                      disabled={!tasks}
                      value={draft.event_task_id ?? ""}
                      options={[
                        { value: "", label: t("assistants.ruleChooseTask") },
                        ...(tasks ?? []),
                      ]}
                      onChange={(value) =>
                        setDraft({ ...draft, event_task_id: value })
                      }
                    />
                  </FormField>
                )}
                <FormField label={t("assistants.ruleInterval")}>
                  <Input
                    type="number"
                    required
                    min={1}
                    max={525600}
                    value={draft.interval_seconds / 60}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        interval_seconds: Number(event.target.value) * 60,
                      })
                    }
                  />
                </FormField>
                <FormField label={t("assistants.taskTimeout")}>
                  <Input
                    type="number"
                    required
                    min={0.5}
                    max={60}
                    step={0.5}
                    value={draft.timeout_seconds / 60}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        timeout_seconds: Number(event.target.value) * 60,
                      })
                    }
                  />
                </FormField>
                <FormField label={t("assistants.ruleWakeupLimit")}>
                  <Input
                    type="number"
                    required
                    min={1}
                    max={100}
                    value={draft.max_wakeups}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        max_wakeups: Number(event.target.value),
                      })
                    }
                  />
                </FormField>
              </div>
              <Button
                type="submit"
                variant="primary"
                loading={busy}
                disabled={
                  !draft.name.trim() ||
                  !draft.instructions.trim() ||
                  (eventTrigger && !draft.event_task_id)
                }
              >
                {t(editing ? "common.save" : "assistants.createRule")}
              </Button>
              <Button
                onClick={() => {
                  setEditing(null);
                  setDraft(initial);
                  setEventTrigger(false);
                  setCreating(false);
                  setError("");
                }}
              >
                {t("common.cancel")}
              </Button>
            </fieldset>
          </form>
        )}
        {creating ? null : !data && !error ? (
          <PanelLoadingState />
        ) : data?.rules.length === 0 ? (
          <EmptyState
            illustration="panel-schedule"
            title={t("assistants.noRules")}
          />
        ) : (
          <ul className="divide-y divide-theme-border">
            {data?.rules.map((rule) => (
              <li key={rule.id} className="space-y-2 py-4">
                <p className="break-words font-medium">{rule.name}</p>
                <p className="text-12 text-theme-text-secondary">
                  {t("assistants.ruleBudget", {
                    used: rule.assistant_rule_wakeups ?? 0,
                    limit: rule.input_payload.assistant_rule.max_wakeups,
                    minutes:
                      rule.input_payload.assistant_rule.timeout_seconds / 60,
                  })}
                </p>
                {rule.assistant_rule_last_claim && (
                  <p className="text-12 text-theme-text-secondary">
                    {t(
                      `assistants.ruleClaimStates.${rule.assistant_rule_last_claim.status}`,
                      { defaultValue: rule.assistant_rule_last_claim.status },
                    )}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  {canWrite ? (
                    <>
                      <Select
                        ariaLabel={t("assistants.ruleModeFor", {
                          name: rule.name,
                        })}
                        disabled={busy}
                        value={
                          rule.enabled && rule.status === "active"
                            ? rule.input_payload.assistant_rule.mode
                            : "off"
                        }
                        options={modes}
                        onChange={(mode) =>
                          void setMode(rule, mode as AssistantRuleMode)
                        }
                      />
                      <Button
                        disabled={busy}
                        onClick={() => {
                          returnFocus.current = true;
                          setError("");
                          setCreating(true);
                          setEditing(rule);
                          setDraft({
                            name: rule.name,
                            instructions: rule.input_payload.message,
                            interval_seconds:
                              rule.trigger_config.seconds ?? 3600,
                            ...rule.input_payload.assistant_rule,
                          });
                          setEventTrigger(
                            Boolean(
                              rule.input_payload.assistant_rule.event_task_id,
                            ),
                          );
                        }}
                      >
                        {t("assistants.edit")}
                      </Button>
                    </>
                  ) : (
                    <span className="text-12 text-theme-text-secondary">
                      {t(
                        `assistants.ruleModes.${
                          rule.enabled && rule.status === "active"
                            ? rule.input_payload.assistant_rule.mode
                            : "off"
                        }`,
                      )}
                    </span>
                  )}
                  <Button
                    onClick={() => {
                      onClose();
                      navigate(
                        `/scheduled-tasks/${encodeURIComponent(rule.id)}`,
                      );
                    }}
                  >
                    {t("assistants.ruleHistory")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </AssistantSurface>
  );
}
