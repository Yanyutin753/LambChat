import { memo, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowDownToDot, ArrowUpFromDot, Bug, ListChecks, UserCheck, Workflow } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CollapsibleStatus } from "../../../common";
import { CollapsiblePill } from "../../../common";
import type { WorkflowPart } from "../../../../types";
import { workflowApi, type WorkflowRunResponse } from "../../../../plugins/workflow/api";
import { DetailSection } from "./DetailSection";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { openPersistentToolPanel, updatePersistentToolPanel } from "./persistentToolPanelState";

type WorkflowInterfaceSection = NonNullable<WorkflowPart["interface"]>;
type WorkflowNextAction = Record<string, unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function compactJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function truncate(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit - 3)}...` : value;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function pathValue(source: Record<string, unknown>, path: string): unknown {
  if (!path) return undefined;
  return path.split(".").reduce<unknown>((current, segment) => {
    if (!isRecord(current)) return undefined;
    if (segment.endsWith("[]")) {
      const items = current[segment.slice(0, -2)];
      if (!Array.isArray(items)) return undefined;
      for (const item of items) {
        const value = isRecord(item) ? item : undefined;
        if (value !== undefined) return value;
      }
      return undefined;
    }
    return current[segment];
  }, source);
}

function outputEntries(part: WorkflowPart): Array<{ key: string; value: string }> {
  const output = part.output;
  if (!isRecord(output)) return [];
  const contract = isRecord(part.output_contract) ? part.output_contract : null;
  const declaredPaths = Array.isArray(contract?.declared_field_paths)
    ? contract.declared_field_paths.filter((field): field is string => typeof field === "string")
    : [];
  const keys = [...new Set([...declaredPaths, "answer", ...Object.keys(output)])];
  return keys
    .map((key) => ({ key, value: pathValue(output, key) }))
    .filter((entry) => entry.value !== undefined && entry.value !== null && entry.value !== "")
    .slice(0, 8)
    .map((entry) => ({ key: entry.key, value: truncate(compactJson(entry.value), 180) }));
}

function nextActionEntries(part: WorkflowPart): Array<{ key: string; value: string }> {
  const action = part.next_action;
  if (!isRecord(action)) return [];
  return ["type", "tool", "field", "reason"]
    .map((key) => ({ key, value: action[key] }))
    .filter((entry) => entry.value !== undefined && entry.value !== null && entry.value !== "")
    .map((entry) => ({ key: entry.key, value: truncate(compactJson(entry.value), 120) }));
}

function nextActionRecord(part: WorkflowPart): WorkflowNextAction | null {
  return isRecord(part.next_action) ? part.next_action : null;
}

function nestedRecord(source: WorkflowNextAction | null, key: string): Record<string, unknown> | null {
  if (!source) return null;
  const value = source[key];
  return isRecord(value) ? value : null;
}

function workflowApprovalAction(part: WorkflowPart) {
  const action = nextActionRecord(part);
  const actionType = stringValue(action?.type);
  if (actionType !== "await_human_approval" && actionType !== "wait_for_human_approval") return null;
  const approval = nestedRecord(action, "approval");
  const pending = nestedRecord(action, "pending");
  const resume = nestedRecord(action, "resume");
  return {
    title: stringValue(approval?.title) || stringValue(approval?.node_id) || "Approval",
    assignee: stringValue(approval?.assignee),
    outputKey: stringValue(approval?.output_key),
    pendingPath: stringValue(pending?.path),
    resumeTool: stringValue(resume?.tool) || "workflow_resume",
    resumePath: stringValue(resume?.path),
  };
}

function workflowPartFromRun(run: WorkflowRunResponse): WorkflowPart {
  return {
    type: "workflow",
    plugin_id: "workflow",
    workflow_id: run.workflow_id,
    run_id: run.run_id ?? null,
    version_id: run.version_id ?? null,
    status: run.status,
    output: run.output,
    error: run.error ?? null,
    interface: run.interface ?? null,
    next_action: run.next_action ?? null,
    io_contract: run.io_contract ?? null,
    output_contract: run.output_contract ?? null,
  };
}

function workflowStatus(status?: string, error?: string | null): CollapsibleStatus {
  const normalized = (status || "").toLowerCase();
  if (normalized === "cancelled" || normalized === "canceled") return "cancelled";
  if (error || normalized === "failed" || normalized === "error") return "error";
  if (["running", "queued", "pending", "paused", "stub"].includes(normalized)) return "loading";
  if (["succeeded", "completed", "success"].includes(normalized)) return "success";
  return "idle";
}

function toolField(tool?: string, field?: string): string {
  if (!tool && !field) return "";
  if (!tool) return field || "";
  if (!field) return tool;
  return `${tool}.${field}`;
}

function InterfaceRows({ contract }: { contract?: WorkflowInterfaceSection | null }) {
  const { t } = useTranslation();
  if (!contract) return null;
  const entry = contract.entry;
  const exit = contract.exit;
  const debug = contract.debug;
  const rows = [
    {
      key: "entry",
      label: t("chat.message.workflowEntry", "Entry"),
      icon: <ArrowUpFromDot size={12} />,
      values: [
        toolField(entry?.tool, entry?.argument),
        toolField(entry?.schema_tool, entry?.schema_field),
      ],
    },
    {
      key: "exit",
      label: t("chat.message.workflowExit", "Exit"),
      icon: <ArrowDownToDot size={12} />,
      values: [
        entry || exit ? stringValue(exit?.field) || "output" : "",
        toolField(exit?.schema_tool, exit?.schema_field),
      ],
    },
    {
      key: "debug",
      label: t("chat.message.workflowDebug", "Debug"),
      icon: <Bug size={12} />,
      values: [toolField(debug?.tool, debug?.events_field), stringValue(debug?.run_id)],
    },
  ];

  return (
    <div className="space-y-1.5" data-testid="workflow-result-interface">
      {rows.map((row) => {
        const values = row.values.filter(Boolean);
        if (values.length === 0) return null;
        return (
          <div
            key={row.key}
            className="flex flex-wrap items-center gap-1.5 text-xs"
            data-testid={`workflow-result-interface-${row.key}`}
          >
            <span className="inline-flex items-center gap-1 text-theme-text-tertiary">
              {row.icon}
              {row.label}
            </span>
            {values.map((value) => (
              <code
                key={value}
                className="rounded-md bg-theme-bg px-1.5 py-0.5 font-mono text-[11px] text-theme-text-secondary ring-1 ring-theme-border"
              >
                {value}
              </code>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function HumanApprovalNextAction({
  action,
  canResume,
  comment,
  isResuming,
  resumeError,
  onCommentChange,
  onResume,
}: {
  action: NonNullable<ReturnType<typeof workflowApprovalAction>>;
  canResume?: boolean;
  comment?: string;
  isResuming?: boolean;
  resumeError?: string | null;
  onCommentChange?: (value: string) => void;
  onResume?: (approved: boolean) => void;
}) {
  const { t } = useTranslation();
  const rows = [
    {
      label: t("chat.message.workflowApprovalResumeTool", "Resume tool"),
      value: action.resumeTool,
    },
    {
      label: t("chat.message.workflowApprovalPending", "Pending inbox"),
      value: action.pendingPath,
    },
    {
      label: t("chat.message.workflowApprovalResumePath", "Resume API"),
      value: action.resumePath,
    },
  ].filter((row) => row.value);

  return (
    <div className="space-y-1.5 rounded-lg bg-theme-bg px-3 py-2 text-xs ring-1 ring-theme-border">
      <div className="flex flex-wrap items-center gap-1.5 text-theme-text-secondary">
        <span className="inline-flex items-center gap-1 font-medium text-theme-text">
          <UserCheck size={12} />
          {t("chat.message.workflowAwaitingApproval", "Awaiting approval")}
        </span>
        <span className="min-w-0 break-words">{action.title}</span>
        {action.assignee && (
          <code className="rounded-md bg-theme-bg-subtle px-1.5 py-0.5 font-mono text-[11px] text-theme-text-tertiary">
            {action.assignee}
          </code>
        )}
        {action.outputKey && (
          <code className="rounded-md bg-theme-bg-subtle px-1.5 py-0.5 font-mono text-[11px] text-theme-text-tertiary">
            {action.outputKey}
          </code>
        )}
      </div>
      {rows.length > 0 && (
        <div className="grid gap-1 sm:grid-cols-[minmax(0,9rem)_1fr]">
          {rows.map((row) => (
            <div key={row.label} className="contents">
              <span className="text-theme-text-tertiary">{row.label}</span>
              <code className="min-w-0 break-words rounded-md bg-theme-bg-subtle px-1.5 py-0.5 font-mono text-[11px] text-theme-text-secondary">
                {row.value}
              </code>
            </div>
          ))}
        </div>
      )}
      {canResume && onResume && onCommentChange && (
        <div className="flex flex-col gap-1.5 pt-1">
          <input
            type="text"
            value={comment ?? ""}
            onChange={(event) => onCommentChange(event.target.value)}
            placeholder={t("chat.message.workflowApprovalComment", "Approval comment")}
            className="h-8 min-w-0 rounded-md border border-theme-border bg-theme-bg-subtle px-2 text-xs text-theme-text outline-none transition-colors placeholder:text-theme-text-tertiary focus:border-theme-border-hover"
            disabled={isResuming}
          />
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => onResume(true)}
              disabled={isResuming}
              className="inline-flex h-7 items-center justify-center rounded-md bg-[var(--theme-primary)] px-2.5 text-xs font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isResuming
                ? t("chat.message.workflowApprovalResuming", "Resuming")
                : t("chat.message.workflowApprove", "Approve")}
            </button>
            <button
              type="button"
              onClick={() => onResume(false)}
              disabled={isResuming}
              className="inline-flex h-7 items-center justify-center rounded-md px-2.5 text-xs font-medium text-theme-text-secondary ring-1 ring-theme-border transition-colors hover:text-theme-text hover:ring-theme-border-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("chat.message.workflowReject", "Reject")}
            </button>
          </div>
          {resumeError && (
            <div className="flex items-start gap-1.5 text-[10px] text-red-600 dark:text-red-300">
              <AlertCircle size={11} className="mt-0.5 shrink-0" />
              <span className="min-w-0 break-words">{resumeError}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function WorkflowResumeResultPanel({ part }: { part: WorkflowPart }) {
  const { t } = useTranslation();
  const entries = outputEntries(part);
  const workflowId = stringValue(part.workflow_id);
  const runId = stringValue(part.run_id);
  const versionId = stringValue(part.version_id);
  const status = stringValue(part.status);
  const outputJson = isRecord(part.output) ? JSON.stringify(part.output, null, 2) : "";
  const canOpenRun = Boolean(workflowId && runId);
  const runHref = canOpenRun
    ? `/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`
    : "";

  return (
    <div className="space-y-3 p-4 sm:p-5 tool-panel-content">
      <div className="grid gap-2 text-xs sm:grid-cols-4">
        {workflowId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowId", "Workflow")}</div>
            <div className="truncate font-mono text-theme-text">{workflowId}</div>
          </div>
        )}
        {runId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowRunId", "Run")}</div>
            <div className="truncate font-mono text-theme-text">{runId}</div>
          </div>
        )}
        {versionId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowVersion", "Version")}</div>
            <div className="truncate font-mono text-theme-text">{versionId}</div>
          </div>
        )}
        {status && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowStatus", "Status")}</div>
            <div className="truncate font-mono text-theme-text">{status}</div>
          </div>
        )}
      </div>

      {entries.length > 0 && (
        <DetailSection title={t("chat.message.workflowOutput", "Output")} icon={<ArrowDownToDot size={12} />} defaultExpanded>
          <div className="space-y-1.5">
            {entries.map((entry) => (
              <div key={entry.key} className="grid gap-1 rounded-lg bg-theme-bg px-3 py-2 text-xs ring-1 ring-theme-border sm:grid-cols-[minmax(0,11rem)_1fr]">
                <code className="min-w-0 truncate text-theme-text-tertiary">{entry.key}</code>
                <span className="min-w-0 break-words text-theme-text-secondary">{entry.value}</span>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {outputJson && (
        <pre className="group/result relative max-h-72 min-w-0 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-theme-bg p-3 text-xs text-theme-text-tertiary ring-1 ring-theme-border">
          {outputJson}
          <ToolHoverCopyButton text={outputJson} position="result" />
        </pre>
      )}

      {canOpenRun && (
        <a
          href={runHref}
          className="inline-flex rounded-lg px-2.5 py-1.5 text-xs font-medium text-theme-text-secondary ring-1 ring-theme-border transition-colors hover:text-theme-text hover:ring-theme-border-hover"
        >
          {t("chat.message.workflowOpenRun", "Open run")}
        </a>
      )}
    </div>
  );
}

const WorkflowItem = memo(function WorkflowItem({ part }: { part: WorkflowPart }) {
  const { t } = useTranslation();
  const [localPart, setLocalPart] = useState<WorkflowPart | null>(null);
  const [approvalComment, setApprovalComment] = useState("");
  const [isResuming, setIsResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const displayPart = localPart ?? part;
  const entries = useMemo(() => outputEntries(displayPart), [displayPart]);
  const actionEntries = useMemo(() => nextActionEntries(displayPart), [displayPart]);
  const approvalAction = useMemo(() => workflowApprovalAction(displayPart), [displayPart]);
  const status = workflowStatus(displayPart.status, displayPart.error);
  const workflowId = stringValue(displayPart.workflow_id);
  const runId = stringValue(displayPart.run_id);
  const versionId = stringValue(displayPart.version_id);
  const hasRawOutput = isRecord(displayPart.output) && Object.keys(displayPart.output).length > 0;
  const canOpenRun = Boolean(workflowId && runId);
  const runHref = canOpenRun
    ? `/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`
    : "";
  const panelKey = `workflow:${workflowId || "unknown"}:${runId || "latest"}`;
  const contract = isRecord(displayPart.output_contract) ? displayPart.output_contract : null;
  const missingRequired = Array.isArray(contract?.missing_required)
    ? contract.missing_required.filter((field): field is string => typeof field === "string")
    : [];
  const typeMismatches = Array.isArray(contract?.type_mismatches)
    ? contract.type_mismatches
    : [];
  const outputJson = hasRawOutput ? JSON.stringify(displayPart.output, null, 2) : "";
  const label = `${t("chat.message.workflowRun", "Workflow run")}${workflowId ? ` ${workflowId}` : ""}`;
  const canResumeApproval = Boolean(approvalAction && workflowId && runId);
  const canExpand =
    entries.length > 0 ||
    actionEntries.length > 0 ||
    Boolean(displayPart.interface) ||
    Boolean(displayPart.error) ||
    hasRawOutput ||
    canResumeApproval;

  const handleResumeApproval = async (approved: boolean) => {
    if (!workflowId || !runId) return;
    setIsResuming(true);
    setResumeError(null);
    try {
      const run = await workflowApi.resumeRun(workflowId, runId, {
        approved,
        comment: approvalComment || null,
      });
      const nextPart = workflowPartFromRun(run);
      setLocalPart(nextPart);
      updatePersistentToolPanel(
        (panel) => ({
          ...panel,
          status: workflowStatus(nextPart.status, nextPart.error),
          subtitle: workflowId || undefined,
          children: <WorkflowResumeResultPanel part={nextPart} />,
        }),
        panelKey,
      );
    } catch (error) {
      setResumeError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsResuming(false);
    }
  };

  const compactContent = (
    <ToolInlineDetails>
      {approvalAction && (
        <HumanApprovalNextAction
          action={approvalAction}
          canResume={canResumeApproval}
          comment={approvalComment}
          isResuming={isResuming}
          resumeError={resumeError}
          onCommentChange={setApprovalComment}
          onResume={handleResumeApproval}
        />
      )}
      {entries.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {entries.slice(0, 4).map((entry) => (
            <span
              key={entry.key}
              className="inline-flex max-w-full items-center gap-1 rounded-md bg-theme-bg px-2 py-0.5 text-[10px] text-theme-text-secondary ring-1 ring-theme-border"
              title={`${entry.key}: ${entry.value}`}
            >
              <span className="font-mono text-theme-text-tertiary">{entry.key}</span>
              <span className="truncate">{entry.value}</span>
            </span>
          ))}
        </div>
      )}
      <InterfaceRows contract={displayPart.interface} />
      {actionEntries.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="inline-flex items-center gap-1 text-theme-text-tertiary">
            <ListChecks size={12} />
            {t("chat.message.workflowNextAction", "Next action")}
          </span>
          {actionEntries.slice(0, 2).map((entry) => (
            <code
              key={entry.key}
              className="rounded-md bg-theme-bg px-1.5 py-0.5 font-mono text-[11px] text-theme-text-secondary ring-1 ring-theme-border"
            >
              {entry.value}
            </code>
          ))}
        </div>
      )}
      {displayPart.error && (
        <div className="flex items-start gap-1.5 text-[10px] text-red-600 dark:text-red-300">
          <AlertCircle size={11} className="mt-0.5 shrink-0" />
          <span className="min-w-0 break-words">{displayPart.error}</span>
        </div>
      )}
    </ToolInlineDetails>
  );

  const detailContent = (
    <div className="space-y-3 p-4 sm:p-5 tool-panel-content">
      <div className="grid gap-2 text-xs sm:grid-cols-3">
        {workflowId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowId", "Workflow")}</div>
            <div className="truncate font-mono text-theme-text">{workflowId}</div>
          </div>
        )}
        {runId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowRunId", "Run")}</div>
            <div className="truncate font-mono text-theme-text">{runId}</div>
          </div>
        )}
        {versionId && (
          <div className="min-w-0 rounded-lg bg-theme-bg px-3 py-2 ring-1 ring-theme-border">
            <div className="text-theme-text-tertiary">{t("chat.message.workflowVersion", "Version")}</div>
            <div className="truncate font-mono text-theme-text">{versionId}</div>
          </div>
        )}
      </div>

      {displayPart.interface && (
        <DetailSection title={t("chat.message.workflowInterface", "Interface")} icon={<Workflow size={12} />} defaultExpanded>
          <InterfaceRows contract={displayPart.interface} />
        </DetailSection>
      )}

      {actionEntries.length > 0 && (
        <DetailSection title={t("chat.message.workflowNextAction", "Next action")} icon={<ListChecks size={12} />} defaultExpanded>
          <div className="space-y-1.5">
            {approvalAction && (
              <HumanApprovalNextAction
                action={approvalAction}
                canResume={canResumeApproval}
                comment={approvalComment}
                isResuming={isResuming}
                resumeError={resumeError}
                onCommentChange={setApprovalComment}
                onResume={handleResumeApproval}
              />
            )}
            {actionEntries.map((entry) => (
              <div key={entry.key} className="grid gap-1 rounded-lg bg-theme-bg px-3 py-2 text-xs ring-1 ring-theme-border sm:grid-cols-[minmax(0,9rem)_1fr]">
                <code className="min-w-0 truncate text-theme-text-tertiary">{entry.key}</code>
                <span className="min-w-0 break-words font-mono text-theme-text-secondary">{entry.value}</span>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {entries.length > 0 && (
        <DetailSection title={t("chat.message.workflowOutput", "Output")} icon={<ArrowDownToDot size={12} />} defaultExpanded>
          <div className="space-y-1.5">
            {entries.map((entry) => (
              <div key={entry.key} className="grid gap-1 rounded-lg bg-theme-bg px-3 py-2 text-xs ring-1 ring-theme-border sm:grid-cols-[minmax(0,11rem)_1fr]">
                <code className="min-w-0 truncate text-theme-text-tertiary">{entry.key}</code>
                <span className="min-w-0 break-words text-theme-text-secondary">{entry.value}</span>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {(missingRequired.length > 0 || typeMismatches.length > 0) && (
        <DetailSection title={t("chat.message.workflowContract", "Output contract")} icon={<AlertCircle size={12} />} defaultExpanded>
          <div className="space-y-2 text-xs text-theme-text-secondary">
            {missingRequired.length > 0 && (
              <div>
                <span className="text-theme-text-tertiary">{t("chat.message.workflowMissingOutputs", "Missing")}: </span>
                {missingRequired.join(", ")}
              </div>
            )}
            {typeMismatches.length > 0 && (
              <pre className="whitespace-pre-wrap break-words rounded-lg bg-theme-bg p-2 font-mono text-[11px] ring-1 ring-theme-border">
                {JSON.stringify(typeMismatches, null, 2)}
              </pre>
            )}
          </div>
        </DetailSection>
      )}

      {displayPart.error && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900/40">
          {displayPart.error}
        </div>
      )}

      {hasRawOutput && (
        <pre className="group/result relative max-h-72 min-w-0 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-theme-bg p-3 text-xs text-theme-text-tertiary ring-1 ring-theme-border">
          {outputJson}
          <ToolHoverCopyButton text={outputJson} position="result" />
        </pre>
      )}

      {canOpenRun && (
        <a
          href={runHref}
          className="inline-flex rounded-lg px-2.5 py-1.5 text-xs font-medium text-theme-text-secondary ring-1 ring-theme-border transition-colors hover:text-theme-text hover:ring-theme-border-hover"
        >
          {t("chat.message.workflowOpenRun", "Open run")}
        </a>
      )}
    </div>
  );

  useEffect(() => {
    updatePersistentToolPanel(
      (panel) => ({
        ...panel,
        status,
        subtitle: workflowId || undefined,
        children: detailContent,
      }),
      panelKey,
    );
  }, [detailContent, panelKey, status, workflowId]);

  return (
    <CollapsiblePill
      status={status}
      icon={<Workflow size={12} className="shrink-0 opacity-60" />}
      label={label}
      suffix={
        displayPart.status ? (
          <span className="max-w-[96px] truncate rounded-md bg-white/30 px-1.5 py-0.5 text-[9px] font-medium dark:bg-black/20">
            {displayPart.status}
          </span>
        ) : undefined
      }
      variant="tool"
      expandable={canExpand}
      formatLabel={false}
      onPanelOpen={() => {
        if (!canExpand) return;
        openPersistentToolPanel({
          title: t("chat.message.workflowRun", "Workflow run"),
          panelKey,
          icon: <Workflow size={16} />,
          status,
          subtitle: workflowId || undefined,
          children: detailContent,
        });
      }}
    >
      {canExpand ? compactContent : undefined}
    </CollapsiblePill>
  );
});

export { WorkflowItem };
