import { useState, useCallback } from "react";
import { Save, Plus, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { EditorSidebar } from "../../../common/EditorSidebar";
import { ProviderSelect } from "../../AgentPanel/shared";
import { modelApi } from "../../../../services/api/model";
import type {
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
  ProviderType,
} from "../../../../services/api/model";

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
  const [formTemperature, setFormTemperature] = useState(
    model?.temperature?.toString() || "",
  );
  const [formMaxTokens, setFormMaxTokens] = useState(
    model?.max_tokens?.toString() || "",
  );
  const [formMaxInputTokens, setFormMaxInputTokens] = useState(
    model?.profile?.max_input_tokens?.toString() || "",
  );
  const [formProvider, setFormProvider] = useState(model?.provider || "");
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
      if (isEditing && model?.id) {
        const update: ModelConfigUpdate = {
          provider: (formProvider || undefined) as ProviderType | undefined,
          label: formLabel.trim(),
          description: formDescription.trim() || undefined,
          ...(formApiKey.trim() && !isMaskedApiKey(formApiKey.trim())
            ? { api_key: formApiKey.trim() }
            : {}),
          api_base: formApiBase.trim() || undefined,
          temperature,
          max_tokens: maxTokens,
          profile: maxInputTokens
            ? { max_input_tokens: maxInputTokens }
            : undefined,
          fallback_model: formFallbackModel.trim() || undefined,
        };
        await modelApi.update(model.id, update);
        toast.success(t("agentConfig.modelSaveSuccess"));
      } else {
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
    formTemperature,
    formMaxTokens,
    formMaxInputTokens,
    formProvider,
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
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">
            {t("common.cancel")}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="btn-primary disabled:opacity-50"
          >
            {isSaving ? <LoadingSpinner size="sm" /> : <Save size={16} />}
            {t("common.save")}
          </button>
        </div>
      }
    >
      <div className="es-form">
        {/* Basic Info */}
        <div className="es-field">
          <label className="es-label">
            {t("agentConfig.modelValue")} <span className="es-required">*</span>
          </label>
          <input
            type="text"
            value={formValue}
            onChange={(e) => setFormValue(e.target.value)}
            disabled={isEditing}
            placeholder={t("agentConfig.modelValuePlaceholder")}
            className="glass-input es-input disabled:opacity-50"
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
          <input
            type="text"
            value={formLabel}
            onChange={(e) => setFormLabel(e.target.value)}
            placeholder={t("agentConfig.modelLabelPlaceholder")}
            className="glass-input es-input px-3"
          />
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
            <div className="es-field">
              <label className="es-label">
                {t("agentConfig.modelDescription")}
              </label>
              <input
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder={t("agentConfig.modelDescriptionPlaceholder")}
                className="glass-input es-input px-3"
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
              <label className="es-label">
                {t("agentConfig.fallbackModel", "Fallback Model")}
              </label>
              <select
                value={formFallbackModel}
                onChange={(e) => setFormFallbackModel(e.target.value)}
                className="glass-input es-select"
              >
                <option value="">{t("agentConfig.noFallback", "None")}</option>
                {models
                  .filter((m) => m.id !== model?.id && m.enabled)
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label} ({m.value})
                    </option>
                  ))}
              </select>
              <p className="es-hint">
                {t(
                  "agentConfig.fallbackModelHint",
                  "主模型重试失败后自动切换的备用模型",
                )}
              </p>
            </div>
            <div className="es-field">
              <label className="es-label">{t("agentConfig.modelApiKey")}</label>
              <div className="relative">
                <input
                  type={showApiKey ? "text" : "password"}
                  value={formApiKey}
                  onChange={(e) => setFormApiKey(e.target.value)}
                  placeholder={t("agentConfig.apiKeyPlaceholder")}
                  className="glass-input es-input pr-10"
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
              <input
                type="text"
                value={formApiBase}
                onChange={(e) => setFormApiBase(e.target.value)}
                placeholder={t("agentConfig.modelApiBasePlaceholder")}
                className="glass-input es-input px-3"
              />
            </div>
            <div className="es-row es-row-3">
              <div className="es-field">
                <label className="es-label">
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
                  className="glass-input es-input px-3"
                />
              </div>
              <div className="es-field">
                <label className="es-label">{t("agentConfig.maxTokens")}</label>
                <input
                  type="number"
                  value={formMaxTokens}
                  onChange={(e) => setFormMaxTokens(e.target.value)}
                  placeholder="4096"
                  className="glass-input es-input px-3"
                />
              </div>
              <div className="es-field">
                <label className="es-label">
                  {t("agentConfig.maxInputTokens")}
                </label>
                <input
                  type="number"
                  value={formMaxInputTokens}
                  onChange={(e) => setFormMaxInputTokens(e.target.value)}
                  placeholder="200000"
                  className="glass-input es-input px-3"
                />
              </div>
            </div>
          </div>
        </details>
      </div>
    </EditorSidebar>
  );
};
