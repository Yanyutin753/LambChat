import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowLeft,
  AlertTriangle,
  Bot,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  ListChecks,
  MessageSquare,
  Workflow,
} from "lucide-react";
import { PanelHeader } from "../../common/PanelHeader";
import { Pagination } from "../../common/Pagination";
import { TaskSessionListSkeleton } from "../../skeletons";
import { scheduledTaskApi } from "../../../services/api/scheduledTask";
import { agentApi } from "../../../services/api/agent";
import type { TaskRun, TaskSession } from "../../../types/scheduledTask";
import type { AgentInfo } from "../../../types/agent";
import { formatDateTimeShort } from "../../../utils/datetime";
import {
  workflowCallableInterfaceLabels,
  workflowOutputPathValue,
  workflowSchemaFieldDescriptors,
} from "../../../plugins/workflow/contractUtils";
import { RunStatusBadge } from "./Badges";

// ── Task Session List (drill-down) ─────────────────

const WORKFLOW_RUN_PREVIEW_LIMIT = 220;
const WORKFLOW_RUN_HISTORY_LIMIT = 5;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function workflowResultFromRun(run: TaskRun): Record<string, unknown> | null {
  const output = asRecord(run.output_result);
  if (!output) return null;
  const direct = asRecord(output.workflow_result);
  if (direct?.plugin_id === "workflow") return direct;
  const pluginResults = asRecord(output.plugin_results);
  const workflowResult = asRecord(pluginResults?.workflow);
  return workflowResult?.plugin_id === "workflow" ? workflowResult : null;
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function compactJson(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isWorkflowResultValuePresent(value: unknown): boolean {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function workflowResultOutputSchema(result: Record<string, unknown>): Record<string, unknown> | null {
  const ioContract = asRecord(result.io_contract);
  const contractSchema = asRecord(ioContract?.output_schema);
  if (contractSchema) return contractSchema;
  return asRecord(result.output_schema);
}

function workflowResultOutputFieldPaths(result: Record<string, unknown>): string[] {
  const descriptors = workflowSchemaFieldDescriptors(
    workflowResultOutputSchema(result),
    { nested: true, limit: 4 },
  );
  return descriptors.map((descriptor) => descriptor.field);
}

function workflowResultPreview(result: Record<string, unknown>): string {
  const contractFailure = workflowOutputContractFailureSummary(result);
  if (contractFailure) {
    if (contractFailure.length <= WORKFLOW_RUN_PREVIEW_LIMIT) return contractFailure;
    return `${contractFailure.slice(0, WORKFLOW_RUN_PREVIEW_LIMIT)}...`;
  }
  const output = asRecord(result.output);
  for (const field of workflowResultOutputFieldPaths(result)) {
    const value = workflowOutputPathValue(output ?? {}, field);
    if (isWorkflowResultValuePresent(value)) {
      const preview = compactJson(value);
      if (preview.length <= WORKFLOW_RUN_PREVIEW_LIMIT) return preview;
      return `${preview.slice(0, WORKFLOW_RUN_PREVIEW_LIMIT)}...`;
    }
  }
  const answer = workflowOutputPathValue(output ?? {}, "answer");
  const raw = isWorkflowResultValuePresent(answer)
    ? compactJson(answer)
    : compactJson(output) || stringField(result.error);
  if (raw.length <= WORKFLOW_RUN_PREVIEW_LIMIT) return raw;
  return `${raw.slice(0, WORKFLOW_RUN_PREVIEW_LIMIT)}...`;
}

function workflowResultOutputEntries(
  result: Record<string, unknown>,
): Array<{ key: string; value: string }> {
  const output = asRecord(result.output);
  if (!output) return [];
  const schemaPaths = workflowResultOutputFieldPaths(result);
  const keys = [
    ...schemaPaths,
    "answer",
    ...Object.keys(output).filter(
      (key) => key !== "answer" && !schemaPaths.includes(key),
    ),
  ];
  return Array.from(new Set(keys))
    .filter((key) => isWorkflowResultValuePresent(workflowOutputPathValue(output, key)))
    .slice(0, 4)
    .map((key) => ({
      key,
      value: compactJson(workflowOutputPathValue(output, key)),
    }))
    .filter((entry) => entry.value !== "");
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.length > 0,
      )
    : [];
}

function workflowOutputContractIssueParts(result: Record<string, unknown>): string[] {
  const contract = asRecord(result.output_contract);
  if (!contract) return [];
  const missing = stringList(contract.missing_required);
  const mismatches = Array.isArray(contract.type_mismatches)
    ? contract.type_mismatches
        .map((item) => asRecord(item))
        .filter((item): item is Record<string, unknown> => item !== null)
        .map((item) => {
          const field = stringField(item.field);
          const expected = compactJson(item.expected);
          const actual = stringField(item.actual);
          return field
            ? `${field}: ${actual || "unknown"} -> ${expected || "declared"}`
            : "";
        })
        .filter(Boolean)
    : [];
  return [
    missing.length > 0 ? `Missing: ${missing.join(", ")}` : "",
    mismatches.length > 0 ? `Type: ${mismatches.join(", ")}` : "",
  ].filter(Boolean);
}

function workflowOutputContractFailureSummary(result: Record<string, unknown>): string | null {
  const contract = asRecord(result.output_contract);
  if (!contract || contract.valid !== false) return null;
  const issueParts = workflowOutputContractIssueParts(result);
  return issueParts.length > 0
    ? `Workflow output contract failed (${issueParts.join(" | ")})`
    : "Workflow output contract failed";
}

function workflowOutputContractStatus(result: Record<string, unknown>): {
  valid: boolean;
  label: string;
  title: string;
} | null {
  const contract = asRecord(result.output_contract);
  if (!contract || typeof contract.valid !== "boolean") return null;
  const issueParts = workflowOutputContractIssueParts(result);
  return {
    valid: contract.valid,
    label: contract.valid ? "Contract ok" : "Contract issue",
    title:
      issueParts.length > 0
        ? issueParts.join(" | ")
        : "Output contract satisfied",
  };
}

function workflowNextActionEntries(
  result: Record<string, unknown>,
): Array<{ key: string; value: string }> {
  const action = asRecord(result.next_action);
  if (!action) return [];
  const approval = asRecord(action.approval);
  const pending = asRecord(action.pending);
  const resume = asRecord(action.resume);
  return [
    { key: "type", value: action.type },
    { key: "tool", value: action.tool },
    { key: "field", value: action.field },
    { key: "reason", value: action.reason },
    { key: "approval", value: approval?.title || approval?.node_id },
    { key: "resume", value: resume?.tool },
    { key: "resume_path", value: resume?.path },
    { key: "pending", value: pending?.path },
  ]
    .filter((entry) => isWorkflowResultValuePresent(entry.value))
    .map((entry) => ({ key: entry.key, value: compactJson(entry.value) }))
    .filter((entry) => entry.value !== "");
}

function workflowResultInterfaceEntries(
  result: Record<string, unknown>,
): Array<{ key: string; value: string; title: string }> {
  const interfacePayload = asRecord(result.interface);
  if (!interfacePayload) return [];
  const labels = workflowCallableInterfaceLabels(interfacePayload);
  return [
    {
      key: "Entry",
      value: labels.entry,
      title: labels.entrySchema,
    },
    {
      key: "Exit",
      value: labels.exit,
      title: labels.exitSchema,
    },
  ].filter((entry) => entry.value);
}

function workflowRunsFromRuns(runs: readonly TaskRun[]): TaskRun[] {
  return runs.filter((run) => workflowResultFromRun(run) !== null);
}

export function TaskSessionList({
  taskId,
  taskName,
  onBack,
}: {
  taskId: string;
  taskName: string;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TaskSession[]>([]);
  const [workflowRuns, setWorkflowRuns] = useState<TaskRun[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const limit = 20;

  // Fetch agents once for name resolution
  useEffect(() => {
    agentApi
      .list()
      .then((res) => setAgents(res.agents))
      .catch(() => {});
  }, []);

  const fetchSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      const [sessionResponse, runResponse] = await Promise.all([
        scheduledTaskApi.getSessions(taskId, skip, limit),
        scheduledTaskApi.getRuns(taskId, WORKFLOW_RUN_HISTORY_LIMIT, 0),
      ]);
      setSessions(sessionResponse.items);
      setTotal(sessionResponse.total);
      setWorkflowRuns(workflowRunsFromRuns(runResponse.items));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [taskId, skip, t]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleSessionClick = (sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  };

  // Show skeleton during initial data loading — consistent with other panels
  if (isLoading && sessions.length === 0 && workflowRuns.length === 0) {
    return <TaskSessionListSkeleton />;
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Header with back button */}
      <PanelHeader
        title={taskName}
        subtitle={t("scheduledTask.sessionsSubtitle")}
        icon={
          <MessageSquare
            size={20}
            className="text-stone-600 dark:text-stone-400"
          />
        }
        actions={
          <button
            onClick={onBack}
            className="scheduled-task-button scheduled-task-button--secondary"
          >
            <ArrowLeft size={16} />
            {t("scheduledTask.backToTasks")}
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-3 sm:p-6">
        {workflowRuns.length > 0 && (
          <div className="mb-5">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--theme-text)]">
              <Workflow size={16} className="text-[var(--theme-primary)]" />
              <span>
                {t("scheduledTask.workflowResults", "Workflow results")}
              </span>
            </div>
            <div className="scheduled-task-list">
              {workflowRuns.map((run) => {
                const workflowResult = workflowResultFromRun(run);
                if (!workflowResult) return null;
                const workflowId = stringField(workflowResult.workflow_id);
                const workflowRunId = stringField(workflowResult.run_id);
                const preview = workflowResultPreview(workflowResult);
                const outputEntries = workflowResultOutputEntries(workflowResult);
                const outputContract = workflowOutputContractStatus(workflowResult);
                const nextActionEntries = workflowNextActionEntries(workflowResult);
                const interfaceEntries = workflowResultInterfaceEntries(workflowResult);
                const canOpenWorkflowRun = Boolean(workflowId && workflowRunId);

                return (
                  <button
                    key={run.id}
                    type="button"
                    disabled={!canOpenWorkflowRun}
                    onClick={() => {
                      if (!canOpenWorkflowRun) return;
                      navigate(
                        `/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(workflowRunId)}`,
                      );
                    }}
                    className="glass-card scheduled-task-session-card w-full text-left disabled:cursor-default"
                  >
                    <div className="scheduled-task-session-card__indicator scheduled-task-session-card__indicator--active">
                      <Workflow size={16} />
                    </div>
                    <div className="scheduled-task-session-card__body">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <p className="scheduled-task-session-card__title">
                          {workflowId || t("scheduledTask.workflow", "Workflow")}
                        </p>
                        <RunStatusBadge status={run.status} />
                        {outputContract && (
                          <span
                            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] ${
                              outputContract.valid
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                : "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                            }`}
                            title={outputContract.title}
                          >
                            {outputContract.valid ? (
                              <CheckCircle2 size={11} />
                            ) : (
                              <AlertTriangle size={11} />
                            )}
                            <span>{outputContract.label}</span>
                          </span>
                        )}
                      </div>
                      {preview && (
                        <p className="line-clamp-2 text-xs leading-relaxed text-[var(--theme-text-secondary)]">
                          {preview}
                        </p>
                      )}
                      {outputEntries.length > 0 && (
                        <div className="flex min-w-0 flex-wrap gap-1.5">
                          {outputEntries.map((entry) => (
                            <span
                              key={`${run.id}-${entry.key}`}
                              className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-1.5 py-0.5 text-[11px] text-[var(--theme-text-secondary)]"
                              title={`${entry.key}: ${entry.value}`}
                            >
                              <span className="shrink-0 font-medium text-[var(--theme-text)]">{entry.key}</span>
                              <span className="truncate">{entry.value}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {interfaceEntries.length > 0 && (
                        <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-[var(--theme-text-secondary)]">
                          <span className="inline-flex shrink-0 items-center gap-1 text-[var(--theme-text-tertiary)]">
                            <Workflow size={11} />
                            {t("scheduledTask.workflowInterface", "Interface")}
                          </span>
                          {interfaceEntries.map((entry) => (
                            <span
                              key={`${run.id}-interface-${entry.key}`}
                              className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-1.5 py-0.5"
                              title={entry.title}
                            >
                              <span className="shrink-0 font-medium text-[var(--theme-text)]">{entry.key}</span>
                              <span className="truncate font-mono">{entry.value}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {nextActionEntries.length > 0 && (
                        <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[11px] text-[var(--theme-text-secondary)]">
                          <span className="inline-flex shrink-0 items-center gap-1 text-[var(--theme-text-tertiary)]">
                            <ListChecks size={11} />
                            {t("scheduledTask.workflowNextAction", "Next action")}
                          </span>
                          {nextActionEntries.map((entry) => (
                            <span
                              key={`${run.id}-next-action-${entry.key}`}
                              className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-1.5 py-0.5"
                              title={`${entry.key}: ${entry.value}`}
                            >
                              <span className="shrink-0 font-mono text-[var(--theme-text-tertiary)]">{entry.key}</span>
                              <span className="truncate font-mono">{entry.value}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="scheduled-task-session-card__meta">
                        {run.started_at && (
                          <span className="inline-flex items-center gap-1">
                            <CalendarClock size={10} />
                            {formatDateTimeShort(run.started_at)}
                          </span>
                        )}
                        {workflowRunId && (
                          <span className="truncate">{workflowRunId}</span>
                        )}
                      </div>
                    </div>
                    {canOpenWorkflowRun && (
                      <div className="scheduled-task-session-card__trail">
                        <ExternalLink
                          size={16}
                          className="text-stone-300 dark:text-stone-600"
                        />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Session List */}
        {sessions.length === 0 ? (
          <div className="scheduled-task-empty-state">
            <div className="scheduled-task-empty-state__icon">
              <MessageSquare size={32} />
            </div>
            <p className="scheduled-task-empty-state__title">
              {t("scheduledTask.noSessions")}
            </p>
            <p className="scheduled-task-empty-state__body">
              {t("scheduledTask.noSessionsDesc")}
            </p>
          </div>
        ) : (
          <div className="scheduled-task-list">
            {sessions.map((session) => {
              const agentName =
                agents.find((a) => a.id === session.agent_id)?.name ??
                session.agent_id;

              return (
                <button
                  key={session.id}
                  onClick={() => handleSessionClick(session.id)}
                  className="glass-card scheduled-task-session-card w-full text-left"
                >
                  {/* Left indicator icon */}
                  <div
                    className={`scheduled-task-session-card__indicator ${
                      session.is_active
                        ? "scheduled-task-session-card__indicator--active"
                        : ""
                    }`}
                  >
                    <MessageSquare size={16} />
                  </div>

                  {/* Body */}
                  <div className="scheduled-task-session-card__body">
                    <p className="scheduled-task-session-card__title">
                      {session.name || t("scheduledTask.untitledSession")}
                    </p>
                    <div className="scheduled-task-session-card__meta">
                      {agentName && (
                        <>
                          <span className="inline-flex items-center gap-1">
                            <Bot size={10} />
                            {t(agentName)}
                          </span>
                          {session.created_at && (
                            <>
                              <span className="scheduled-task-session-card__meta-separator">
                                ·
                              </span>
                              <span>
                                {formatDateTimeShort(session.created_at)}
                              </span>
                            </>
                          )}
                        </>
                      )}
                      {!agentName && session.created_at && (
                        <span>{formatDateTimeShort(session.created_at)}</span>
                      )}
                    </div>
                  </div>

                  {/* Trail: unread badge + chevron */}
                  <div className="scheduled-task-session-card__trail">
                    {session.unread_count > 0 && (
                      <span className="scheduled-task-session-card__unread">
                        {session.unread_count > 99
                          ? "99+"
                          : session.unread_count}
                      </span>
                    )}
                    <ChevronRight
                      size={16}
                      className="text-stone-300 dark:text-stone-600"
                    />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="glass-divider bg-transparent px-4 py-4 sm:px-6">
          <Pagination
            page={Math.floor(skip / limit) + 1}
            pageSize={limit}
            total={total}
            onChange={(page) => setSkip((page - 1) * limit)}
          />
        </div>
      )}
    </div>
  );
}
