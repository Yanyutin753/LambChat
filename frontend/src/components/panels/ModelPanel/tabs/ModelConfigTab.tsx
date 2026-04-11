import { useState, useRef } from "react";
import { Cpu, Plus, Trash2, Edit2, X, Save, GripVertical } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ToggleSwitch } from "../../AgentPanel/shared/ToggleSwitch";
import { modelApi } from "../../../../services/api";
import type {
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
} from "../../../../services/api/model";

interface ModelConfigTabProps {
  models: ModelConfig[];
  onReload: () => void;
}

export function ModelConfigTab({ models, onReload }: ModelConfigTabProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState<ModelConfig | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

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
  const [showApiKey, setShowApiKey] = useState(false);

  const resetForm = () => {
    setFormValue("");
    setFormLabel("");
    setFormDescription("");
    setFormApiKey("");
    setFormApiBase("");
    setFormTemperature("");
    setFormMaxTokens("");
    setFormMaxInputTokens("");
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
    setShowApiKey(false);
    setIsCreating(false);
  };

  const startCreate = () => {
    resetForm();
    setIsCreating(true);
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
    if (!confirm(t("agentConfig.confirmDeleteModel"))) return;
    setIsDeleting(modelId);
    try {
      await modelApi.delete(modelId);
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
      model.api_key ||
      model.api_base ||
      model.temperature != null ||
      model.max_tokens != null ||
      model.profile?.max_input_tokens != null
    );

  // Show form
  if (isEditing || isCreating) {
    return (
      <div className="space-y-4 sm:space-y-5 animate-glass-enter">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 tracking-tight">
            {isEditing
              ? t("agentConfig.editModel")
              : t("agentConfig.createModel")}
          </h3>
          <button
            onClick={resetForm}
            className="p-2 text-stone-500 hover:text-stone-700 hover:bg-white/40 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
          >
            <X size={20} />
          </button>
        </div>

        <div className="glass-card rounded-xl divide-y glass-divider">
          {/* Basic Info */}
          <div className="p-4 sm:p-5 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.modelValue")} *
                </label>
                <input
                  type="text"
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  disabled={!!isEditing}
                  placeholder={t("agentConfig.modelValuePlaceholder")}
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 disabled:opacity-50 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.modelLabel")} *
                </label>
                <input
                  type="text"
                  value={formLabel}
                  onChange={(e) => setFormLabel(e.target.value)}
                  placeholder={t("agentConfig.modelLabelPlaceholder")}
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                {t("agentConfig.modelDescription")}
              </label>
              <input
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder={t("agentConfig.modelDescriptionPlaceholder")}
                className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
              />
            </div>
          </div>

          {/* API Configuration */}
          <div className="p-4 sm:p-5 space-y-4">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-500 flex items-center gap-2 after:content-[''] after:flex-1 after:h-px after:bg-gradient-to-r after:from-stone-200/60 after:to-transparent dark:after:from-stone-700/40">
              {t("agentConfig.apiConfiguration")}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.modelApiKey")}
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={formApiKey}
                    onChange={(e) => setFormApiKey(e.target.value)}
                    placeholder={t("agentConfig.apiKeyPlaceholder")}
                    className="glass-input w-full px-3.5 py-2.5 pr-10 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-stone-500 hover:text-stone-700 hover:bg-white/50 rounded-md transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
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
                <p className="mt-1.5 text-xs text-stone-500 dark:text-stone-500">
                  {isEditing
                    ? t("agentConfig.apiKeyEditHint")
                    : t("agentConfig.apiKeyHint")}
                </p>
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.modelApiBase")}
                </label>
                <input
                  type="text"
                  value={formApiBase}
                  onChange={(e) => setFormApiBase(e.target.value)}
                  placeholder={t("agentConfig.modelApiBasePlaceholder")}
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
            </div>
          </div>

          {/* Model Parameters */}
          <div className="p-4 sm:p-5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-500 mb-4 flex items-center gap-2 after:content-[''] after:flex-1 after:h-px after:bg-gradient-to-r after:from-stone-200/60 after:to-transparent dark:after:from-stone-700/40">
              {t("agentConfig.parameters")}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
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
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.maxTokens")}
                </label>
                <input
                  type="number"
                  value={formMaxTokens}
                  onChange={(e) => setFormMaxTokens(e.target.value)}
                  placeholder="4096"
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-stone-600 dark:text-stone-400 mb-1.5">
                  {t("agentConfig.maxInputTokens")}
                </label>
                <input
                  type="number"
                  value={formMaxInputTokens}
                  onChange={(e) => setFormMaxInputTokens(e.target.value)}
                  placeholder="200000"
                  className="glass-input w-full px-3.5 py-2.5 text-sm dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-1">
          <button
            onClick={resetForm}
            className="px-4 py-2.5 text-sm font-medium text-stone-600 hover:text-stone-800 hover:bg-white/40 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm"
          >
            {isSaving ? <LoadingSpinner size="sm" /> : <Save size={16} />}
            {t("common.save")}
          </button>
        </div>
      </div>
    );
  }

  // Show list
  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-stone-500 dark:text-stone-400 hidden sm:block">
          {t("agentConfig.modelConfigDescription")}
        </p>
        <button
          onClick={startCreate}
          className="btn-primary flex items-center gap-1.5 px-3 py-2 sm:px-4 text-sm flex-shrink-0 hover:shadow-lg hover:shadow-stone-500/10 transition-shadow duration-200"
        >
          <Plus size={16} />
          <span className="hidden sm:inline">{t("agentConfig.addModel")}</span>
        </button>
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
              overIndex === index && dragIndex !== null && dragIndex !== index;

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
    </div>
  );
}
