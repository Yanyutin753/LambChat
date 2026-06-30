import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { GitBranch, GitCommit } from "lucide-react";
import { Select } from "../../components/common";
import { workflowApi } from "./api";
import type {
  WorkflowIoContractResponse,
  WorkflowSummary,
  WorkflowVersionSummary,
} from "./api";
import {
  sampleWorkflowInputFromSchema,
  workflowCallableInterfaceLabels,
  workflowInputDraftMessage,
  workflowInputDraftStatus,
  workflowSchemaFieldLabels,
} from "./contractUtils";
import type { WorkflowInputDraftStatus } from "./contractUtils";

interface WorkflowSelectOptionProps {
  option?: { key: string };
  value: unknown;
  pluginValues?: Record<string, unknown>;
  disabled?: boolean;
  inactive?: boolean;
  triggerClassName?: string;
  placeholder?: string;
  onChange: (value: unknown) => void;
  onPluginValueChange?: (key: string, value: unknown) => void;
}

const WORKFLOW_ID_KEY_BY_VERSION_KEY: Record<string, string> = {
  DEFAULT_WORKFLOW_VERSION_ID: "DEFAULT_WORKFLOW_ID",
  SELECTED_WORKFLOW_VERSION_ID: "SELECTED_WORKFLOW_ID",
  WORKFLOW_VERSION_ID: "WORKFLOW_ID",
};

const WORKFLOW_ID_KEY_BY_INPUT_KEY: Record<string, string> = {
  SELECTED_WORKFLOW_INPUT_JSON: "SELECTED_WORKFLOW_ID",
  WORKFLOW_INPUT_JSON: "WORKFLOW_ID",
};

const VERSION_KEY_BY_INPUT_KEY: Record<string, string> = {
  SELECTED_WORKFLOW_INPUT_JSON: "SELECTED_WORKFLOW_VERSION_ID",
  WORKFLOW_INPUT_JSON: "WORKFLOW_VERSION_ID",
};

const VERSION_KEY_BY_WORKFLOW_ID_KEY: Record<string, string> = Object.fromEntries(
  Object.entries(WORKFLOW_ID_KEY_BY_VERSION_KEY).map(([versionKey, workflowKey]) => [
    workflowKey,
    versionKey,
  ]),
);

function workflowLabel(label: string, status?: WorkflowSummary["status"]): ReactNode {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <GitBranch size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{label}</span>
      {status && (
        <span className="shrink-0 rounded bg-stone-100 px-1 py-0.5 text-[10px] uppercase tracking-normal text-stone-500 dark:bg-stone-800 dark:text-stone-400">
          {status}
        </span>
      )}
    </span>
  );
}

function versionLabel(label: string): ReactNode {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <GitCommit size={14} className="shrink-0 opacity-70" />
      <span className="truncate">{label}</span>
    </span>
  );
}

