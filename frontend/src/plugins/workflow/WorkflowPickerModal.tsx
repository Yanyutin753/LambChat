import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { GitBranch, GitCommit, PencilLine, Plus, Search, Settings2, Workflow, X } from "lucide-react";
import { Select } from "../../components/common";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import {
  workflowApi,
  type WorkflowIoContractResponse,
  type WorkflowSummary,
  type WorkflowVersionSummary,
} from "./api";
import {
  sampleWorkflowInputFromSchema,
  workflowCallableInterfaceLabels,
  workflowInputDraftMessage,
  workflowInputDraftStatus,
  workflowSchemaFieldLabels,
} from "./contractUtils";

interface WorkflowPickerModalProps {
  isOpen: boolean;
  selectedWorkflowId: string | null;
  selectedVersionId?: string | null;
  selectedInput?: unknown;
  onSelect: (workflowId: string | null) => void;
  onSelectVersion?: (versionId: string | null) => void;
  onInputChange?: (value: Record<string, unknown> | null) => void;
  onClose: () => void;
  onCreateWorkflow?: () => void;
  onManageWorkflows?: () => void;
  onEditWorkflow?: (workflowId: string) => void;
}

function workflowMatches(workflow: WorkflowSummary, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    workflow.name.toLowerCase().includes(q) ||
    workflow.workflow_id.toLowerCase().includes(q) ||
    workflow.status.toLowerCase().includes(q)
  );
}

