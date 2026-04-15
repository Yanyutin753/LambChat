import { useState, useMemo, useCallback } from "react";
import { Plus, Trash2, X, Upload, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ProviderSelect } from "../../AgentPanel/shared";
import { modelApi } from "../../../../services/api";
import type {
  ModelConfigCreate,
  ProviderType,
} from "../../../../services/api/model";

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

interface BatchCreateModalProps {
  initialTab?: "addOneByOne" | "jsonImport";
  onClose: () => void;
  onSaved: () => void;
}

export const BatchCreateModal = ({
  initialTab = "addOneByOne",
  onClose,
  onSaved,
}: BatchCreateModalProps) => {
  const { t } = useTranslation();
  const [batchActiveTab, setBatchActiveTab] = useState(initialTab);
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

  const validBatchRows = useMemo(
    () => batchRows.filter((r) => r.value.trim() && r.label.trim()),
    [batchRows],
  );

  const handleBatchCreateRows = useCallback(async () => {
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
      onSaved();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.batchCreateFailed"));
    } finally {
      setBatchSaving(false);
    }
  }, [validBatchRows, batchApiKey, batchApiBase, t, onSaved]);

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

  const handleJsonImport = useCallback(async () => {
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
      onSaved();
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err) {
      const msg = (err as Error).message || t("agentConfig.batchCreateFailed");
      setImportResult({ success: false, message: msg });
      toast.error(msg);
    } finally {
      setBatchSaving(false);
    }
  }, [importValidation, importJson, t, onSaved, onClose]);

  return (
    <>
      <div
        className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
        onClick={onClose}
      />
      <div
        className="modal-bottom-sheet sm:modal-centered-wrapper"
        onClick={onClose}
      >
        <div
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-3xl max-h-[85vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
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
            <button onClick={onClose} className="btn-icon">
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
                      placeholder={t("agentConfig.modelApiBasePlaceholder")}
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
                        onClick={() => setShowBatchApiKey(!showBatchApiKey)}
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
                    {t("agentConfig.batchModelListHint", "* 值 和标签为必填项")}
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
                            updateBatchRow(row.id, "value", e.target.value)
                          }
                          placeholder={t("agentConfig.modelValuePlaceholder")}
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
                            updateBatchRow(row.id, "label", e.target.value)
                          }
                          placeholder={t("agentConfig.modelLabelPlaceholder")}
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
            <button onClick={onClose} className="btn-secondary">
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
                <span className="inline-flex items-center justify-center gap-2">
                  <span className="inline-flex h-4 w-4 items-center justify-center">
                    {batchSaving ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <Upload size={16} />
                    )}
                  </span>
                  <span>{t("agentConfig.batchImportBtn")}</span>
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
};
