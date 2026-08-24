import { useState, useMemo, useCallback } from "react";
import {
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Upload,
  Check,
  X,
  ListPlus,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { EditorSidebar } from "../../../common/EditorSidebar";
import {
  Button,
  IconButton,
  Input,
  PanelFooterActions,
  Select,
  Textarea,
} from "../../../common";
import { ProviderSelect } from "../../AgentPanel/shared";
import { modelApi } from "../../../../services/api/model";
import type {
  ApiFormat,
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
  const [batchApiFormat, setBatchApiFormat] = useState<ApiFormat | "">("");
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
          api_format: batchApiFormat || undefined,
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
  }, [validBatchRows, batchApiKey, batchApiBase, batchApiFormat, t, onSaved]);

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
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={t("agentConfig.batchCreateTitle")}
      subtitle={t("agentConfig.batchCreateDesc", "快速添加多个模型配置")}
      icon={<ListPlus size={16} />}
      width="wide"
      footer={
        <PanelFooterActions>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          {batchActiveTab === "addOneByOne" ? (
            <Button
              variant="primary"
              onClick={handleBatchCreateRows}
              disabled={batchSaving || validBatchRows.length === 0}
              loading={batchSaving}
              leftIcon={<Upload size={16} />}
            >
              {t("agentConfig.batchCreateBtn", {
                count: validBatchRows.length,
              })}
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleJsonImport}
              disabled={batchSaving || !importValidation.valid}
              loading={batchSaving}
              leftIcon={<Upload size={16} />}
            >
              {t("agentConfig.batchImportBtn")}
            </Button>
          )}
        </PanelFooterActions>
      }
    >
      <div className="flex flex-col h-full">
        {/* Tab bar */}
        <div
          className="flex border-b px-4 sm:px-6"
          style={{ borderColor: "var(--glass-border)" }}
        >
          <button
            onClick={() => {
              setBatchActiveTab("addOneByOne");
              setImportResult(null);
            }}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              batchActiveTab === "addOneByOne"
                ? "border-theme-border text-theme-text"
                : "border-transparent text-theme-text-secondary hover:text-theme-text"
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
                ? "border-theme-border text-theme-text"
                : "border-transparent text-theme-text-secondary hover:text-theme-text"
            }`}
          >
            {t("agentConfig.batchTabJsonImport")}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto es-form">
          {/* Shared Config (Tab 1 only) */}
          {batchActiveTab === "addOneByOne" && (
            <div className="es-section">
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-theme-text-secondary">
                  {t("agentConfig.sharedConfig")}
                </h4>
                <span className="es-chip">
                  {t("agentConfig.optional", "可选")}
                </span>
              </div>
              <p className="es-hint -mt-0.5">
                {t(
                  "agentConfig.sharedConfigHint",
                  "为所有模型统一设置 API 地址和密钥，留空则各模型单独配置",
                )}
              </p>
              <div className="es-row es-row-2">
                <div className="es-field">
                  <label className="es-label">
                    {t("agentConfig.modelApiBase")}
                  </label>
                  <Input
                    type="text"
                    value={batchApiBase}
                    onChange={(e) => setBatchApiBase(e.target.value)}
                    placeholder={t("agentConfig.modelApiBasePlaceholder")}
                    className="es-input"
                  />
                </div>
                <div className="es-field">
                  <label className="es-label">
                    {t("agentConfig.modelApiFormat")}
                  </label>
                  <Select
                    value={batchApiFormat}
                    onChange={(v) => setBatchApiFormat(v as ApiFormat | "")}
                    options={[
                      { value: "", label: t("agentConfig.apiFormatFollowDefault") },
                      { value: "chat_completions", label: "Chat Completions" },
                      { value: "responses", label: "Responses" },
                    ]}
                  />
                </div>
                <div className="es-field">
                  <label className="es-label">
                    {t("agentConfig.modelApiKey")}
                  </label>
                  <Input
                    type={showBatchApiKey ? "text" : "password"}
                    value={batchApiKey}
                    onChange={(e) => setBatchApiKey(e.target.value)}
                    placeholder={t("agentConfig.apiKeyPlaceholder")}
                    className="es-input"
                    trailingSlot={
                      <IconButton
                        icon={
                          showBatchApiKey ? (
                            <EyeOff size={14} />
                          ) : (
                            <Eye size={14} />
                          )
                        }
                        onClick={() => setShowBatchApiKey(!showBatchApiKey)}
                        size="sm"
                        aria-label={t("common.toggleVisibility", "切换可见性")}
                      />
                    }
                  />
                </div>
              </div>
            </div>
          )}

          {/* Tab 1: Add One by One */}
          {batchActiveTab === "addOneByOne" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-theme-text-secondary">
                  {t("agentConfig.batchModelListHint", "* 值 和标签为必填项")}
                </p>
                <span className="text-xs text-theme-text-secondary">
                  {validBatchRows.length > 0 &&
                    `${validBatchRows.length}/${batchRows.length}`}
                </span>
              </div>
              {batchRows.map((row, index) => (
                <div
                  key={row.id}
                  className="glass-card-subtle rounded-xl p-3 sm:p-4 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-theme-text-secondary font-mono">
                      #{index + 1}
                    </span>
                    {batchRows.length > 1 && (
                      <button
                        onClick={() => removeBatchRow(row.id)}
                        className="p-1.5 text-theme-text-secondary hover:text-red-500 rounded-lg transition-colors"
                        title={t("common.delete")}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                  <div className="space-y-2">
                    <div className="es-field">
                      <label className="es-label">
                        {t("agentConfig.modelValue")}{" "}
                        <span className="es-required">*</span>
                      </label>
                      <Input
                        type="text"
                        value={row.value}
                        onChange={(e) =>
                          updateBatchRow(row.id, "value", e.target.value)
                        }
                        placeholder={t("agentConfig.modelValuePlaceholder")}
                        className="es-input"
                      />
                    </div>
                    <div className="es-field">
                      <label className="es-label">
                        {t("agentConfig.modelLabel")}{" "}
                        <span className="es-required">*</span>
                      </label>
                      <Input
                        type="text"
                        value={row.label}
                        onChange={(e) =>
                          updateBatchRow(row.id, "label", e.target.value)
                        }
                        placeholder={t("agentConfig.modelLabelPlaceholder")}
                        className="es-input"
                      />
                    </div>
                  </div>
                  <details className="group">
                    <summary className="text-xs text-theme-text-secondary cursor-pointer select-none hover:text-theme-text transition-colors">
                      {t("agentConfig.advancedConfig", "高级配置")}
                    </summary>
                    <div
                      className="space-y-2 mt-2 pt-2 border-t"
                      style={{ borderColor: "var(--glass-border)" }}
                    >
                      <div className="es-field">
                        <label className="es-label">
                          {t("agentConfig.modelDescription")}
                        </label>
                        <Input
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
                          className="es-input"
                        />
                      </div>
                      <div className="es-field">
                        <label className="es-label">
                          {t("agentConfig.modelProvider")}
                        </label>
                        <ProviderSelect
                          value={row.provider}
                          onChange={(v) =>
                            updateBatchRow(row.id, "provider", v)
                          }
                          placeholder={t("agentConfig.providerAuto")}
                        />
                        <p className="es-hint">
                          {t("agentConfig.providerHint")}
                        </p>
                      </div>
                      <div className="es-row es-row-3">
                        <div className="es-field">
                          <label className="es-label">
                            {t("agentConfig.temperature")}
                          </label>
                          <Input
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
                            className="es-input"
                          />
                        </div>
                        <div className="es-field">
                          <label className="es-label">
                            {t("agentConfig.maxTokens")}
                          </label>
                          <Input
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
                            className="es-input"
                          />
                        </div>
                        <div className="es-field">
                          <label className="es-label">
                            {t("agentConfig.maxInputTokens")}
                          </label>
                          <Input
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
                            className="es-input"
                          />
                        </div>
                      </div>
                    </div>
                  </details>
                </div>
              ))}
              <button
                onClick={addBatchRow}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm text-theme-text-secondary hover:text-theme-text border border-dashed border-theme-border hover:border-theme-text-secondary rounded-xl transition-colors"
              >
                <Plus size={16} />
                {t("agentConfig.batchAddRow")}
              </button>
            </div>
          )}

          {/* Tab 2: JSON Import */}
          {batchActiveTab === "jsonImport" && (
            <div className="space-y-4">
              <div className="es-field">
                <label className="es-label">
                  {t("agentConfig.batchJsonLabel")}
                </label>
                <Textarea
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
                  className="es-textarea font-mono"
                />
                <p className="es-hint">{t("agentConfig.batchJsonHint")}</p>
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
                  {importResult.success ? <Check size={20} /> : <X size={20} />}
                  <span className="whitespace-pre-wrap text-sm">
                    {importResult.message}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </EditorSidebar>
  );
};
