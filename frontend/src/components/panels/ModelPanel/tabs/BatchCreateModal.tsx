import { useState, useMemo, useCallback, useRef, useId } from "react";
import {
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Upload,
  Check,
  X,
  ListPlus,
  FileJson,
  AlertTriangle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { Checkbox } from "../../../common/Checkbox";
import { EditorSidebar } from "../../../common/EditorSidebar";
import {
  Button,
  IconButton,
  Input,
  PanelFooterActions,
  Select,
  Textarea,
} from "../../../common";
import { ConfigPanelErrorCallout } from "../../ConfigPanelErrorCallout";
import { ProviderSelect } from "../../AgentPanel/shared";
import { modelApi } from "../../../../services/api/model";
import type {
  ApiFormat,
  ModelConfigCreate,
} from "../../../../services/api/model";
import { ModelIconSelect } from "./ModelIconSelect";
import { parseRequestHeadersInput } from "./requestHeadersInput";
import {
  buildModelCreateFromRow,
  mergeSharedIntoImported,
  normalizeImportedModels,
  type BatchModelRow,
  type SharedModelConfig,
} from "./batchModelImport";

interface BatchRow extends BatchModelRow {
  id: string;
}

let _rowIdCounter = 0;
const createEmptyBatchRow = (): BatchRow => ({
  id: `row-${++_rowIdCounter}-${Date.now()}`,
  value: "",
  label: "",
  description: "",
  provider: "",
  icon: "",
  apiKey: "",
  apiBase: "",
  temperature: "",
  maxTokens: "",
  maxInputTokens: "",
  supportsVision: false,
  imageUrlToBase64: false,
  priceInput: "",
  priceOutput: "",
  priceCacheRead: "",
  priceCacheWrite: "",
});

interface BatchCreateModalProps {
  initialTab?: "addOneByOne" | "jsonImport";
  onClose: () => void;
  onSaved: () => void;
}

type ImportParseState =
  | null
  | { kind: "invalid" }
  | {
      kind: "ok";
      models: ModelConfigCreate[];
      maskedKeyCount: number;
      skippedCount: number;
    };

const JSON_PLACEHOLDER = `[
  {
    "value": "openai/gpt-4o",
    "label": "GPT-4o",
    "description": "最新的多模态模型",
    "provider": "openai",
    "icon": "openai",
    "api_key": "sk-...",
    "api_base": "https://api.openai.com/v1",
    "api_format": "chat_completions",
    "request_headers": { "X-Custom": "value" },
    "temperature": 0.7,
    "max_tokens": 4096,
    "profile": {
      "max_input_tokens": 128000,
      "supports_vision": true,
      "image_url_to_base64": false
    },
    "pricing": { "input": 2.5, "output": 10 },
    "fallback_model": "<model-id>"
  }
]`;

export const BatchCreateModal = ({
  initialTab = "addOneByOne",
  onClose,
  onSaved,
}: BatchCreateModalProps) => {
  const { t } = useTranslation();
  const formId = useId();
  const [batchActiveTab, setBatchActiveTab] = useState(initialTab);
  const [batchApiKey, setBatchApiKey] = useState("");
  const [batchApiBase, setBatchApiBase] = useState("");
  const [batchApiFormat, setBatchApiFormat] = useState<ApiFormat | "">("");
  const [batchRequestHeaders, setBatchRequestHeaders] = useState("");
  const [showBatchApiKey, setShowBatchApiKey] = useState(false);
  const [batchRows, setBatchRows] = useState<BatchRow[]>([
    createEmptyBatchRow(),
  ]);
  const [importJson, setImportJson] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [batchSaving, setBatchSaving] = useState(false);
  const [isDraggingJson, setIsDraggingJson] = useState(false);
  const jsonFileInputRef = useRef<HTMLInputElement | null>(null);
  const reportError = useCallback((message: string) => {
    setImportError(message);
    toast.error(message);
  }, []);

  const addBatchRow = () =>
    setBatchRows((prev) => [...prev, createEmptyBatchRow()]);
  const removeBatchRow = (rowId: string) => {
    const index = batchRows.findIndex((row) => row.id === rowId);
    const next = batchRows[index + 1] ?? batchRows[index - 1];
    if (next) document.getElementById(`${formId}-${next.id}-value`)?.focus();
    setBatchRows((prev) => prev.filter((r) => r.id !== rowId));
  };
  const updateBatchRow = <K extends keyof BatchModelRow>(
    rowId: string,
    field: K,
    value: BatchModelRow[K],
  ) =>
    setBatchRows((prev) =>
      prev.map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    );

  const validBatchRows = useMemo(
    () => batchRows.filter((r) => r.value.trim() && r.label.trim()),
    [batchRows],
  );

  const parseSharedConfig = useCallback(():
    | { ok: true; shared: SharedModelConfig }
    | { ok: false; error: "invalidHeaders" } => {
    const parsedHeaders = parseRequestHeadersInput(batchRequestHeaders);
    if (!parsedHeaders.ok) return { ok: false, error: "invalidHeaders" };
    return {
      ok: true,
      shared: {
        apiKey: batchApiKey,
        apiBase: batchApiBase,
        apiFormat: batchApiFormat,
        requestHeaders: parsedHeaders.headers,
      },
    };
  }, [batchApiKey, batchApiBase, batchApiFormat, batchRequestHeaders]);

  const handleBatchCreateRows = useCallback(async () => {
    if (validBatchRows.length === 0) {
      reportError(t("agentConfig.batchNoModels"));
      return;
    }
    const parsedShared = parseSharedConfig();
    if (!parsedShared.ok) {
      reportError(
        parsedShared.error === "invalidHeaders"
          ? t("agentConfig.requestHeadersInvalidJson")
          : t("agentConfig.requestHeadersNotObject"),
      );
      return;
    }
    const models: ModelConfigCreate[] = [];
    for (const row of validBatchRows) {
      const built = buildModelCreateFromRow(row, parsedShared.shared);
      if (!built.ok) {
        reportError(t(`agentConfig.${built.error}`));
        return;
      }
      models.push(built.model);
    }
    setBatchSaving(true);
    setImportError(null);
    try {
      await modelApi.importModels(models);
      toast.success(
        t("agentConfig.batchCreateSuccess", { count: models.length }),
      );
      onSaved();
    } catch (err) {
      const msg = (err as Error).message || t("agentConfig.batchCreateFailed");
      reportError(msg);
    } finally {
      setBatchSaving(false);
    }
  }, [validBatchRows, parseSharedConfig, t, onSaved, reportError]);

  const importParse = useMemo<ImportParseState>(() => {
    if (!importJson.trim()) return null;
    try {
      const parsed: unknown = JSON.parse(importJson);
      if (!Array.isArray(parsed)) return { kind: "invalid" };
      const normalized = normalizeImportedModels(parsed);
      if (normalized.models.length === 0) return { kind: "invalid" };
      return { kind: "ok", ...normalized };
    } catch {
      return { kind: "invalid" };
    }
  }, [importJson]);

  const readJsonFile = useCallback(
    async (file: File) => {
      try {
        const text = await file.text();
        setImportJson(text);
        setImportError(null);
      } catch {
        const msg = t("agentConfig.batchFileReadFailed");
        reportError(msg);
      }
    },
    [t, reportError],
  );

  const handleJsonImport = useCallback(async () => {
    if (importParse?.kind !== "ok") {
      reportError(t("agentConfig.importInvalidFormat"));
      return;
    }
    const parsedShared = parseSharedConfig();
    if (!parsedShared.ok) {
      reportError(
        parsedShared.error === "invalidHeaders"
          ? t("agentConfig.requestHeadersInvalidJson")
          : t("agentConfig.requestHeadersNotObject"),
      );
      return;
    }
    const models = importParse.models.map((m) =>
      mergeSharedIntoImported(m, parsedShared.shared),
    );
    setBatchSaving(true);
    setImportError(null);
    try {
      await modelApi.importModels(models);
      toast.success(
        t("agentConfig.batchCreateSuccess", { count: models.length }),
      );
      onSaved();
    } catch (err) {
      const msg = (err as Error).message || t("agentConfig.batchCreateFailed");
      reportError(msg);
    } finally {
      setBatchSaving(false);
    }
  }, [importParse, parseSharedConfig, t, onSaved, reportError]);

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={t("agentConfig.batchCreateTitle")}
      subtitle={t("agentConfig.batchCreateDesc", "快速添加多个模型配置")}
      icon={<ListPlus size={16} />}
      width="wide"
      footer={
        <div className="space-y-2">
          {importError && (
            <ConfigPanelErrorCallout
              message={importError}
              tabIndex={0}
              className="max-h-32 overflow-y-auto"
            />
          )}
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
                disabled={batchSaving || importParse?.kind !== "ok"}
                loading={batchSaving}
                leftIcon={<Upload size={16} />}
              >
                {t("agentConfig.batchImportBtn")}
              </Button>
            )}
          </PanelFooterActions>
        </div>
      }
    >
      <div
        className="flex flex-col h-full"
        data-disable-global-file-drop="true"
      >
        {/* Tab bar */}
        <div
          className="flex border-b px-4 sm:px-6"
          style={{ borderColor: "var(--glass-border)" }}
        >
          <button
            type="button"
            aria-pressed={batchActiveTab === "addOneByOne"}
            onClick={() => {
              setBatchActiveTab("addOneByOne");
              setImportError(null);
            }}
            className={`min-h-11 min-w-0 flex-1 px-3 py-3 text-14 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] motion-reduce:transition-none font-medium border-b-2 transition-colors ${
              batchActiveTab === "addOneByOne"
                ? "border-theme-border text-theme-text"
                : "border-transparent text-theme-text-secondary hover:text-theme-text"
            }`}
          >
            {t("agentConfig.batchTabAddOneByOne")}
          </button>
          <button
            type="button"
            aria-pressed={batchActiveTab === "jsonImport"}
            onClick={() => {
              setBatchActiveTab("jsonImport");
              setImportError(null);
            }}
            className={`min-h-11 min-w-0 flex-1 px-3 py-3 text-14 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] motion-reduce:transition-none font-medium border-b-2 transition-colors ${
              batchActiveTab === "jsonImport"
                ? "border-theme-border text-theme-text"
                : "border-transparent text-theme-text-secondary hover:text-theme-text"
            }`}
          >
            {t("agentConfig.batchTabJsonImport")}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto es-form">
          {/* Shared Config — 两个 Tab 共用：只补齐各模型缺失的连接信息 */}
          <div className="es-section">
            <div className="flex items-center gap-2">
              <h4 className="text-12 font-semibold uppercase tracking-wider text-theme-text-secondary">
                {t("agentConfig.sharedConfig")}
              </h4>
              <span className="es-chip">
                {t("agentConfig.optional", "可选")}
              </span>
            </div>
            <p className="es-hint -mt-0.5">
              {t(
                "agentConfig.sharedConfigHint",
                "为所有模型统一设置 API 地址、密钥与请求头；各模型已有配置优先，缺失项由共享配置补齐",
              )}
            </p>
            <div className="es-row es-row-2">
              <div className="es-field">
                <label className="es-label" htmlFor={`${formId}-base`}>
                  {t("agentConfig.modelApiBase")}
                </label>
                <Input
                  id={`${formId}-base`}
                  type="text"
                  value={batchApiBase}
                  onChange={(e) => setBatchApiBase(e.target.value)}
                  placeholder={t("agentConfig.modelApiBasePlaceholder")}
                  className="es-input"
                />
              </div>
              <div className="es-field">
                <span className="es-label">
                  {t("agentConfig.modelApiFormat")}
                </span>
                <Select
                  ariaLabel={t("agentConfig.modelApiFormat")}
                  value={batchApiFormat}
                  onChange={(v) => setBatchApiFormat(v as ApiFormat | "")}
                  options={[
                    {
                      value: "",
                      label: t("agentConfig.apiFormatFollowDefault"),
                    },
                    { value: "chat_completions", label: "Chat Completions" },
                    { value: "responses", label: "Responses" },
                  ]}
                />
                <p className="es-hint">{t("agentConfig.modelApiFormatHint")}</p>
              </div>
              <div className="es-field">
                <label className="es-label" htmlFor={`${formId}-key`}>
                  {t("agentConfig.modelApiKey")}
                </label>
                <Input
                  id={`${formId}-key`}
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
            <div className="es-field">
              <label className="es-label" htmlFor={`${formId}-headers`}>
                {t("agentConfig.modelRequestHeaders")}
              </label>
              <Textarea
                id={`${formId}-headers`}
                value={batchRequestHeaders}
                onChange={(e) => setBatchRequestHeaders(e.target.value)}
                placeholder={t("agentConfig.modelRequestHeadersPlaceholder")}
                className="es-input font-mono text-12"
                rows={3}
                spellCheck={false}
              />
              <p className="es-hint">
                {t("agentConfig.modelRequestHeadersHint")}
              </p>
            </div>
          </div>

          {/* Tab 1: Add One by One */}
          {batchActiveTab === "addOneByOne" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-12 text-theme-text-secondary">
                  {t("agentConfig.batchModelListHint", "* 值 和标签为必填项")}
                </p>
                <span className="text-12 text-theme-text-secondary">
                  {validBatchRows.length > 0 &&
                    `${validBatchRows.length}/${batchRows.length}`}
                </span>
              </div>
              {batchRows.map((row, index) => (
                <div
                  key={row.id}
                  role="group"
                  aria-labelledby={`${formId}-${row.id}-title`}
                  className="glass-card-subtle rounded-xl p-3 sm:p-4 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span
                      id={`${formId}-${row.id}-title`}
                      className="text-12 text-theme-text-secondary font-mono"
                    >
                      #{index + 1}
                    </span>
                    {batchRows.length > 1 && (
                      <IconButton
                        onClick={() => removeBatchRow(row.id)}
                        icon={<Trash2 size={16} />}
                        aria-label={`${t("common.delete")} #${index + 1}`}
                      />
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div className="es-field">
                      <label
                        className="es-label"
                        htmlFor={`${formId}-${row.id}-value`}
                      >
                        {t("agentConfig.modelValue")}{" "}
                        <span className="es-required">*</span>
                      </label>
                      <Input
                        id={`${formId}-${row.id}-value`}
                        aria-required="true"
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
                      <label
                        className="es-label"
                        htmlFor={`${formId}-${row.id}-label`}
                      >
                        {t("agentConfig.modelLabel")}{" "}
                        <span className="es-required">*</span>
                      </label>
                      <Input
                        id={`${formId}-${row.id}-label`}
                        aria-required="true"
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
                    <summary className="min-h-11 content-center rounded-lg focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] motion-reduce:transition-none text-12 text-theme-text-secondary cursor-pointer select-none hover:text-theme-text transition-colors">
                      {t("agentConfig.advancedConfig", "高级配置")}
                    </summary>
                    <div
                      className="space-y-2 mt-2 pt-2 border-t"
                      style={{ borderColor: "var(--glass-border)" }}
                    >
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="es-field">
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-description`}
                          >
                            {t("agentConfig.modelDescription")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-description`}
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
                          <span className="es-label">
                            {t("agentConfig.modelProvider")}
                          </span>
                          <ProviderSelect
                            value={row.provider}
                            onChange={(v) =>
                              updateBatchRow(row.id, "provider", v)
                            }
                            placeholder={t("agentConfig.providerAuto")}
                          />
                        </div>
                      </div>
                      <div className="es-field">
                        <span className="es-label">
                          {t("agentConfig.modelIcon")}
                        </span>
                        <ModelIconSelect
                          value={row.icon}
                          onChange={(v) => updateBatchRow(row.id, "icon", v)}
                          placeholder={t("agentConfig.iconAuto")}
                        />
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="es-field">
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-apiKey`}
                          >
                            {t("agentConfig.modelApiKey")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-apiKey`}
                            type="text"
                            value={row.apiKey}
                            onChange={(e) =>
                              updateBatchRow(row.id, "apiKey", e.target.value)
                            }
                            placeholder={t("agentConfig.apiKeyPlaceholder")}
                            className="es-input"
                          />
                          <p className="es-hint">
                            {t("agentConfig.batchRowOverrideHint")}
                          </p>
                        </div>
                        <div className="es-field">
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-apiBase`}
                          >
                            {t("agentConfig.modelApiBase")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-apiBase`}
                            type="text"
                            value={row.apiBase}
                            onChange={(e) =>
                              updateBatchRow(row.id, "apiBase", e.target.value)
                            }
                            placeholder={t(
                              "agentConfig.modelApiBasePlaceholder",
                            )}
                            className="es-input"
                          />
                          <p className="es-hint">
                            {t("agentConfig.batchRowOverrideHint")}
                          </p>
                        </div>
                      </div>
                      <div className="es-row es-row-3">
                        <div className="es-field">
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-temperature`}
                          >
                            {t("agentConfig.temperature")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-temperature`}
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
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-maxTokens`}
                          >
                            {t("agentConfig.maxTokens")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-maxTokens`}
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
                          <label
                            className="es-label"
                            htmlFor={`${formId}-${row.id}-maxInputTokens`}
                          >
                            {t("agentConfig.maxInputTokens")}
                          </label>
                          <Input
                            id={`${formId}-${row.id}-maxInputTokens`}
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
                      <div className="es-field">
                        <span className="es-label">
                          {t(
                            "agentConfig.pricingLabel",
                            "价格覆盖（USD / 百万 tokens）",
                          )}
                        </span>
                        <div className="grid grid-cols-2 gap-2">
                          {(
                            [
                              ["priceInput", "pricingInput"],
                              ["priceOutput", "pricingOutput"],
                              ["priceCacheRead", "pricingCacheRead"],
                              ["priceCacheWrite", "pricingCacheWrite"],
                            ] as const
                          ).map(([field, labelKey]) => (
                            <div key={field} className="es-field">
                              <label
                                className="es-label"
                                htmlFor={`${formId}-${row.id}-${field}`}
                              >
                                {t(`agentConfig.${labelKey}`)}
                              </label>
                              <Input
                                id={`${formId}-${row.id}-${field}`}
                                type="text"
                                inputMode="decimal"
                                value={row[field]}
                                onChange={(e) =>
                                  updateBatchRow(row.id, field, e.target.value)
                                }
                                className="es-input"
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <label className="flex items-start gap-2 text-14 text-theme-text cursor-pointer">
                          <Checkbox
                            ariaLabel={t("agentConfig.supportsVision")}
                            checked={row.supportsVision}
                            onChange={() =>
                              updateBatchRow(
                                row.id,
                                "supportsVision",
                                !row.supportsVision,
                              )
                            }
                            className="mt-1"
                          />
                          <span>
                            <span className="block font-medium">
                              {t("agentConfig.supportsVision")}
                            </span>
                            <span className="es-hint block">
                              {t("agentConfig.supportsVisionHint")}
                            </span>
                          </span>
                        </label>
                        <label className="flex items-start gap-2 text-14 text-theme-text cursor-pointer">
                          <Checkbox
                            ariaLabel={t("agentConfig.imageUrlModeBase64")}
                            checked={row.imageUrlToBase64}
                            onChange={() =>
                              updateBatchRow(
                                row.id,
                                "imageUrlToBase64",
                                !row.imageUrlToBase64,
                              )
                            }
                            className="mt-1"
                          />
                          <span>
                            <span className="block font-medium">
                              {t("agentConfig.imageUrlModeBase64")}
                            </span>
                            <span className="es-hint block">
                              {t("agentConfig.imageUrlModeHint")}
                            </span>
                          </span>
                        </label>
                      </div>
                    </div>
                  </details>
                </div>
              ))}
              <Button
                variant="ghost"
                leftIcon={<Plus size={16} />}
                onClick={addBatchRow}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 text-14 text-theme-text-secondary hover:text-theme-text border border-dashed border-theme-border hover:border-theme-text-secondary rounded-xl transition-colors"
              >
                {t("agentConfig.batchAddRow")}
              </Button>
            </div>
          )}

          {/* Tab 2: JSON / File Import */}
          {batchActiveTab === "jsonImport" && (
            <div className="space-y-4">
              <button
                type="button"
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDraggingJson(true);
                }}
                onDragLeave={() => setIsDraggingJson(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDraggingJson(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) void readJsonFile(file);
                }}
                onClick={() => jsonFileInputRef.current?.click()}
                className={`w-full flex cursor-pointer flex-col focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] motion-reduce:transition-none items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 transition-colors ${
                  isDraggingJson
                    ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]/40"
                    : "border-[var(--glass-border)] hover:border-theme-text-secondary"
                }`}
              >
                <FileJson size={20} className="text-theme-text-secondary" />
                <span className="text-14 text-theme-text">
                  {isDraggingJson
                    ? t("agentConfig.batchDropzoneActive")
                    : t("agentConfig.batchDropzoneTitle")}
                </span>
                <span className="text-12 text-theme-text-secondary">
                  {t("agentConfig.batchDropzoneHint")}
                </span>
              </button>
              <input
                ref={jsonFileInputRef}
                type="file"
                aria-label={t("agentConfig.batchDropzoneTitle")}
                accept=".json,application/json"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void readJsonFile(file);
                  e.target.value = "";
                }}
                className="hidden"
              />
              <div className="es-field">
                <label className="es-label" htmlFor={`${formId}-json`}>
                  {t("agentConfig.batchJsonLabel")}
                </label>
                <Textarea
                  id={`${formId}-json`}
                  aria-invalid={importParse?.kind === "invalid"}
                  aria-describedby={
                    importParse ? `${formId}-json-status` : undefined
                  }
                  value={importJson}
                  onChange={(e) => {
                    setImportJson(e.target.value);
                    setImportError(null);
                  }}
                  rows={10}
                  placeholder={JSON_PLACEHOLDER}
                  className="es-textarea font-mono"
                  spellCheck={false}
                />
                <p className="es-hint">{t("agentConfig.batchJsonHint")}</p>
              </div>
              {importParse && (
                <div
                  id={`${formId}-json-status`}
                  role="status"
                  className={`rounded-xl p-3 text-14 flex items-center gap-2 ${
                    importParse.kind === "ok"
                      ? "bg-[color-mix(in_srgb,var(--theme-success)_12%,transparent)] text-theme-success dark:bg-green-900/30 dark:text-green-400"
                      : "bg-[color-mix(in_srgb,var(--theme-error)_12%,transparent)] text-theme-error dark:bg-red-900/30 dark:text-red-400"
                  }`}
                >
                  {importParse.kind === "ok" ? (
                    <Check size={16} />
                  ) : (
                    <X size={16} />
                  )}
                  {importParse.kind === "ok"
                    ? t("agentConfig.batchJsonPreview", {
                        count: importParse.models.length,
                      })
                    : t("agentConfig.batchJsonError")}
                </div>
              )}
              {importParse?.kind === "ok" && importParse.maskedKeyCount > 0 && (
                <div className="rounded-xl p-3 text-12 flex items-start gap-2 bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  {t("agentConfig.batchMaskedKeyWarning", {
                    count: importParse.maskedKeyCount,
                  })}
                </div>
              )}
              {importParse?.kind === "ok" && importParse.skippedCount > 0 && (
                <div className="rounded-xl p-3 text-12 flex items-start gap-2 bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  {t("agentConfig.batchSkippedWarning", {
                    count: importParse.skippedCount,
                  })}
                </div>
              )}
              {importParse?.kind === "ok" && (
                <div
                  className="rounded-xl p-3 space-y-1"
                  style={{ backgroundColor: "var(--glass-bg-subtle)" }}
                >
                  {importParse.models.slice(0, 8).map((m) => (
                    <div
                      key={`${m.provider ?? ""}/${m.value}`}
                      className="text-12 font-mono text-theme-text-secondary truncate"
                    >
                      {m.value} → {m.label}
                    </div>
                  ))}
                  {importParse.models.length > 8 && (
                    <div className="text-12 text-theme-text-secondary">
                      {t("agentConfig.batchPreviewMore", {
                        count: importParse.models.length - 8,
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </EditorSidebar>
  );
};
