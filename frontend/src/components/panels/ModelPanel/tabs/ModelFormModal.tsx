import { useState, useCallback } from "react";
import { Eye, EyeOff, Save, Plus, Pencil } from "lucide-react";
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
import { ProviderSelect } from "../../AgentPanel/shared";
import { modelApi } from "../../../../services/api/model";
import type {
  ApiFormat,
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
  ModelProfile,
  ProviderType,
} from "../../../../services/api/model";
import { ModelIconSelect } from "./ModelIconSelect";
import {
  formatRequestHeaders,
  parseRequestHeadersInput,
} from "./requestHeadersInput";

interface ModelFormModalProps {
  model: ModelConfig | null; // null = creating, non-null = editing
  models: ModelConfig[];
  onClose: () => void;
  onSaved: () => void;
}

export const ModelFormModal = ({
  model,
  models,
  onClose,
  onSaved,
}: ModelFormModalProps) => {
  const { t } = useTranslation();
  const isEditing = model !== null;

  const [formValue, setFormValue] = useState(model?.value || "");
  const [formLabel, setFormLabel] = useState(model?.label || "");
  const [formDescription, setFormDescription] = useState(
    model?.description || "",
  );
  const [formApiKey, setFormApiKey] = useState("");
  const [formApiBase, setFormApiBase] = useState(model?.api_base || "");
  const [formApiFormat, setFormApiFormat] = useState<ApiFormat | "">(
    model?.api_format || "",
  );
  const [formRequestHeaders, setFormRequestHeaders] = useState(
    formatRequestHeaders(model?.request_headers),
  );
  const [formTemperature, setFormTemperature] = useState(
    model?.temperature?.toString() || "",
  );
  const [formMaxTokens, setFormMaxTokens] = useState(
    model?.max_tokens?.toString() || "",
  );
  const [formMaxInputTokens, setFormMaxInputTokens] = useState(
    model?.profile?.max_input_tokens?.toString() || "",
  );
  const [formSupportsVision, setFormSupportsVision] = useState(
    Boolean(model?.profile?.supports_vision),
  );
  const [formImageUrlToBase64, setFormImageUrlToBase64] = useState(
    Boolean(model?.profile?.image_url_to_base64),
  );
  const [formProvider, setFormProvider] = useState(model?.provider || "");
  const [formIcon, setFormIcon] = useState(model?.icon || "");
  const [formFallbackModel, setFormFallbackModel] = useState(
    model?.fallback_model || "",
  );
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const isMaskedApiKey = (key: string) => key.includes("...") || key === "****";

  const handleSave = useCallback(async () => {
    if (!formValue.trim() || !formLabel.trim()) {
      toast.error(t("agentConfig.valueAndLabelRequired"));
      return;
    }

    const temperature = formTemperature
      ? parseFloat(formTemperature)
      : undefined;
    const parsedHeaders = parseRequestHeadersInput(formRequestHeaders);
    if (!parsedHeaders.ok) {
      toast.error(
        parsedHeaders.error === "invalidJson"
          ? t("agentConfig.requestHeadersInvalidJson")
          : t("agentConfig.requestHeadersNotObject"),
      );
      return;
    }
    const maxTokens = formMaxTokens ? parseInt(formMaxTokens, 10) : undefined;
    const maxInputTokens = formMaxInputTokens
      ? parseInt(formMaxInputTokens, 10)
      : undefined;
    const profile: ModelProfile = {
      ...(maxInputTokens ? { max_input_tokens: maxInputTokens } : {}),
      supports_vision: formSupportsVision,
      image_url_to_base64: formImageUrlToBase64,
    };

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
      if (isEditing && model?.id) {
        const update: ModelConfigUpdate = {
          provider: (formProvider || undefined) as ProviderType | undefined,
          icon: formIcon || undefined,
          label: formLabel.trim(),
          description: formDescription.trim() || undefined,
          ...(formApiKey.trim() && !isMaskedApiKey(formApiKey.trim())
            ? { api_key: formApiKey.trim() }
            : {}),
          api_base: formApiBase.trim() || undefined,
          api_format: formApiFormat || "",
          request_headers: parsedHeaders.headers ?? {},
          temperature,
          max_tokens: maxTokens,
          profile,
          fallback_model: formFallbackModel.trim() || undefined,
        };
        await modelApi.update(model.id, update);
        toast.success(t("agentConfig.modelSaveSuccess"));
      } else {
        const data: ModelConfigCreate = {
          value: formValue.trim(),
          provider: (formProvider || undefined) as ProviderType | undefined,
          icon: formIcon || undefined,
          label: formLabel.trim(),
          description: formDescription.trim() || undefined,
          api_key: formApiKey.trim() || undefined,
          api_base: formApiBase.trim() || undefined,
          api_format: formApiFormat || undefined,
          request_headers: parsedHeaders.headers,
          temperature,
          max_tokens: maxTokens,
          profile,
          fallback_model: formFallbackModel.trim() || undefined,
          enabled: true,
        };
        await modelApi.create(data);
        toast.success(t("agentConfig.modelCreateSuccess"));
      }
      onSaved();
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.modelSaveFailed"));
    } finally {
      setIsSaving(false);
    }
  }, [
    formValue,
    formLabel,
    formDescription,
    formApiKey,
    formApiBase,
    formApiFormat,
    formRequestHeaders,
    formTemperature,
    formMaxTokens,
    formMaxInputTokens,
    formSupportsVision,
    formImageUrlToBase64,
    formProvider,
    formIcon,
    formFallbackModel,
    isEditing,
    model,
    t,
    onSaved,
  ]);

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={
        isEditing ? t("agentConfig.editModel") : t("agentConfig.createModel")
      }
      subtitle={
        isEditing
          ? t("agentConfig.editModelDesc", "修改模型配置信息")
          : t("agentConfig.createModelDesc", "添加一个新的模型配置")
      }
      icon={isEditing ? <Pencil size={16} /> : <Plus size={16} />}
      footer={
        <PanelFooterActions>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            loading={isSaving}
            leftIcon={<Save size={16} />}
          >
            {t("common.save")}
          </Button>
        </PanelFooterActions>
      }
    >
      <div className="es-form">
        {/* Basic Info */}
        <div className="es-field">
          <label className="es-label">
            {t("agentConfig.modelValue")} <span className="es-required">*</span>
          </label>
          <Input
            type="text"
            value={formValue}
            onChange={(e) => setFormValue(e.target.value)}
            disabled={isEditing}
            placeholder={t("agentConfig.modelValuePlaceholder")}
            className="es-input disabled:opacity-50"
          />
          <p className="es-hint">
            {isEditing
              ? t("agentConfig.modelValueReadonly", "模型 ID 创建后不可修改")
              : t(
                  "agentConfig.modelValueHint",
                  "例如 anthropic/claude-3-5-sonnet，用于路由到对应的 API",
                )}
          </p>
        </div>
        <div className="es-field">
          <label className="es-label">
            {t("agentConfig.modelLabel")} <span className="es-required">*</span>
          </label>
          <Input
            type="text"
            value={formLabel}
            onChange={(e) => setFormLabel(e.target.value)}
            placeholder={t("agentConfig.modelLabelPlaceholder")}
            className="es-input"
          />
        </div>

        {/* Advanced (collapsed) */}
        <details className="group">
          <summary className="text-xs text-theme-text-secondary cursor-pointer select-none hover:text-theme-text transition-colors py-1">
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
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder={t("agentConfig.modelDescriptionPlaceholder")}
                className="es-input"
              />
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.modelProvider")}
              </label>
              <ProviderSelect
                value={formProvider}
                onChange={setFormProvider}
                placeholder={t("agentConfig.providerAuto")}
              />
              <p className="es-hint">{t("agentConfig.providerHint")}</p>
            </div>
            <div className="es-field">
              <label className="es-label">{t("agentConfig.modelIcon")}</label>
              <ModelIconSelect
                value={formIcon}
                onChange={setFormIcon}
                placeholder={t("agentConfig.iconAuto")}
              />
              <p className="es-hint">{t("agentConfig.iconHint")}</p>
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.fallbackModel", "Fallback Model")}
              </label>
              <Select
                value={formFallbackModel}
                onChange={setFormFallbackModel}
                placeholder={t("agentConfig.noFallback", "None")}
                options={models
                  .filter((m) => m.id !== model?.id && m.enabled)
                  .map((m) => ({
                    value: m.id!,
                    label: `${m.label} (${m.value})`,
                  }))}
              />
              <p className="es-hint">
                {t(
                  "agentConfig.fallbackModelHint",
                  "主模型重试失败后自动切换的备用模型",
                )}
              </p>
            </div>
            <div className="es-field">
              <label className="es-label">{t("agentConfig.modelApiKey")}</label>
              <Input
                type={showApiKey ? "text" : "password"}
                value={formApiKey}
                onChange={(e) => setFormApiKey(e.target.value)}
                placeholder={t("agentConfig.apiKeyPlaceholder")}
                className="es-input"
                trailingSlot={
                  <IconButton
                    icon={showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    onClick={() => setShowApiKey(!showApiKey)}
                    size="sm"
                    aria-label={t("common.toggleVisibility", "切换可见性")}
                  />
                }
              />
              <p className="es-hint">
                {isEditing
                  ? t("agentConfig.apiKeyEditHint")
                  : t("agentConfig.apiKeyHint")}
              </p>
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.modelApiBase")}
              </label>
              <Input
                type="text"
                value={formApiBase}
                onChange={(e) => setFormApiBase(e.target.value)}
                placeholder={t("agentConfig.modelApiBasePlaceholder")}
                className="es-input"
              />
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.modelApiFormat")}
              </label>
              <Select
                value={formApiFormat}
                onChange={(v) => setFormApiFormat(v as ApiFormat | "")}
                options={[
                  { value: "", label: t("agentConfig.apiFormatFollowDefault") },
                  { value: "chat_completions", label: "Chat Completions" },
                  { value: "responses", label: "Responses" },
                ]}
              />
              <p className="es-hint">
                {t("agentConfig.modelApiFormatHint")}
              </p>
            </div>
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.modelRequestHeaders")}
              </label>
              <Textarea
                value={formRequestHeaders}
                onChange={(e) => setFormRequestHeaders(e.target.value)}
                placeholder={t("agentConfig.modelRequestHeadersPlaceholder")}
                className="es-input font-mono text-xs"
                rows={3}
                spellCheck={false}
              />
              <p className="es-hint">
                {t("agentConfig.modelRequestHeadersHint")}
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
                  value={formTemperature}
                  onChange={(e) => setFormTemperature(e.target.value)}
                  placeholder="0.7"
                  className="es-input"
                />
              </div>
              <div className="es-field">
                <label className="es-label">{t("agentConfig.maxTokens")}</label>
                <Input
                  type="number"
                  value={formMaxTokens}
                  onChange={(e) => setFormMaxTokens(e.target.value)}
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
                  value={formMaxInputTokens}
                  onChange={(e) => setFormMaxInputTokens(e.target.value)}
                  placeholder="200000"
                  className="es-input"
                />
              </div>
            </div>
            <div className="es-field">
              <label className="flex items-start gap-2 text-sm text-theme-text cursor-pointer">
                <Checkbox
                  checked={formSupportsVision}
                  onChange={() => setFormSupportsVision((checked) => !checked)}
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
            </div>
            <div className="es-field">
              <label className="flex items-start gap-2 text-sm text-theme-text cursor-pointer">
                <Checkbox
                  checked={formImageUrlToBase64}
                  onChange={() =>
                    setFormImageUrlToBase64((checked) => !checked)
                  }
                  className="mt-1"
                />
                <span>
                  <span className="block font-medium">
                    {t("agentConfig.imageUrlToBase64", "图片链接转 base64")}
                  </span>
                  <span className="es-hint block">
                    {t(
                      "agentConfig.imageUrlToBase64Hint",
                      "发给模型前把 image_url 自动转成 data URL",
                    )}
                  </span>
                </span>
              </label>
            </div>
          </div>
        </details>
      </div>
    </EditorSidebar>
  );
};
