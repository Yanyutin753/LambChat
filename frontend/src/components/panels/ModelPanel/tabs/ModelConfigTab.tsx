import { useState, useRef, useMemo } from "react";
import {
  Cpu,
  Plus,
  Trash2,
  Edit2,
  X,
  Save,
  GripVertical,
  Upload,
  Check,
  Download,
  FileJson,
  Layers,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ConfirmDialog } from "../../../common";
import { ToggleSwitch, ProviderSelect } from "../../AgentPanel/shared";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { modelApi } from "../../../../services/api";
import type {
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
  ProviderType,
} from "../../../../services/api/model";

interface ModelConfigTabProps {
  models: ModelConfig[];
  onReload: () => void;
}

interface BatchModelRow {
  id: string;
  value: string;
  label: string;
  description: string;
  provider: string;
  temperature: string;
  maxTokens: string;
  maxInputTokens: string;
}

let _rowIdCounter = 0;
const createEmptyBatchRow = (): BatchModelRow => ({
  id: `row-${++_rowIdCounter}-${Date.now()}`,
  value: "",
  label: "",
  description: "",
  provider: "",
  temperature: "",
  maxTokens: "",
  maxInputTokens: "",
});

export function ModelConfigTab({ models, onReload }: ModelConfigTabProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState<ModelConfig | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // Drag-and-drop state
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const dragNode = useRef<HTMLDivElement | null>(null);

  // Form state
  const [formValue, setFormValue] = useState("");
  const [formLabel, setFormLabel] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formApiKey, setFormApiKey] = useState("");
  const [formApiBase, setFormApiBase] = useState("");
  const [formTemperature, setFormTemperature] = useState("");
  const [formMaxTokens, setFormMaxTokens] = useState("");
  const [formMaxInputTokens, setFormMaxInputTokens] = useState("");
  const [formProvider, setFormProvider] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  // Batch create state
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [batchActiveTab, setBatchActiveTab] = useState<
    "addOneByOne" | "jsonImport"
  >("addOneByOne");
  const [batchApiKey, setBatchApiKey] = useState("");
  const [batchApiBase, setBatchApiBase] = useState("");
  const [showBatchApiKey, setShowBatchApiKey] = useState(false);
  const [batchRows, setBatchRows] = useState<BatchModelRow[]>([
    createEmptyBatchRow(),
  ]);
  const [importJson, setImportJson] = useState("");
  const [importResult, setImportResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [batchSaving, setBatchSaving] = useState(false);

  const resetForm = () => {
    setFormValue("");
    setFormLabel("");
    setFormDescription("");
    setFormApiKey("");
    setFormApiBase("");
    setFormTemperature("");
    setFormMaxTokens("");
    setFormMaxInputTokens("");
    setFormProvider("");
    setShowApiKey(false);
    setIsEditing(null);
    setIsCreating(false);
  };

  // Masked API key pattern from backend (e.g., "sk-a...xyz" or "****")
  const isMaskedApiKey = (key: string) => key.includes("...") || key === "****";

  const startEdit = (model: ModelConfig) => {
    setIsEditing(model);
    setFormValue(model.value);
    setFormLabel(model.label);
    setFormDescription(model.description || "");
    // Don't populate form with masked key — user must enter a new key to change it
    setFormApiKey("");
    setFormApiBase(model.api_base || "");
    setFormTemperature(model.temperature?.toString() || "");
    setFormMaxTokens(model.max_tokens?.toString() || "");
    setFormMaxInputTokens(model.profile?.max_input_tokens?.toString() || "");
    setFormProvider(model.provider || "");
    setShowApiKey(false);
    setIsCreating(false);
  };

  const startCreate = () => {
    resetForm();
    setIsCreating(true);
  };

  // Export models as JSON
  const handleExportModels = () => {
    const data = models.map(
      ({
        id: _,
        order: __,
        enabled: ___,
        created_at: ____,
        updated_at: _____,
        ...rest
      }) => rest,
    );
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "models.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  // Batch create helpers
  const addBatchRow = () =>
    setBatchRows((prev) => [...prev, createEmptyBatchRow()]);
  const removeBatchRow = (rowId: string) =>
    setBatchRows((prev) => prev.filter((r) => r.id !== rowId));
  const updateBatchRow = (
    rowId: string,
    field: keyof BatchModelRow,
    value: string,
  ) =>
    setBatchRows((prev) =>
      prev.map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    );

  const validBatchRows = batchRows.filter(
    (r) => r.value.trim() && r.label.trim(),
  );

  const resetBatchForm = () => {
    setBatchApiKey("");
    setBatchApiBase("");
    setShowBatchApiKey(false);
    setBatchRows([createEmptyBatchRow()]);
    setImportJson("");
    setImportResult(null);
    setBatchSaving(false);
    setBatchActiveTab("addOneByOne");
  };

  const handleBatchCreateRows = async () => {
    if (validBatchRows.length === 0) {
      toast.error(t("agentConfig.batchNoModels"));
      return;
    }
    setBatchSaving(true);
    try {
      const models: ModelConfigCreate[] = validBatchRows.map((r) => {
        const temperature = r.temperature
          ? parseFloat(r.temperature)
          : undefined;
        const maxTokens = r.maxTokens ? parseInt(r.maxTokens, 10) : undefined;
        const maxInputTokens = r.maxInputTokens
          ? parseInt(r.maxInputTokens, 10)
          : undefined;
        if (
          r.temperature &&
          (isNaN(temperature!) || temperature! < 0 || temperature! > 2)
        ) {
          throw new Error(t("agentConfig.invalidTemperature"));
        }
        if (r.maxTokens && isNaN(maxTokens!)) {
          throw new Error(t("agentConfig.invalidMaxTokens"));
        }
        if (r.maxInputTokens && isNaN(maxInputTokens!)) {
          throw new Error(t("agentConfig.invalidMaxInputTokens"));
        }
        return {
          value: r.value.trim(),
          label: r.label.trim(),
          description: r.description.trim() || undefined,
          provider: (r.provider || undefined) as ProviderType | undefined,
          api_key: batchApiKey.trim() || undefined,
          api_base: batchApiBase.trim() || undefined,
          temperature,
          max_tokens: maxTokens,
          profile: maxInputTokens
            ? { max_input_tokens: maxInputTokens }
            : undefined,
          enabled: true,
        };
      });
      await modelApi.importModels(models);
      toast.success(
        t("agentConfig.batchCreateSuccess", { count: models.length }),
      );
      resetBatchForm();
      setShowBatchModal(false);
      onReload();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.batchCreateFailed"));
    } finally {
      setBatchSaving(false);
    }
  };

  const importValidation = useMemo(() => {
    if (!importJson.trim()) return { valid: false };
    try {
      const parsed = JSON.parse(importJson);
      if (!Array.isArray(parsed) || parsed.length === 0)
        return { valid: false };
      for (const item of parsed) {
        if (!item.value || !item.label) return { valid: false };
      }
      return { valid: true, count: parsed.length };
    } catch {
      return { valid: false };
    }
  }, [importJson]);

  const handleJsonImport = async () => {
    if (!importValidation.valid) {
      toast.error(t("agentConfig.importInvalidFormat"));
      return;
    }
    setBatchSaving(true);
    setImportResult(null);
    try {
      const parsed = JSON.parse(importJson) as ModelConfigCreate[];
      await modelApi.importModels(parsed);
      setImportResult({
        success: true,
        message: t("agentConfig.batchCreateSuccess", { count: parsed.length }),
      });
      toast.success(
        t("agentConfig.batchCreateSuccess", { count: parsed.length }),
      );
      onReload();
      setTimeout(() => {
        setShowBatchModal(false);
      }, 1200);
    } catch (err) {
      const msg = (err as Error).message || t("agentConfig.batchCreateFailed");
      setImportResult({ success: false, message: msg });
      toast.error(msg);
    } finally {
      setBatchSaving(false);
    }
  };

  const handleSave = async () => {
    if (!formValue.trim() || !formLabel.trim()) {
      toast.error(t("agentConfig.valueAndLabelRequired"));
      return;
    }

    // Validate numeric fields
    const temperature = formTemperature
      ? parseFloat(formTemperature)
      : undefined;
    const maxTokens = formMaxTokens ? parseInt(formMaxTokens, 10) : undefined;
    const maxInputTokens = formMaxInputTokens
      ? parseInt(formMaxInputTokens, 10)
      : undefined;

    if (
      formTemperature &&
      (isNaN(temperature!) || temperature! < 0 || temperature! > 2)
    ) {
      toast.error(t("agentConfig.invalidTemperature"));
      return;
    }
    if (formMaxTokens && isNaN(maxTokens!)) {
      toast.error(t("agentConfig.invalidMaxTokens"));
      return;
    }
    if (formMaxInputTokens && isNaN(maxInputTokens!)) {
      toast.error(t("agentConfig.invalidMaxInputTokens"));
      return;
    }

    setIsSaving(true);
    try {
      const data: ModelConfigCreate = {
        value: formValue.trim(),
        provider: (formProvider || undefined) as ProviderType | undefined,
        label: formLabel.trim(),
        description: formDescription.trim() || undefined,
        api_key: formApiKey.trim() || undefined,
        api_base: formApiBase.trim() || undefined,
        temperature,
        max_tokens: maxTokens,
        profile: maxInputTokens
          ? { max_input_tokens: maxInputTokens }
          : undefined,
        enabled: true,
      };

      if (isEditing?.id) {
        const update: ModelConfigUpdate = {
          provider: (formProvider || undefined) as ProviderType | undefined,
          label: formLabel.trim(),
          description: formDescription.trim() || undefined,
          // Only send api_key if user entered a new one (don't send masked keys)
          ...(formApiKey.trim() && !isMaskedApiKey(formApiKey.trim())
            ? { api_key: formApiKey.trim() }
            : {}),
          api_base: formApiBase.trim() || undefined,
          temperature,
          max_tokens: maxTokens,
          profile: maxInputTokens
            ? { max_input_tokens: maxInputTokens }
            : undefined,
        };
        await modelApi.update(isEditing.id, update);
        toast.success(t("agentConfig.modelSaveSuccess"));
      } else {
        await modelApi.create(data);
        toast.success(t("agentConfig.modelCreateSuccess"));
      }
      resetForm();
      onReload();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.modelSaveFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (modelId: string) => {
    setDeleteTarget(modelId);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(deleteTarget);
    setDeleteTarget(null);
    try {
      await modelApi.delete(deleteTarget);
      toast.success(t("agentConfig.modelDeleteSuccess"));
      onReload();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.modelDeleteFailed"));
    } finally {
      setIsDeleting(null);
    }
  };

  const handleToggle = async (model: ModelConfig) => {
    if (!model.id) return;
    try {
      await modelApi.toggle(model.id, !model.enabled);
      toast.success(
        !model.enabled
          ? t("agentConfig.modelEnabled")
          : t("agentConfig.modelDisabled"),
      );
      onReload();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.modelToggleFailed"));
    }
  };

  // ---- Drag-and-drop handlers ----

  const handleDragStart = (
    index: number,
    e: React.DragEvent<HTMLDivElement>,
  ) => {
    setDragIndex(index);
    dragNode.current = e.currentTarget;
    requestAnimationFrame(() => {
      if (dragNode.current) {
        dragNode.current.style.opacity = "0.4";
      }
    });
  };

  const handleDragOver = (index: number, e: React.DragEvent) => {
    e.preventDefault();
    if (dragIndex === null || dragIndex === index) return;
    setOverIndex(index);
  };

  const handleDragEnd = async () => {
    if (dragNode.current) {
      dragNode.current.style.opacity = "";
    }
    if (dragIndex !== null && overIndex !== null && dragIndex !== overIndex) {
      const reordered = [...models];
      const [moved] = reordered.splice(dragIndex, 1);
      reordered.splice(overIndex, 0, moved);
      try {
        await modelApi.reorder(
          reordered.map((m) => m.id).filter(Boolean) as string[],
        );
        onReload();
      } catch (err) {
        toast.error((err as Error).message || "Failed to reorder models");
      }
    }
    setDragIndex(null);
    setOverIndex(null);
    dragNode.current = null;
  };

  // ---- Render helpers ----

  const modelTags = (model: ModelConfig, compact = false) => {
    const tags: React.ReactNode[] = [];
    if (model.provider) {
      tags.push(
        <span
          key="provider"
          className={`glass-tag glass-tag--provider ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          {model.provider}
        </span>,
      );
    }
    if (model.api_key) {
      tags.push(
        <span
          key="key"
          className={`glass-tag glass-tag--key ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          Key
        </span>,
      );
    }
    if (model.api_base) {
      tags.push(
        <span
          key="api"
          className={`glass-tag glass-tag--api ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          API
        </span>,
      );
    }
    if (model.temperature != null) {
      tags.push(
        <span
          key="temp"
          className={`glass-tag glass-tag--accent ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          temp:{model.temperature}
        </span>,
      );
    }
    if (model.max_tokens != null) {
      tags.push(
        <span
          key="max"
          className={`glass-tag glass-tag--accent ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          max:{model.max_tokens}
        </span>,
      );
    }
    if (model.profile?.max_input_tokens != null) {
      tags.push(
        <span
          key="ctx"
          className={`glass-tag glass-tag--accent ${
            compact ? "text-[10px]" : "text-xs"
          }`}
        >
          ctx:{model.profile.max_input_tokens}
        </span>,
      );
    }
    return tags;
  };

  const hasTags = (model: ModelConfig) =>
    !!(
      model.provider ||
      model.api_key ||
      model.api_base ||
      model.temperature != null ||
      model.max_tokens != null ||
      model.profile?.max_input_tokens != null
    );

  // Show list
  return (
    <>
      <div className="flex flex-col gap-4 h-full">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-stone-500 dark:text-stone-400 hidden sm:block">
            {t("agentConfig.modelConfigDescription")}
          </p>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleExportModels}
              disabled={models.length === 0}
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-[var(--glass-border)] text-stone-700 dark:text-stone-300 hover:bg-[var(--glass-bg-subtle)] transition-colors disabled:opacity-40"
            >
              <Download size={16} />
              <span className="hidden sm:inline">
                {t("agentConfig.exportModels")}
              </span>
            </button>
            <button
              onClick={() => {
                resetBatchForm();
                setBatchActiveTab("jsonImport");
                setShowBatchModal(true);
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-[var(--glass-border)] text-stone-700 dark:text-stone-300 hover:bg-[var(--glass-bg-subtle)] transition-colors"
            >
              <FileJson size={16} />
              <span className="hidden sm:inline">
                {t("agentConfig.importModels")}
              </span>
            </button>
            <button
              onClick={() => {
                resetBatchForm();
                setShowBatchModal(true);
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-[var(--glass-border)] text-stone-700 dark:text-stone-300 hover:bg-[var(--glass-bg-subtle)] transition-colors"
            >
              <Layers size={16} />
              <span className="hidden sm:inline">
                {t("agentConfig.batchCreate")}
              </span>
            </button>
            <button
              onClick={startCreate}
              className="btn-primary flex items-center gap-1.5 px-3 py-2 sm:px-4 text-sm hover:shadow-lg hover:shadow-stone-500/10 transition-shadow duration-200"
            >
              <Plus size={16} />
              <span className="hidden sm:inline">
                {t("agentConfig.addModel")}
              </span>
            </button>
          </div>
        </div>

        {models.length === 0 ? (
          <div className="skill-empty-state flex-1 animate-glass-enter">
            <Cpu size={28} className="skill-empty-state__icon" />
            <p className="skill-empty-state__title">
              {t("agentConfig.noModelsConfigured")}
            </p>
            <p className="skill-empty-state__description">
              {t("agentConfig.noModelsConfiguredHint")}
            </p>
            <button onClick={startCreate} className="skill-empty-state__action">
              <Plus size={14} />
              {t("agentConfig.addFirstModel")}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {models.map((model, index) => {
              const isDragging = dragIndex === index;
              const isDragOver =
                overIndex === index &&
                dragIndex !== null &&
                dragIndex !== index;

              return (
                <div
                  key={model.id}
                  draggable
                  onDragStart={(e) => handleDragStart(index, e)}
                  onDragOver={(e) => handleDragOver(index, e)}
                  onDragLeave={(e) => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                      setOverIndex(null);
                    }
                  }}
                  onDragEnd={handleDragEnd}
                  className={`group glass-card rounded-xl transition-all duration-200 cursor-grab active:cursor-grabbing ${
                    isDragging
                      ? "!border-blue-300/60 !bg-blue-50/40 dark:!border-blue-700/50 dark:!bg-blue-900/20 scale-[1.01] animate-glass-drag"
                      : isDragOver
                        ? "!border-blue-200/50 !bg-blue-50/20 dark:!border-blue-800/30 dark:!bg-blue-900/10"
                        : !model.enabled
                          ? "opacity-60"
                          : ""
                  }`}
                >
                  {/* Mobile layout: stacked */}
                  <div className="block sm:hidden p-3.5">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <GripVertical
                          size={16}
                          className="text-stone-300 dark:text-stone-600 flex-shrink-0"
                        />
                        <ModelIconImg
                          model={model.value}
                          provider={model.provider}
                          size={22}
                        />
                        <h4 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">
                          {model.label}
                        </h4>
                        {!model.enabled && (
                          <span className="glass-pill glass-pill--disabled text-[10px] px-2 py-0.5 flex-shrink-0">
                            {t("agentConfig.off")}
                          </span>
                        )}
                      </div>
                      <ToggleSwitch
                        enabled={model.enabled}
                        onToggle={() => handleToggle(model)}
                        ariaLabel={
                          model.enabled
                            ? t("agentConfig.disable")
                            : t("agentConfig.enable")
                        }
                      />
                    </div>
                    <div className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate mb-2">
                      {model.value}
                    </div>
                    {hasTags(model) && (
                      <div className="flex flex-wrap gap-1 mb-2.5">
                        {modelTags(model, true)}
                      </div>
                    )}
                    <div className="flex items-center gap-1 justify-end -mr-1">
                      <button
                        onClick={() => startEdit(model)}
                        className="p-2 text-stone-500 hover:text-stone-700 hover:bg-white/50 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
                        title={t("agentConfig.edit")}
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => model.id && handleDelete(model.id)}
                        disabled={isDeleting === model.id}
                        className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50/60 rounded-lg transition-all duration-200 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20 disabled:opacity-50"
                        title={t("agentConfig.delete")}
                      >
                        {isDeleting === model.id ? (
                          <LoadingSpinner size="sm" />
                        ) : (
                          <Trash2 size={16} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Desktop layout: horizontal */}
                  <div className="hidden sm:block">
                    <div className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-3 min-w-0 flex-1 pr-4">
                        <GripVertical
                          size={16}
                          className="text-stone-300 dark:text-stone-600 flex-shrink-0"
                        />
                        <ModelIconImg
                          model={model.value}
                          provider={model.provider}
                          size={24}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2.5">
                            <h4 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate tracking-tight">
                              {model.label}
                            </h4>
                            {!model.enabled && (
                              <span className="glass-pill glass-pill--disabled">
                                {t("agentConfig.disabled")}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate">
                              {model.value}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <ToggleSwitch
                          enabled={model.enabled}
                          onToggle={() => handleToggle(model)}
                          ariaLabel={
                            model.enabled
                              ? t("agentConfig.disable")
                              : t("agentConfig.enable")
                          }
                        />
                        <button
                          onClick={() => startEdit(model)}
                          className="p-2 text-stone-500 hover:text-stone-700 hover:bg-white/50 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
                          title={t("agentConfig.edit")}
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => model.id && handleDelete(model.id)}
                          disabled={isDeleting === model.id}
                          className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50/60 rounded-lg transition-all duration-200 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20 disabled:opacity-50"
                          title={t("agentConfig.delete")}
                        >
                          {isDeleting === model.id ? (
                            <LoadingSpinner size="sm" />
                          ) : (
                            <Trash2 size={16} />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Details row */}
                    {(model.description || hasTags(model)) && (
                      <div className="px-4 pb-4 pt-0">
                        <div className="glass-card-subtle rounded-lg px-3 py-2.5">
                          {model.description && (
                            <p className="text-xs text-stone-500 dark:text-stone-400 mb-2">
                              {model.description}
                            </p>
                          )}
                          <div className="flex flex-wrap gap-1.5">
                            {modelTags(model, false)}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Create / Edit Modal */}
        {(isEditing || isCreating) && (
          <>
            <div
              className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
              onClick={resetForm}
            />
            <div
              className="modal-bottom-sheet sm:modal-centered-wrapper"
              onClick={resetForm}
            >
              <div className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-2xl max-h-[85vh] flex flex-col">
                <div className="bottom-sheet-handle sm:hidden" />
                <div className="flex items-center justify-between glass-divider px-6 py-4">
                  <div>
                    <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                      {isEditing
                        ? t("agentConfig.editModel")
                        : t("agentConfig.createModel")}
                    </h3>
                    <p className="text-xs text-stone-500 dark:text-stone-500 mt-0.5">
                      {isEditing
                        ? t("agentConfig.editModelDesc", "修改模型配置信息")
                        : t(
                            "agentConfig.createModelDesc",
                            "添加一个新的模型配置",
                          )}
                    </p>
                  </div>
                  <button onClick={resetForm} className="btn-icon">
                    <X size={20} />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-2">
                  {/* Basic Info */}
                  <div className="space-y-2">
                    <div>
                      <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                        {t("agentConfig.modelValue")}{" "}
                        <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="text"
                        value={formValue}
                        onChange={(e) => setFormValue(e.target.value)}
                        disabled={!!isEditing}
                        placeholder={t("agentConfig.modelValuePlaceholder")}
                        className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 disabled:opacity-50 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                      />
                      <p className="mt-1 text-xs text-stone-400 dark:text-stone-500">
                        {isEditing
                          ? t(
                              "agentConfig.modelValueReadonly",
                              "模型 ID 创建后不可修改",
                            )
                          : t(
                              "agentConfig.modelValueHint",
                              "例如 anthropic/claude-3-5-sonnet，用于路由到对应的 API",
                            )}
                      </p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                        {t("agentConfig.modelLabel")}{" "}
                        <span className="text-red-400">*</span>
                      </label>
                      <input
                        type="text"
                        value={formLabel}
                        onChange={(e) => setFormLabel(e.target.value)}
                        placeholder={t("agentConfig.modelLabelPlaceholder")}
                        className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                      />
                    </div>
                  </div>

                  {/* Advanced (collapsed) */}
                  <details className="group">
                    <summary className="text-xs text-stone-500 dark:text-stone-500 cursor-pointer select-none hover:text-stone-700 dark:hover:text-stone-300 transition-colors py-1">
                      {t("agentConfig.advancedConfig", "高级配置")}
                    </summary>
                    <div
                      className="space-y-2 mt-2 pt-2 border-t"
                      style={{ borderColor: "var(--glass-border)" }}
                    >
                      <div>
                        <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                          {t("agentConfig.modelDescription")}
                        </label>
                        <input
                          type="text"
                          value={formDescription}
                          onChange={(e) => setFormDescription(e.target.value)}
                          placeholder={t(
                            "agentConfig.modelDescriptionPlaceholder",
                          )}
                          className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                          {t("agentConfig.modelProvider")}
                        </label>
                        <ProviderSelect
                          value={formProvider}
                          onChange={setFormProvider}
                          placeholder={t("agentConfig.providerAuto")}
                        />
                        <p className="mt-1 text-xs text-stone-400 dark:text-stone-500">
                          {t("agentConfig.providerHint")}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                          {t("agentConfig.modelApiKey")}
                        </label>
                        <div className="relative">
                          <input
                            type={showApiKey ? "text" : "password"}
                            value={formApiKey}
                            onChange={(e) => setFormApiKey(e.target.value)}
                            placeholder={t("agentConfig.apiKeyPlaceholder")}
                            className="glass-input w-full px-3 py-2 pr-10 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                          />
                          <button
                            type="button"
                            onClick={() => setShowApiKey(!showApiKey)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-stone-500 hover:text-stone-700 rounded-md dark:text-stone-400"
                          >
                            {showApiKey ? (
                              <svg
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                                />
                              </svg>
                            ) : (
                              <svg
                                className="h-4 w-4"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                                />
                              </svg>
                            )}
                          </button>
                        </div>
                        <p className="mt-1 text-xs text-stone-400 dark:text-stone-500">
                          {isEditing
                            ? t("agentConfig.apiKeyEditHint")
                            : t("agentConfig.apiKeyHint")}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                          {t("agentConfig.modelApiBase")}
                        </label>
                        <input
                          type="text"
                          value={formApiBase}
                          onChange={(e) => setFormApiBase(e.target.value)}
                          placeholder={t("agentConfig.modelApiBasePlaceholder")}
                          className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                        />
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        <div>
                          <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                            {t("agentConfig.temperature")}
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="2"
                            value={formTemperature}
                            onChange={(e) => setFormTemperature(e.target.value)}
                            placeholder="0.7"
                            className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                            {t("agentConfig.maxTokens")}
                          </label>
                          <input
                            type="number"
                            value={formMaxTokens}
                            onChange={(e) => setFormMaxTokens(e.target.value)}
                            placeholder="4096"
                            className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                            {t("agentConfig.maxInputTokens")}
                          </label>
                          <input
                            type="number"
                            value={formMaxInputTokens}
                            onChange={(e) =>
                              setFormMaxInputTokens(e.target.value)
                            }
                            placeholder="200000"
                            className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                          />
                        </div>
                      </div>
                    </div>
                  </details>
                </div>

                <div className="flex justify-end gap-2 px-6 py-4 glass-divider">
                  <button onClick={resetForm} className="btn-secondary">
                    {t("common.cancel")}
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="btn-primary disabled:opacity-50"
                  >
                    {isSaving ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <Save size={16} />
                    )}
                    {t("common.save")}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Batch Create Modal */}
        {showBatchModal && (
          <>
            <div
              className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
              onClick={() => setShowBatchModal(false)}
            />
            <div
              className="modal-bottom-sheet sm:modal-centered-wrapper"
              onClick={() => setShowBatchModal(false)}
            >
              <div className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-3xl max-h-[85vh] flex flex-col">
                <div className="bottom-sheet-handle sm:hidden" />
                <div className="flex items-center justify-between px-6 py-4">
                  <div>
                    <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                      {t("agentConfig.batchCreateTitle")}
                    </h3>
                    <p className="text-xs text-stone-500 dark:text-stone-500 mt-0.5">
                      {t("agentConfig.batchCreateDesc", "快速添加多个模型配置")}
                    </p>
                  </div>
                  <button
                    onClick={() => setShowBatchModal(false)}
                    className="btn-icon"
                  >
                    <X size={20} />
                  </button>
                </div>

                {/* Tab bar */}
                <div
                  className="flex border-b px-6"
                  style={{ borderColor: "var(--glass-border)" }}
                >
                  <button
                    onClick={() => {
                      setBatchActiveTab("addOneByOne");
                      setImportResult(null);
                    }}
                    className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                      batchActiveTab === "addOneByOne"
                        ? "border-stone-900 dark:border-stone-100 text-stone-900 dark:text-stone-100"
                        : "border-transparent text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                    }`}
                  >
                    {t("agentConfig.batchTabAddOneByOne")}
                  </button>
                  <button
                    onClick={() => {
                      setBatchActiveTab("jsonImport");
                      setImportResult(null);
                    }}
                    className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                      batchActiveTab === "jsonImport"
                        ? "border-stone-900 dark:border-stone-100 text-stone-900 dark:text-stone-100"
                        : "border-transparent text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                    }`}
                  >
                    {t("agentConfig.batchTabJsonImport")}
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
                  {/* Shared Config (Tab 1 only) */}
                  {batchActiveTab === "addOneByOne" && (
                    <div className="glass-card-subtle rounded-xl p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-500">
                          {t("agentConfig.sharedConfig")}
                        </h4>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-200/60 dark:bg-stone-700/40 text-stone-500 dark:text-stone-400">
                          {t("agentConfig.optional", "可选")}
                        </span>
                      </div>
                      <p className="text-xs text-stone-500 dark:text-stone-500 -mt-1">
                        {t(
                          "agentConfig.sharedConfigHint",
                          "为所有模型统一设置 API 地址和密钥，留空则各模型单独配置",
                        )}
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                            {t("agentConfig.modelApiBase")}
                          </label>
                          <input
                            type="text"
                            value={batchApiBase}
                            onChange={(e) => setBatchApiBase(e.target.value)}
                            placeholder={t(
                              "agentConfig.modelApiBasePlaceholder",
                            )}
                            className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                            {t("agentConfig.modelApiKey")}
                          </label>
                          <div className="relative">
                            <input
                              type={showBatchApiKey ? "text" : "password"}
                              value={batchApiKey}
                              onChange={(e) => setBatchApiKey(e.target.value)}
                              placeholder={t("agentConfig.apiKeyPlaceholder")}
                              className="glass-input w-full px-3.5 py-2.5 pr-10 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                            />
                            <button
                              type="button"
                              onClick={() =>
                                setShowBatchApiKey(!showBatchApiKey)
                              }
                              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-stone-500 hover:text-stone-700 rounded-md dark:text-stone-400"
                            >
                              {showBatchApiKey ? (
                                <svg
                                  className="h-4 w-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                                  />
                                </svg>
                              ) : (
                                <svg
                                  className="h-4 w-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                                  />
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                                  />
                                </svg>
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Tab 1: Add One by One */}
                  {batchActiveTab === "addOneByOne" && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-stone-500 dark:text-stone-500">
                          {t(
                            "agentConfig.batchModelListHint",
                            "* 值 和标签为必填项",
                          )}
                        </p>
                        <span className="text-xs text-stone-400 dark:text-stone-400">
                          {validBatchRows.length > 0 &&
                            `${validBatchRows.length}/${batchRows.length}`}
                        </span>
                      </div>
                      {batchRows.map((row, index) => (
                        <div
                          key={row.id}
                          className="glass-card-subtle rounded-xl p-3 sm:p-4 space-y-2"
                        >
                          {/* Header: number + delete */}
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] text-stone-400 font-mono">
                              #{index + 1}
                            </span>
                            {batchRows.length > 1 && (
                              <button
                                onClick={() => removeBatchRow(row.id)}
                                className="p-1.5 text-stone-400 hover:text-red-500 rounded-lg transition-colors"
                                title={t("common.delete")}
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                          {/* Basic */}
                          <div className="space-y-2">
                            <div>
                              <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                {t("agentConfig.modelValue")}{" "}
                                <span className="text-red-400">*</span>
                              </label>
                              <input
                                type="text"
                                value={row.value}
                                onChange={(e) =>
                                  updateBatchRow(
                                    row.id,
                                    "value",
                                    e.target.value,
                                  )
                                }
                                placeholder={t(
                                  "agentConfig.modelValuePlaceholder",
                                )}
                                className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                {t("agentConfig.modelLabel")}{" "}
                                <span className="text-red-400">*</span>
                              </label>
                              <input
                                type="text"
                                value={row.label}
                                onChange={(e) =>
                                  updateBatchRow(
                                    row.id,
                                    "label",
                                    e.target.value,
                                  )
                                }
                                placeholder={t(
                                  "agentConfig.modelLabelPlaceholder",
                                )}
                                className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                              />
                            </div>
                          </div>
                          {/* Advanced (collapsed by default) */}
                          <details className="group">
                            <summary className="text-xs text-stone-500 dark:text-stone-500 cursor-pointer select-none hover:text-stone-700 dark:hover:text-stone-300 transition-colors">
                              {t("agentConfig.advancedConfig", "高级配置")}
                            </summary>
                            <div
                              className="space-y-2 mt-2 pt-2 border-t"
                              style={{ borderColor: "var(--glass-border)" }}
                            >
                              <div>
                                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                  {t("agentConfig.modelDescription")}
                                </label>
                                <input
                                  type="text"
                                  value={row.description}
                                  onChange={(e) =>
                                    updateBatchRow(
                                      row.id,
                                      "description",
                                      e.target.value,
                                    )
                                  }
                                  placeholder={t(
                                    "agentConfig.modelDescriptionPlaceholder",
                                  )}
                                  className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                  {t("agentConfig.modelProvider")}
                                </label>
                                <ProviderSelect
                                  value={row.provider}
                                  onChange={(v) =>
                                    updateBatchRow(row.id, "provider", v)
                                  }
                                  placeholder={t("agentConfig.providerAuto")}
                                />
                                <p className="mt-1 text-xs text-stone-400 dark:text-stone-500">
                                  {t("agentConfig.providerHint")}
                                </p>
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <div>
                                  <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                    {t("agentConfig.temperature")}
                                  </label>
                                  <input
                                    type="number"
                                    step="0.1"
                                    min="0"
                                    max="2"
                                    value={row.temperature}
                                    onChange={(e) =>
                                      updateBatchRow(
                                        row.id,
                                        "temperature",
                                        e.target.value,
                                      )
                                    }
                                    placeholder="0.7"
                                    className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                    {t("agentConfig.maxTokens")}
                                  </label>
                                  <input
                                    type="number"
                                    value={row.maxTokens}
                                    onChange={(e) =>
                                      updateBatchRow(
                                        row.id,
                                        "maxTokens",
                                        e.target.value,
                                      )
                                    }
                                    placeholder="4096"
                                    className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1">
                                    {t("agentConfig.maxInputTokens")}
                                  </label>
                                  <input
                                    type="number"
                                    value={row.maxInputTokens}
                                    onChange={(e) =>
                                      updateBatchRow(
                                        row.id,
                                        "maxInputTokens",
                                        e.target.value,
                                      )
                                    }
                                    placeholder="200000"
                                    className="glass-input w-full px-3 py-2 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                                  />
                                </div>
                              </div>
                            </div>
                          </details>
                        </div>
                      ))}
                      <button
                        onClick={addBatchRow}
                        className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm text-stone-500 hover:text-stone-700 border border-dashed border-stone-300 dark:border-stone-600 hover:border-stone-400 dark:hover:border-stone-500 rounded-xl transition-colors dark:text-stone-400 dark:hover:text-stone-200"
                      >
                        <Plus size={16} />
                        {t("agentConfig.batchAddRow")}
                      </button>
                    </div>
                  )}

                  {/* Tab 2: JSON Import */}
                  {batchActiveTab === "jsonImport" && (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                          {t("agentConfig.batchJsonLabel")}
                        </label>
                        <textarea
                          value={importJson}
                          onChange={(e) => {
                            setImportJson(e.target.value);
                            setImportResult(null);
                          }}
                          rows={10}
                          placeholder={`[
  {
    "value": "openai/gpt-4o",
    "label": "GPT-4o",
    "description": "最新的多模态模型",
    "provider": "openai",
    "api_key": "sk-...",
    "api_base": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 4096,
    "profile": { "max_input_tokens": 128000 }
  }
]`}
                          className="w-full rounded-xl glass-input px-3 py-2 font-mono text-sm text-stone-900 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:border-stone-400 focus:outline-none"
                        />
                        <p className="mt-1.5 text-xs text-stone-500">
                          {t("agentConfig.batchJsonHint")}
                        </p>
                      </div>
                      {importJson.trim() && (
                        <div
                          className={`rounded-xl p-3 text-sm flex items-center gap-2 ${
                            importValidation.valid
                              ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          }`}
                        >
                          {importValidation.valid ? (
                            <Check size={16} />
                          ) : (
                            <X size={16} />
                          )}
                          {importValidation.valid
                            ? t("agentConfig.batchJsonPreview", {
                                count: importValidation.count,
                              })
                            : t("agentConfig.batchJsonError")}
                        </div>
                      )}
                      {importResult && (
                        <div
                          className={`flex items-center gap-2 rounded-xl p-3 ${
                            importResult.success
                              ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          }`}
                        >
                          {importResult.success ? (
                            <Check size={20} />
                          ) : (
                            <X size={20} />
                          )}
                          <span className="whitespace-pre-wrap text-sm">
                            {importResult.message}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-2 px-6 py-4 glass-divider">
                  <button
                    onClick={() => setShowBatchModal(false)}
                    className="btn-secondary"
                  >
                    {t("common.cancel")}
                  </button>
                  {batchActiveTab === "addOneByOne" ? (
                    <button
                      onClick={handleBatchCreateRows}
                      disabled={batchSaving || validBatchRows.length === 0}
                      className="btn-primary disabled:opacity-50"
                    >
                      {batchSaving ? (
                        <LoadingSpinner size="sm" />
                      ) : (
                        <Upload size={16} />
                      )}
                      {t("agentConfig.batchCreateBtn", {
                        count: validBatchRows.length,
                      })}
                    </button>
                  ) : (
                    <button
                      onClick={handleJsonImport}
                      disabled={batchSaving || !importValidation.valid}
                      className="btn-primary disabled:opacity-50"
                    >
                      {batchSaving ? (
                        <>
                          <LoadingSpinner size="sm" />
                          {t("agentConfig.importing")}
                        </>
                      ) : (
                        <>
                          <Upload size={16} />
                          {t("agentConfig.batchImportBtn")}
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title={t("agentConfig.deleteModel")}
        message={t("agentConfig.confirmDeleteModel")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        variant="danger"
        loading={!!isDeleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  );
}
