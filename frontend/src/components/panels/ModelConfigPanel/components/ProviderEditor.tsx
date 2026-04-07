/**
 * Provider editor card component
 */
import { useState, useEffect } from "react";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  Globe,
  Key,
  LayoutGrid,
  Sparkles,
  Save,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderBadge } from "./ProviderBadge";
import { ModelEditor } from "./ModelEditor";
import type { ModelProviderConfig, ModelConfig } from "../../../../types";

interface ProviderEditorProps {
  provider: ModelProviderConfig;
  onUpdate: (updated: ModelProviderConfig) => void;
  onDelete: () => void;
}

export function ProviderEditor({
  provider,
  onUpdate,
  onDelete,
}: ProviderEditorProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);
  const [localProvider, setLocalProvider] = useState(provider);

  useEffect(() => {
    setLocalProvider(provider);
  }, [provider]);

  const updateModel = (index: number, updated: ModelConfig) => {
    const newModels = [...localProvider.models];
    newModels[index] = updated;
    setLocalProvider({ ...localProvider, models: newModels });
  };

  const addModel = () => {
    const newModel: ModelConfig = {
      value: "",
      label: "",
      description: "",
      enabled: true,
    };
    setLocalProvider({
      ...localProvider,
      models: [...localProvider.models, newModel],
    });
  };

  const removeModel = (index: number) => {
    setLocalProvider({
      ...localProvider,
      models: localProvider.models.filter(
        (_: ModelConfig, i: number) => i !== index,
      ),
    });
  };

  const hasChanges =
    JSON.stringify(localProvider) !== JSON.stringify(provider) ||
    localProvider.models.length !== provider.models.length;

  return (
    <div
      className="rounded-2xl overflow-hidden transition-all duration-200"
      style={{
        background: "var(--theme-bg-card)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
        border: "1px solid var(--theme-border)",
      }}
    >
      {/* Provider Header */}
      <div
        className="flex items-center gap-4 p-5"
        style={{ background: "var(--theme-bg)" }}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-200 transition-colors p-1 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800"
        >
          {expanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        </button>

        <ProviderBadge provider={localProvider.provider} />

        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="min-w-0 flex-1">
            <input
              type="text"
              value={localProvider.label}
              onChange={(e) =>
                setLocalProvider({ ...localProvider, label: e.target.value })
              }
              className="w-full bg-transparent text-base font-semibold outline-none border-b-2 border-transparent focus:border-stone-400 dark:focus:border-stone-500 transition-colors"
              style={{ color: "var(--theme-text)" }}
              placeholder={t("modelConfig.providerLabelPlaceholder")}
            />
            <div className="flex items-center gap-2 mt-1.5">
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  backgroundColor: "var(--theme-primary-light)",
                  color: "var(--theme-primary)",
                }}
              >
                {localProvider.provider}
              </span>
              {localProvider.models.length > 0 && (
                <span
                  className="text-xs"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {localProvider.models.length} models
                </span>
              )}
            </div>
          </div>
        </div>

        <button
          onClick={onDelete}
          className="flex-shrink-0 p-2.5 text-stone-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
          title={t("modelConfig.deleteProvider")}
        >
          <Trash2 size={18} />
        </button>
      </div>

      {/* Provider Fields */}
      {expanded && (
        <div
          className="p-5 space-y-5"
          style={{ borderTop: "1px solid var(--theme-border)" }}
        >
          {/* Provider type and credentials */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <LayoutGrid size={14} />
                {t("modelConfig.provider")}
              </label>
              <select
                value={localProvider.provider}
                onChange={(e) =>
                  setLocalProvider({
                    ...localProvider,
                    provider: e.target.value,
                  })
                }
                className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-colors"
                style={{
                  border: "1px solid var(--theme-border)",
                  background: "var(--theme-bg-card)",
                  color: "var(--theme-text)",
                }}
              >
                <option value="anthropic">Anthropic</option>
                <option value="google">Google Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="azure">Azure OpenAI</option>
                <option value="bedrock">AWS Bedrock</option>
                <option value="groq">Groq</option>
                <option value="deepseek">DeepSeek</option>
                <option value="mistral">Mistral AI</option>
                <option value="cohere">Cohere</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="minimax">Minimax</option>
                <option value="zai">ZAI</option>
              </select>
            </div>

            <div className="space-y-2">
              <label
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Globe size={14} />
                {t("modelConfig.baseUrl")}
              </label>
              <input
                type="text"
                value={localProvider.base_url || ""}
                onChange={(e) =>
                  setLocalProvider({
                    ...localProvider,
                    base_url: e.target.value || undefined,
                  })
                }
                className="w-full rounded-xl px-4 py-3 text-sm outline-none transition-colors"
                style={{
                  border: "1px solid var(--theme-border)",
                  background: "var(--theme-bg-card)",
                  color: "var(--theme-text)",
                }}
                placeholder={t("modelConfig.baseUrlPlaceholder")}
              />
            </div>

            <div className="sm:col-span-2 space-y-2">
              <label
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Key size={14} />
                {t("modelConfig.apiKey")}
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? "text" : "password"}
                  value={localProvider.api_key || ""}
                  onChange={(e) =>
                    setLocalProvider({
                      ...localProvider,
                      api_key: e.target.value || undefined,
                    })
                  }
                  className="w-full rounded-xl px-4 py-3 pr-12 text-sm outline-none transition-colors"
                  style={{
                    border: "1px solid var(--theme-border)",
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                  }}
                  placeholder={t("modelConfig.apiKeyPlaceholder")}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 p-1 rounded-lg transition-colors"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
          </div>

          {/* Per-provider defaults */}
          <div
            className="p-4 rounded-xl space-y-4"
            style={{ background: "var(--theme-bg)" }}
          >
            <div
              className="text-xs font-semibold uppercase tracking-wider mb-3"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              Default Parameters
            </div>
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
              <div className="space-y-2">
                <label
                  className="text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Temperature
                </label>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={localProvider.temperature ?? 0.7}
                  onChange={(e) =>
                    setLocalProvider({
                      ...localProvider,
                      temperature: parseFloat(e.target.value) || 0.7,
                    })
                  }
                  className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors"
                  style={{
                    border: "1px solid var(--theme-border)",
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                  }}
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Max Tokens
                </label>
                <input
                  type="number"
                  min={1}
                  value={localProvider.max_tokens ?? 4096}
                  onChange={(e) =>
                    setLocalProvider({
                      ...localProvider,
                      max_tokens: parseInt(e.target.value) || 4096,
                    })
                  }
                  className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors"
                  style={{
                    border: "1px solid var(--theme-border)",
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                  }}
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Max Retries
                </label>
                <input
                  type="number"
                  min={0}
                  value={localProvider.max_retries ?? 3}
                  onChange={(e) =>
                    setLocalProvider({
                      ...localProvider,
                      max_retries: parseInt(e.target.value) || 3,
                    })
                  }
                  className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors"
                  style={{
                    border: "1px solid var(--theme-border)",
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                  }}
                />
              </div>
              <div className="space-y-2">
                <label
                  className="text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Retry Delay (s)
                </label>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={localProvider.retry_delay ?? 1.0}
                  onChange={(e) =>
                    setLocalProvider({
                      ...localProvider,
                      retry_delay: parseFloat(e.target.value) || 1.0,
                    })
                  }
                  className="w-full rounded-xl px-3 py-2.5 text-sm outline-none transition-colors"
                  style={{
                    border: "1px solid var(--theme-border)",
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                  }}
                />
              </div>
            </div>
          </div>

          {/* Models */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label
                className="text-xs font-semibold uppercase tracking-wider flex items-center gap-2"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Sparkles size={14} />
                {t("modelConfig.models")}
              </label>
              <button
                onClick={addModel}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors"
                style={{
                  background: "var(--theme-bg)",
                  color: "var(--theme-primary)",
                }}
              >
                <Plus size={14} />
                {t("modelConfig.addModel")}
              </button>
            </div>

            <div className="space-y-2">
              {localProvider.models.map((model: ModelConfig, idx: number) => (
                <ModelEditor
                  key={idx}
                  model={model}
                  onUpdate={(updated) => updateModel(idx, updated)}
                  onDelete={() => removeModel(idx)}
                />
              ))}

              {localProvider.models.length === 0 && (
                <div
                  className="rounded-xl border-2 border-dashed p-8 text-center"
                  style={{ borderColor: "var(--theme-border)" }}
                >
                  <Sparkles
                    size={32}
                    className="mx-auto mb-3 opacity-40"
                    style={{ color: "var(--theme-primary)" }}
                  />
                  <p
                    className="text-sm"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {t("modelConfig.noModelsInProvider")}
                  </p>
                  <button
                    onClick={addModel}
                    className="mt-3 text-xs font-medium px-4 py-2 rounded-lg text-white transition-all hover:opacity-90"
                    style={{ background: "var(--theme-primary)" }}
                  >
                    <Plus size={14} className="inline mr-1" />
                    Add Model
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Save changes */}
          {hasChanges && (
            <div className="flex justify-end pt-2">
              <button
                onClick={() => onUpdate(localProvider)}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl text-white transition-all duration-200 hover:scale-105 active:scale-95"
                style={{
                  background: "var(--theme-primary)",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                }}
              >
                <Save size={16} />
                {t("common.save")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