export function WorkflowPickerModal({
  isOpen,
  selectedWorkflowId,
  selectedVersionId,
  selectedInput,
  onSelect,
  onSelectVersion,
  onInputChange,
  onClose,
  onCreateWorkflow,
  onManageWorkflows,
  onEditWorkflow,
}: WorkflowPickerModalProps) {
  const { t } = useTranslation();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [versions, setVersions] = useState<WorkflowVersionSummary[]>([]);
  const [query, setQuery] = useState("");
  const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [contractLoading, setContractLoading] = useState(false);
  const [inputDraft, setInputDraft] = useState("{}");
  const [inputDraftError, setInputDraftError] = useState<string | null>(null);
  useBodyScrollLock(isOpen);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    let cancelled = false;
    workflowApi
      .list(0, 100)
      .then((response) => {
        if (!cancelled) setWorkflows(response.workflows);
      })
      .catch(() => {
        if (!cancelled) setWorkflows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !selectedWorkflowId) {
      setVersions([]);
      setVersionsLoading(false);
      return;
    }
    let cancelled = false;
    setVersionsLoading(true);
    workflowApi
      .versions(selectedWorkflowId)
      .then((response) => {
        if (!cancelled) setVersions(response.versions);
      })
      .catch(() => {
        if (!cancelled) setVersions([]);
      })
      .finally(() => {
        if (!cancelled) setVersionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedWorkflowId]);

  useEffect(() => {
    if (!isOpen || !selectedWorkflowId) {
      setIoContract(null);
      setContractLoading(false);
      return;
    }
    let cancelled = false;
    setContractLoading(true);
    workflowApi
      .ioContract(selectedWorkflowId, selectedVersionId ?? null)
      .then((response) => {
        if (!cancelled) setIoContract(response);
      })
      .catch(() => {
        if (!cancelled) setIoContract(null);
      })
      .finally(() => {
        if (!cancelled) setContractLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedVersionId, selectedWorkflowId]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (selectedInput && typeof selectedInput === "object" && !Array.isArray(selectedInput)) {
      setInputDraft(JSON.stringify(selectedInput, null, 2));
    } else if (typeof selectedInput === "string" && selectedInput.trim()) {
      setInputDraft(selectedInput);
    } else {
      setInputDraft("{}");
    }
  }, [selectedInput]);

  useEffect(() => {
    const validation = workflowInputDraftStatus(inputDraft, ioContract?.input_schema);
    setInputDraftError(workflowInputDraftMessage(validation, t) || null);
  }, [inputDraft, ioContract, t]);

  const filteredWorkflows = useMemo(
    () => workflows.filter((workflow) => workflowMatches(workflow, query)),
    [query, workflows],
  );
  const inputFields = useMemo(
    () => workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 6 }),
    [ioContract],
  );
  const outputFields = useMemo(
    () => workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 6 }),
    [ioContract],
  );
  const interfaceLabels = useMemo(
    () => workflowCallableInterfaceLabels(ioContract?.interface),
    [ioContract],
  );

  const versionValue = selectedVersionId ?? "";
  const versionOptions = [
    {
      value: "",
      label: versionsLoading
        ? t("workflowPlugin.picker.loadingVersions")
        : t("workflowPlugin.picker.usePublishedOrLatest"),
    },
    ...versions.map((version) => ({
      value: version.version_id,
      label: `v${version.version_number} - ${version.version_id}`,
    })),
  ];
  if (versionValue && !versionOptions.some((option) => option.value === versionValue)) {
    versionOptions.push({ value: versionValue, label: versionValue });
  }

  const handleSelect = useCallback(
    (workflowId: string) => {
      if (workflowId !== selectedWorkflowId) {
        onSelectVersion?.(null);
      }
      onSelect(workflowId);
    },
    [onSelect, onSelectVersion, selectedWorkflowId],
  );

  const handleClear = useCallback(() => {
    onSelectVersion?.(null);
    onInputChange?.(null);
    onSelect(null);
    onClose();
  }, [onClose, onInputChange, onSelect, onSelectVersion]);

  const applyInputDraft = useCallback(
    (nextDraft: string) => {
      setInputDraft(nextDraft);
      const validation = workflowInputDraftStatus(nextDraft, ioContract?.input_schema);
      setInputDraftError(workflowInputDraftMessage(validation, t) || null);
      if (validation.parsed) {
        onInputChange?.(validation.parsed);
      }
    },
    [ioContract, onInputChange, t],
  );

  const fillSampleInput = useCallback(() => {
    const sample = sampleWorkflowInputFromSchema(
      ioContract?.input_schema,
      t("workflowPlugin.picker.sampleChatMessage"),
    );
    applyInputDraft(JSON.stringify(sample, null, 2));
  }, [applyInputDraft, ioContract]);

  if (!isOpen) return null;

  return createPortal(
    <div
      data-yields-sidebar
      className="safe-area-viewport-padding fixed inset-0 z-[250] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl md:max-w-4xl lg:max-w-5xl sm:rounded-2xl"
        style={{ background: "var(--theme-bg-card)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-stone-100 dark:bg-stone-800">
              <Workflow size={18} style={{ color: "var(--theme-primary)" }} />
            </div>
            <div className="min-w-0">
              <h2
                className="truncate text-base font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("workflowPlugin.picker.title")}
              </h2>
              <p
                className="truncate text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("workflowPlugin.picker.subtitle")}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="rounded-lg p-2 hover:bg-stone-100 dark:hover:bg-stone-800"
            onClick={onClose}
            title={t("workflowPlugin.picker.close")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 border-b border-stone-200/70 px-5 py-3 dark:border-stone-700/70">
          <div className="flex items-center gap-2">
            {selectedWorkflowId && (
              <button
                type="button"
                onClick={handleClear}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                {t("workflowPlugin.picker.clearCurrent")}
              </button>
            )}
            {selectedWorkflowId && onSelectVersion && (
              <div className="min-w-0 flex-1 sm:max-w-xs">
                <Select
                  value={versionValue}
                  onChange={(nextValue) => onSelectVersion(nextValue || null)}
                  disabled={versionsLoading || (!versions.length && !versionValue)}
                  triggerClassName="h-8 text-xs"
                  options={versionOptions.map((option) => ({
                    value: option.value,
                    label: (
                      <span className="inline-flex min-w-0 items-center gap-2">
                        <GitCommit size={13} className="shrink-0 opacity-70" />
                        <span className="truncate">{option.label}</span>
                      </span>
                    ),
                  }))}
                />
              </div>
            )}
            {onCreateWorkflow && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onCreateWorkflow();
                }}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-primary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-primary)",
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Plus size={13} />
                  {t("workflowPlugin.picker.create")}
                </span>
              </button>
            )}
            {onManageWorkflows && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onManageWorkflows();
                }}
                className="ml-auto rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Settings2 size={13} />
                  {t("workflowPlugin.picker.manage")}
                </span>
              </button>
            )}
            {selectedWorkflowId && onEditWorkflow && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onEditWorkflow(selectedWorkflowId);
                }}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-primary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-primary)",
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <PencilLine size={13} />
                  {t("workflowPlugin.picker.edit")}
                </span>
              </button>
            )}
          </div>
          {selectedWorkflowId && (
            <div className="grid gap-2">
              <div
                className="grid gap-2 rounded-lg border px-3 py-2 text-xs sm:grid-cols-2"
                style={{
                  borderColor: "var(--theme-border)",
                  background: "var(--theme-bg-secondary)",
                }}
              >
                <div className="min-w-0 sm:col-span-2">
                  <div className="mb-1 font-medium text-[var(--theme-text-secondary)]">
                    {t("workflowPlugin.selector.interface")}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {contractLoading ? (
                      <span className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.picker.loading")}</span>
                    ) : (
                      [
                        [t("workflowPlugin.selector.entry"), interfaceLabels.entry, interfaceLabels.entrySchema],
                        [t("workflowPlugin.selector.exit"), interfaceLabels.exit, interfaceLabels.exitSchema],
                        [t("workflowPlugin.selector.schema"), interfaceLabels.schema, interfaceLabels.version],
                      ].map(([label, value, detail]) => (
                        <span
                          key={label}
                          className="max-w-full truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5"
                          title={[value, detail].filter(Boolean).join(" | ")}
                        >
                          {label} {value}
                        </span>
                      ))
                    )}
                  </div>
                </div>
                <div className="min-w-0">
                  <div className="mb-1 font-medium text-[var(--theme-text-secondary)]">
                    {t("workflowPlugin.selector.inputs")}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {contractLoading ? (
                      <span className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.picker.loading")}</span>
                    ) : inputFields.length === 0 ? (
                      <span className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.selector.noneDeclared")}</span>
                    ) : (
                      inputFields.map((field) => (
                        <span key={field} className="max-w-full truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
                          {field}
                        </span>
                      ))
                    )}
                  </div>
                </div>
                <div className="min-w-0">
                  <div className="mb-1 font-medium text-[var(--theme-text-secondary)]">
                    {t("workflowPlugin.selector.outputs")}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {contractLoading ? (
                      <span className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.picker.loading")}</span>
                    ) : outputFields.length === 0 ? (
                      <span className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.selector.noneDeclared")}</span>
                    ) : (
                      outputFields.map((field) => (
                        <span key={field} className="max-w-full truncate rounded bg-[var(--theme-bg)] px-1.5 py-0.5">
                          {field}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>
              {onInputChange && (
                <div className="grid gap-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.picker.entryInputJson")}
                    </span>
                    <button
                      type="button"
                      onClick={fillSampleInput}
                      className="rounded-md border px-2 py-1 text-xs transition-colors hover:border-[var(--theme-primary)]"
                      style={{
                        borderColor: "var(--theme-border)",
                        color: "var(--theme-text-secondary)",
                      }}
                    >
                      {t("workflowPlugin.selector.fillFromContract")}
                    </button>
                  </div>
                  <textarea
                    value={inputDraft}
                    onChange={(event) => applyInputDraft(event.target.value)}
                    rows={4}
                    spellCheck={false}
                    className="w-full resize-y rounded-lg border bg-[var(--theme-bg)] px-3 py-2 font-mono text-xs text-[var(--theme-text)] outline-none focus:border-[var(--theme-primary)]"
                    style={{ borderColor: "var(--theme-border)" }}
                  />
                  <div className="min-h-4 text-xs">
                    {inputDraftError ? (
                      <span className="text-red-500">{inputDraftError}</span>
                    ) : (
                      <span className="text-[var(--theme-text-tertiary)]">
                        {t("workflowPlugin.picker.inputMergeHint")}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("workflowPlugin.picker.searchPlaceholder")}
              className="w-full rounded-lg border bg-transparent py-2 pl-9 pr-3 text-sm outline-none"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text)",
              }}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-10 text-center text-sm text-stone-500">
              {t("workflowPlugin.picker.loading")}
            </div>
          ) : filteredWorkflows.length === 0 ? (
            <div className="py-10 text-center text-sm text-stone-500">
              <div>{t("workflowPlugin.picker.noWorkflows")}</div>
              {onCreateWorkflow && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onCreateWorkflow();
                  }}
                  className="mt-3 inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:border-[var(--theme-primary)]"
                  style={{
                    borderColor: "var(--theme-border)",
                    color: "var(--theme-primary)",
                  }}
                >
                  <Plus size={13} />
                  {t("workflowPlugin.picker.createWorkflow")}
                </button>
              )}
            </div>
          ) : (
            <div className="grid auto-grid-cols gap-3">
              {filteredWorkflows.map((workflow) => {
                const selected = selectedWorkflowId === workflow.workflow_id;
                return (
                  <button
                    key={workflow.workflow_id}
                    type="button"
                    onClick={() => handleSelect(workflow.workflow_id)}
                    className="group flex h-full min-h-32 flex-col rounded-lg border p-4 text-left transition-colors hover:border-[var(--theme-primary)]"
                    style={{
                      borderColor: selected
                        ? "var(--theme-primary)"
                        : "var(--theme-border)",
                      background: selected
                        ? "var(--theme-primary-light)"
                        : "var(--theme-bg-card)",
                    }}
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-[var(--theme-primary)] dark:bg-stone-800">
                        <GitBranch size={17} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="truncate text-sm font-semibold text-[var(--theme-text)]">
                            {workflow.name}
                          </span>
                          <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] uppercase tracking-normal text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                            {workflow.status}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-xs text-[var(--theme-text-secondary)]">
                          {workflow.workflow_id}
                        </div>
                      </div>
                    </div>
                    <div className="mt-auto pt-4 text-xs font-medium text-[var(--theme-primary)]">
                      {selected ? t("workflowPlugin.picker.selected") : t("workflowPlugin.picker.useWorkflow")}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