function workflowIdForVersionOption(
  optionKey: string | undefined,
  pluginValues: Record<string, unknown> | undefined,
): string {
  const values = pluginValues ?? {};
  const preferredKey = optionKey ? WORKFLOW_ID_KEY_BY_VERSION_KEY[optionKey] : undefined;
  const candidates = [
    preferredKey,
    "WORKFLOW_ID",
    "SELECTED_WORKFLOW_ID",
    "DEFAULT_WORKFLOW_ID",
  ].filter(Boolean) as string[];
  for (const key of candidates) {
    const value = values[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function versionIdForWorkflowOption(
  optionKey: string | undefined,
  pluginValues: Record<string, unknown> | undefined,
): string | null {
  const versionKey = optionKey ? VERSION_KEY_BY_WORKFLOW_ID_KEY[optionKey] : undefined;
  const value = versionKey ? pluginValues?.[versionKey] : undefined;
  return typeof value === "string" && value ? value : null;
}

function sampleInputFromContract(contract: WorkflowIoContractResponse | null, fallbackText: string): Record<string, unknown> {
  return sampleWorkflowInputFromSchema(contract?.input_schema, fallbackText);
}

function inputDraftError(
  draft: string,
  contract: WorkflowIoContractResponse | null,
): WorkflowInputDraftStatus | null {
  return workflowInputDraftStatus(draft, contract?.input_schema);
}

function workflowInputOptionWorkflowId(
  optionKey: string | undefined,
  pluginValues: Record<string, unknown> | undefined,
): string {
  const workflowKey = optionKey ? WORKFLOW_ID_KEY_BY_INPUT_KEY[optionKey] : undefined;
  const value = workflowKey ? pluginValues?.[workflowKey] : pluginValues?.WORKFLOW_ID;
  return typeof value === "string" ? value : "";
}

function workflowInputOptionVersionId(
  optionKey: string | undefined,
  pluginValues: Record<string, unknown> | undefined,
): string | null {
  const versionKey = optionKey ? VERSION_KEY_BY_INPUT_KEY[optionKey] : undefined;
  const value = versionKey ? pluginValues?.[versionKey] : pluginValues?.WORKFLOW_VERSION_ID;
  return typeof value === "string" && value ? value : null;
}

export function WorkflowPluginSelectOption({
  option,
  value,
  pluginValues,
  disabled,
  inactive,
  triggerClassName,
  placeholder,
  onChange,
  onPluginValueChange,
}: WorkflowSelectOptionProps) {
  const { t } = useTranslation();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null);
  const stringValue = typeof value === "string" ? value : "";
  const selectedVersionId = versionIdForWorkflowOption(option?.key, pluginValues);

  useEffect(() => {
    if (inactive) {
      setWorkflows([]);
      return;
    }
    let cancelled = false;
    workflowApi
      .list(0, 100)
      .then((response) => {
        if (!cancelled) setWorkflows(response.workflows);
      })
      .catch(() => {
        if (!cancelled) setWorkflows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [inactive]);

  useEffect(() => {
    if (inactive || !stringValue) {
      setIoContract(null);
      return;
    }
    let cancelled = false;
    workflowApi
      .ioContract(stringValue, selectedVersionId)
      .then((response) => {
        if (!cancelled) setIoContract(response);
      })
      .catch(() => {
        if (!cancelled) setIoContract(null);
      });
    return () => {
      cancelled = true;
    };
  }, [inactive, selectedVersionId, stringValue]);

  const options = [
    { value: "", label: workflowLabel(placeholder ?? t("workflowPlugin.selector.noWorkflowSelected")) },
    ...workflows.map((workflow) => ({
      value: workflow.workflow_id,
      label: workflowLabel(workflow.name, workflow.status),
    })),
  ];

  if (stringValue && !options.some((option) => option.value === stringValue)) {
    options.push({
      value: stringValue,
      label: workflowLabel(stringValue),
    });
  }

  const inputFields = workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 4 });
  const outputFields = workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 4 });
  const interfaceLabels = workflowCallableInterfaceLabels(ioContract?.interface);

  return (
    <div className="grid gap-1.5">
      <Select
        value={stringValue}
        onChange={(nextValue) => {
          const normalizedValue = nextValue || null;
          if (normalizedValue !== stringValue) {
            const versionKey = option?.key
              ? VERSION_KEY_BY_WORKFLOW_ID_KEY[option.key]
              : undefined;
            if (versionKey) onPluginValueChange?.(versionKey, null);
          }
          onChange(normalizedValue);
        }}
        disabled={disabled}
        triggerClassName={triggerClassName}
        options={options}
      />
      {stringValue && ioContract && (
        <div className="grid gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-2 py-1.5 text-[11px] text-[var(--theme-text-secondary)]">
          <div className="flex min-w-0 flex-wrap gap-1">
            <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.interface")}</span>
            <span className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5" title={interfaceLabels.entrySchema}>
              {t("workflowPlugin.selector.entry")} {interfaceLabels.entry}
            </span>
            <span className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5" title={interfaceLabels.exitSchema}>
              {t("workflowPlugin.selector.exit")} {interfaceLabels.exit}
            </span>
          </div>
          <div className="flex min-w-0 flex-wrap gap-1">
            <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.inputs")}</span>
            {(inputFields.length ? inputFields : [t("workflowPlugin.editor.common.none")]).map((field) => (
              <span key={`input-${field}`} className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
                {field}
              </span>
            ))}
          </div>
          <div className="flex min-w-0 flex-wrap gap-1">
            <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.outputs")}</span>
            {(outputFields.length ? outputFields : [t("workflowPlugin.editor.common.none")]).map((field) => (
              <span key={`output-${field}`} className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
                {field}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function WorkflowPluginInputOption({
  option,
  value,
  pluginValues,
  disabled,
  inactive,
  onChange,
}: WorkflowSelectOptionProps) {
  const { t } = useTranslation();
  const workflowId = workflowInputOptionWorkflowId(option?.key, pluginValues);
  const versionId = workflowInputOptionVersionId(option?.key, pluginValues);
  const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null);
  const [draft, setDraft] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      setDraft(JSON.stringify(value, null, 2));
    } else if (typeof value === "string" && value.trim()) {
      setDraft(value);
    } else {
      setDraft("{}");
    }
  }, [value]);

  useEffect(() => {
    const validation = inputDraftError(draft, ioContract);
    setError(workflowInputDraftMessage(validation, t) || null);
  }, [draft, ioContract, t]);

  useEffect(() => {
    if (inactive || !workflowId) {
      setIoContract(null);
      return;
    }
    let cancelled = false;
    workflowApi
      .ioContract(workflowId, versionId)
      .then((response) => {
        if (!cancelled) setIoContract(response);
      })
      .catch(() => {
        if (!cancelled) setIoContract(null);
      });
    return () => {
      cancelled = true;
    };
  }, [inactive, versionId, workflowId]);

  const inputFields = workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 4 });
  const outputFields = workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 4 });
  const interfaceLabels = workflowCallableInterfaceLabels(ioContract?.interface);

  const applyDraft = (nextDraft: string) => {
    setDraft(nextDraft);
    const validation = inputDraftError(nextDraft, ioContract);
    setError(workflowInputDraftMessage(validation, t) || null);
    if (!validation?.parsed) return;
    onChange(validation.parsed);
  };

  const fillSample = () => {
    const sample = sampleInputFromContract(ioContract, t("workflowPlugin.selector.sampleScheduledTask"));
    applyDraft(JSON.stringify(sample, null, 2));
  };

  return (
    <div className="grid gap-2">
      <div className="grid gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-2 py-1.5 text-[11px] text-[var(--theme-text-secondary)]">
        <div className="flex min-w-0 flex-wrap gap-1">
          <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.interface")}</span>
          <span className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5" title={interfaceLabels.entrySchema}>
            {t("workflowPlugin.selector.entry")} {interfaceLabels.entry}
          </span>
          <span className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5" title={interfaceLabels.exitSchema}>
            {t("workflowPlugin.selector.exit")} {interfaceLabels.exit}
          </span>
        </div>
        <div className="flex min-w-0 flex-wrap gap-1">
          <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.inputs")}</span>
          {(inputFields.length ? inputFields : [t("workflowPlugin.selector.selectWorkflowFirst")]).map((field) => (
            <span key={`input-${field}`} className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
              {field}
            </span>
          ))}
        </div>
        <div className="flex min-w-0 flex-wrap gap-1">
          <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.selector.outputs")}</span>
          {(outputFields.length ? outputFields : [t("workflowPlugin.editor.common.none")]).map((field) => (
            <span key={`output-${field}`} className="truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
              {field}
            </span>
          ))}
        </div>
      </div>
      <textarea
        value={draft}
        onChange={(event) => applyDraft(event.target.value)}
        disabled={disabled || inactive || !workflowId}
        rows={6}
        spellCheck={false}
        className="w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-2 font-mono text-xs text-[var(--theme-text)] outline-none focus:border-[var(--theme-primary)] disabled:opacity-50"
      />
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <button
          type="button"
          onClick={fillSample}
          disabled={disabled || inactive || !workflowId}
          className="rounded-md border border-[var(--theme-border)] px-2 py-1 text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
        >
          {t("workflowPlugin.selector.fillFromContract")}
        </button>
        {error && <span className="text-red-500">{error}</span>}
      </div>
    </div>
  );
}

