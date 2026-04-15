import React, { useState, useRef, useCallback } from "react";
import {
  Cpu,
  Plus,
  Trash2,
  Edit2,
  GripVertical,
  Download,
  FileJson,
  Layers,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ConfirmDialog } from "../../../common";
import { ToggleSwitch } from "../../AgentPanel/shared";
import { ModelIconImg } from "../../../agent/modelIcon.tsx";
import { modelApi } from "../../../../services/api";
import type { ModelConfig } from "../../../../services/api/model";
import { ModelFormModal } from "./ModelFormModal";
import { BatchCreateModal } from "./BatchCreateModal";

interface ModelConfigTabProps {
  models: ModelConfig[];
  onReload: () => void;
}

// ---- Tags helper (pure function, no React dependency) ----

function renderModelTags(model: ModelConfig, compact: boolean) {
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
}

function modelHasTags(model: ModelConfig) {
  return !!(
    model.provider ||
    model.api_key ||
    model.api_base ||
    model.temperature != null ||
    model.max_tokens != null ||
    model.profile?.max_input_tokens != null
  );
}

// ---- Extracted memoized model card component ----

interface ModelCardProps {
  model: ModelConfig;
  index: number;
  isDragging: boolean;
  isDragOver: boolean;
  isDeleting: boolean;
  onToggle: (model: ModelConfig) => void;
  onEdit: (model: ModelConfig) => void;
  onDelete: (modelId: string) => void;
  onDragStart: (index: number, e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver: (index: number, e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

const ModelCard = React.memo(function ModelCard({
  model,
  index,
  isDragging,
  isDragOver,
  isDeleting,
  onToggle,
  onEdit,
  onDelete,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDragEnd,
  t,
}: ModelCardProps) {
  const handleDragLeave = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) {
        onDragLeave(e);
      }
    },
    [onDragLeave],
  );

  const handleToggle = useCallback(() => onToggle(model), [onToggle, model]);
  const handleEdit = useCallback(() => onEdit(model), [onEdit, model]);
  const handleDelete = useCallback(
    () => model.id && onDelete(model.id),
    [onDelete, model.id],
  );

  const hasTags = modelHasTags(model);

  return (
    <div
      key={model.id}
      draggable
      onDragStart={(e) => onDragStart(index, e)}
      onDragOver={(e) => onDragOver(index, e)}
      onDragLeave={handleDragLeave}
      onDragEnd={onDragEnd}
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
            onToggle={handleToggle}
            ariaLabel={
              model.enabled ? t("agentConfig.disable") : t("agentConfig.enable")
            }
          />
        </div>
        <div className="text-xs font-mono text-stone-400 dark:text-stone-500 truncate mb-2">
          {model.value}
        </div>
        {hasTags && (
          <div className="flex flex-wrap gap-1 mb-2.5">
            {renderModelTags(model, true)}
          </div>
        )}
        <div className="flex items-center gap-1 justify-end -mr-1">
          <button
            onClick={handleEdit}
            className="p-2 text-stone-500 hover:text-stone-700 hover:bg-white/50 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
            title={t("agentConfig.edit")}
          >
            <Edit2 size={16} />
          </button>
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50/60 rounded-lg transition-all duration-200 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20 disabled:opacity-50"
            title={t("agentConfig.delete")}
          >
            {isDeleting ? <LoadingSpinner size="sm" /> : <Trash2 size={16} />}
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
              onToggle={handleToggle}
              ariaLabel={
                model.enabled
                  ? t("agentConfig.disable")
                  : t("agentConfig.enable")
              }
            />
            <button
              onClick={handleEdit}
              className="p-2 text-stone-500 hover:text-stone-700 hover:bg-white/50 rounded-lg transition-all duration-200 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/40"
              title={t("agentConfig.edit")}
            >
              <Edit2 size={16} />
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50/60 rounded-lg transition-all duration-200 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20 disabled:opacity-50"
              title={t("agentConfig.delete")}
            >
              {isDeleting ? <LoadingSpinner size="sm" /> : <Trash2 size={16} />}
            </button>
          </div>
        </div>

        {/* Details row */}
        {(model.description || hasTags) && (
          <div className="px-4 pb-4 pt-0">
            <div className="glass-card-subtle rounded-lg px-3 py-2.5">
              {model.description && (
                <p className="text-xs text-stone-500 dark:text-stone-400 mb-2">
                  {model.description}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {renderModelTags(model, false)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export function ModelConfigTab({ models, onReload }: ModelConfigTabProps) {
  const { t } = useTranslation();

  // Modal state — only these booleans, all form state lives inside the modal components
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [batchInitialTab, setBatchInitialTab] = useState<
    "addOneByOne" | "jsonImport"
  >("addOneByOne");

  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // Drag-and-drop state
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const dragNode = useRef<HTMLDivElement | null>(null);

  // Export models as JSON
  const handleExportModels = useCallback(() => {
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
  }, [models]);

  const handleDelete = useCallback((modelId: string) => {
    setDeleteTarget(modelId);
  }, []);

  const confirmDelete = useCallback(async () => {
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
  }, [deleteTarget, t, onReload]);

  const handleToggle = useCallback(
    async (model: ModelConfig) => {
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
        toast.error(
          (err as Error).message || t("agentConfig.modelToggleFailed"),
        );
      }
    },
    [t, onReload],
  );

  // ---- Drag-and-drop handlers ----

  const handleDragStart = useCallback(
    (index: number, e: React.DragEvent<HTMLDivElement>) => {
      setDragIndex(index);
      dragNode.current = e.currentTarget;
      requestAnimationFrame(() => {
        if (dragNode.current) {
          dragNode.current.style.opacity = "0.4";
        }
      });
    },
    [],
  );

  const handleDragOver = useCallback(
    (index: number, e: React.DragEvent) => {
      e.preventDefault();
      if (dragIndex === null || dragIndex === index) return;
      setOverIndex(index);
    },
    [dragIndex],
  );

  const handleDragEnd = useCallback(async () => {
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
  }, [dragIndex, overIndex, models, onReload]);

  const handleDragLeave = useCallback(() => setOverIndex(null), []);

  // Modal callbacks
  const handleFormSaved = useCallback(() => {
    setEditingModel(null);
    setIsCreating(false);
    onReload();
  }, [onReload]);

  const handleBatchSaved = useCallback(() => {
    setShowBatchModal(false);
    onReload();
  }, [onReload]);

  const handleBatchClosed = useCallback(() => {
    setShowBatchModal(false);
  }, []);

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
                setBatchInitialTab("jsonImport");
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
                setBatchInitialTab("addOneByOne");
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
              onClick={() => setIsCreating(true)}
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
            <button
              onClick={() => setIsCreating(true)}
              className="skill-empty-state__action"
            >
              <Plus size={14} />
              {t("agentConfig.addFirstModel")}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {models.map((model, index) => (
              <ModelCard
                key={model.id}
                model={model}
                index={index}
                isDragging={dragIndex === index}
                isDragOver={
                  overIndex === index &&
                  dragIndex !== null &&
                  dragIndex !== index
                }
                isDeleting={isDeleting === model.id}
                onToggle={handleToggle}
                onEdit={setEditingModel}
                onDelete={handleDelete}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDragEnd={handleDragEnd}
                t={t}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create / Edit Modal — isolated component, form state lives here */}
      {(editingModel || isCreating) && (
        <ModelFormModal
          model={editingModel}
          models={models}
          onClose={() => {
            setEditingModel(null);
            setIsCreating(false);
          }}
          onSaved={handleFormSaved}
        />
      )}

      {/* Batch Create Modal — isolated component, batch state lives here */}
      {showBatchModal && (
        <BatchCreateModal
          initialTab={batchInitialTab}
          onClose={handleBatchClosed}
          onSaved={handleBatchSaved}
        />
      )}

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