export function WorkflowPluginVersionSelectOption({
  option,
  value,
  pluginValues,
  disabled,
  inactive,
  triggerClassName,
  placeholder,
  onChange,
}: WorkflowSelectOptionProps) {
  const { t } = useTranslation();
  const [versions, setVersions] = useState<WorkflowVersionSummary[]>([]);
  const stringValue = typeof value === "string" ? value : "";
  const workflowId = workflowIdForVersionOption(option?.key, pluginValues);

  useEffect(() => {
    if (inactive || !workflowId) {
      setVersions([]);
      return;
    }
    let cancelled = false;
    workflowApi
      .versions(workflowId)
      .then((response) => {
        if (!cancelled) setVersions(response.versions);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [inactive, workflowId]);

  const emptyLabel = workflowId
    ? placeholder ?? t("workflowPlugin.selector.noVersionSelected")
    : t("workflowPlugin.selector.selectWorkflowFirst");
  const options = [
    { value: "", label: versionLabel(emptyLabel) },
    ...versions.map((version) => ({
      value: version.version_id,
      label: versionLabel(`v${version.version_number} - ${version.version_id}`),
    })),
  ];

  if (stringValue && !options.some((option) => option.value === stringValue)) {
    options.push({
      value: stringValue,
      label: versionLabel(stringValue),
    });
  }

  return (
    <Select
      value={stringValue}
      onChange={(nextValue) => onChange(nextValue || null)}
      disabled={disabled || (!workflowId && !stringValue)}
      triggerClassName={triggerClassName}
      options={options}
    />
  );
}

export async function resolveWorkflowPluginLabels(
  values: readonly string[],
): Promise<Record<string, string>> {
  const wanted = new Set(values.filter(Boolean));
  if (wanted.size === 0) return {};
  const response = await workflowApi.list(0, 100);
  return Object.fromEntries(
    response.workflows
      .filter((workflow) => wanted.has(workflow.workflow_id))
      .map((workflow) => [workflow.workflow_id, workflow.name]),
  );
}

export async function resolveWorkflowPluginVersionLabels(
  values: readonly string[],
): Promise<Record<string, string>> {
  const wanted = new Set(values.filter(Boolean));
  if (wanted.size === 0) return {};
  const workflowResponse = await workflowApi.list(0, 100);
  const versionResponses = await Promise.all(
    workflowResponse.workflows.map((workflow) =>
      workflowApi.versions(workflow.workflow_id).catch(() => ({
        workflow_id: workflow.workflow_id,
        versions: [],
        skip: 0,
        limit: 0,
      })),
    ),
  );
  const labels: Record<string, string> = {};
  for (const response of versionResponses) {
    for (const version of response.versions) {
      if (wanted.has(version.version_id)) {
        labels[version.version_id] = `v${version.version_number}`;
      }
    }
  }
  return labels;
}
