/**
 * Provider editor card component
 */
import { useState, useEffect, useRef } from "react";
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
  RotateCcw,
  Settings2,
  Check,
  BadgeInfo,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderBadge } from "./ProviderBadge";
import { ModelEditor } from "./ModelEditor";
import type { ModelProviderConfig, ModelConfig } from "../../../../types";
import {
  getProviderMeta,
  PROVIDER_TYPE_OPTIONS,
} from "../../../../types/model";

/** Built-in provider identifiers that are always shown in the dropdown. */
const BUILTIN_PROVIDERS = [
  "anthropic",
  "google",
  "openai",
  "azure",
  "bedrock",
  "groq",
  "deepseek",
  "mistral",
  "cohere",
  "ollama",
  "zai",
] as const;

interface ProviderEditorProps {
  provider: ModelProviderConfig;
  providerNames?: string[];
  isLegacyInherited?: boolean;
  onUpdate: (updated: ModelProviderConfig) => void;
  onDelete: () => void;
  showDelete?: boolean;
}

/** Build provider dropdown options from built-in list + any extra names from the API + "custom". */
function buildProviderOptions(extraNames?: string[]) {
  const seen = new Set<string>(BUILTIN_PROVIDERS);
  if (extraNames) {
    for (const n of extraNames) {
      if (!seen.has(n)) seen.add(n);
    }
  }
  const options: { value: string; label: string }[] = [];
  for (const value of seen) {
    const meta = getProviderMeta(value);
    options.push({ value, label: meta?.display_name || value });
  }
  options.push({ value: "custom", label: "Custom" });
  return options;
}

export function ProviderEditor({
  provider,
  providerNames,
  isLegacyInherited = false,
  onUpdate,
  onDelete,
  showDelete = true,
}: ProviderEditorProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);
  const [providerDropdownOpen, setProviderDropdownOpen] = useState(false);
  const [providerTypeDropdownOpen, setProviderTypeDropdownOpen] = useState(false);
  const [localProvider, setLocalProvider] = useState(provider);
  const [apiKeyInput, setApiKeyInput] = useState(provider.api_key || "");
  const providerDropdownRef = useRef<HTMLDivElement | null>(null);
  const providerTypeDropdownRef = useRef<HTMLDivElement | null>(null);

  const PROVIDER_OPTIONS = buildProviderOptions(providerNames);

  useEffect(() => {
    setLocalProvider(provider);
    setApiKeyInput(provider.api_key || "");
    setShowApiKey(false);
  }, [provider]);

  useEffect(() => {
    if (!providerDropdownOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        providerDropdownRef.current &&
        !providerDropdownRef.current.contains(event.target as Node)
      ) {
        setProviderDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [providerDropdownOpen]);

  useEffect(() => {
    if (!providerTypeDropdownOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        providerTypeDropdownRef.current &&
        !providerTypeDropdownRef.current.contains(event.target as Node)
      ) {
        setProviderTypeDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [providerTypeDropdownOpen]);

  const meta = getProviderMeta(localProvider.provider);
  const brandColor = meta?.color || "#78716c";
  const selectedProviderLabel =
    PROVIDER_OPTIONS.find((option) => option.value === localProvider.provider)
      ?.label ||
    meta?.display_name ||
    localProvider.provider;
  const isCustomProvider = !BUILTIN_PROVIDERS.includes(
    localProvider.provider as (typeof BUILTIN_PROVIDERS)[number],
  );
  const selectedProviderTypeLabel =
    PROVIDER_TYPE_OPTIONS.find(
      (opt) => opt.value === (localProvider.provider_type ?? "openai_compatible"),
    )?.label ?? "OpenAI Compatible";

  const updateModel = (index: number, updated: ModelConfig) => {
    const newModels = [...localProvider.models];
    newModels[index] = updated;
    setLocalProvider({ ...localProvider, models: newModels });
  };

  const addModel = () => {
    const newModel: ModelConfig = {
      id: "",
      name: "",
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

  const normalizedProvider = JSON.stringify({
    ...localProvider,
    api_key: undefined,
  });
  const normalizedOriginalProvider = JSON.stringify({
    ...provider,
    api_key: undefined,
  });
  const hasChanges =
    normalizedProvider !== normalizedOriginalProvider ||
    apiKeyInput !== "";

  const handleReset = () => {
    setLocalProvider(provider);
    setApiKeyInput(provider.api_key || "");
    setShowApiKey(false);
  };

  const handleSave = () => {
    onUpdate({
      ...localProvider,
      api_key: apiKeyInput || undefined,
      clear_api_key: localProvider.clear_api_key || false,
      provider_type: localProvider.provider_type,
    });
  };

  return (
    <div className="model-config-provider-card rounded-3xl shadow-sm">
      {/* ── Provider Header ── */}
      <div
        className="model-config-provider-header flex cursor-pointer select-none items-center gap-3 rounded-t-3xl px-4 py-3.5 sm:px-5 sm:py-4"
        onClick={() => setExpanded(!expanded)}
      >
        <ProviderBadge provider={localProvider.provider} size="sm" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={localProvider.label}
              onChange={(e) =>
                setLocalProvider({ ...localProvider, label: e.target.value })
              }
              onClick={(e) => e.stopPropagation()}
              className="w-full truncate border-b-2 border-transparent bg-transparent text-sm font-semibold outline-none transition-colors focus:border-current"
              style={{ color: "var(--theme-text)" }}
              placeholder={t("modelConfig.providerLabelPlaceholder")}
            />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span
              className="text-[11px] px-2 py-0.5 rounded-full font-medium"
              style={{
                backgroundColor: `${brandColor}15`,
                color: brandColor,
              }}
            >
              {meta?.display_name || localProvider.provider}
            </span>
            {localProvider.models.length > 0 && (
              <span
                className="text-[11px]"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("modelConfig.modelCount", {
                  count: localProvider.models.length,
                })}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div
          className="flex items-center gap-0.5"
          onClick={(e) => e.stopPropagation()}
        >
          {hasChanges && (
            <button
              onClick={handleReset}
              className="model-config-icon-button rounded-lg p-1.5"
              title={t("common.cancel")}
            >
              <RotateCcw size={14} />
            </button>
          )}
          {showDelete && (
            <button
              onClick={onDelete}
              className="model-config-icon-button model-config-icon-button--danger rounded-lg p-1.5"
              title={t("modelConfig.deleteProvider")}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>

        <div
          style={{ color: "var(--theme-text-secondary)" }}
          className="flex-shrink-0"
        >
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </div>
      </div>

      {/* ── Expanded Content ── */}
      {expanded && (
        <div className="space-y-5 border-t px-4 pb-4 pt-3 sm:px-5 sm:pb-5" style={{ borderColor: "var(--theme-border)" }}>
          {isLegacyInherited && (
            <div className="model-config-migration-card rounded-2xl px-4 py-3">
              <div className="flex items-start gap-3">
                <div className="model-config-migration-card__icon flex h-9 w-9 items-center justify-center rounded-2xl">
                  <BadgeInfo size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[var(--theme-text)]">
                    {t("modelConfig.inheritedFromLegacy")}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)]">
                    {t("modelConfig.inheritedFromLegacyDescription")}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── Connection Settings ── */}
          <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
            {/* Provider type */}
            <div className="space-y-1.5">
              <label
                className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <LayoutGrid size={12} />
                {t("modelConfig.provider")}
              </label>
              <div className="relative" ref={providerDropdownRef}>
                <button
                  type="button"
                  onClick={() => setProviderDropdownOpen((open) => !open)}
                  className="model-config-input flex h-[46px] w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition-colors"
                  aria-haspopup="listbox"
                  aria-expanded={providerDropdownOpen}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <ProviderBadge provider={localProvider.provider} size="sm" />
                    <span className="truncate">{selectedProviderLabel}</span>
                  </span>
                  <ChevronDown
                    size={18}
                    className={`flex-shrink-0 transition-transform ${providerDropdownOpen ? "rotate-180" : ""}`}
                    style={{ color: "var(--theme-text-secondary)" }}
                  />
                </button>

                {providerDropdownOpen && (
                  <div className="model-config-role-card model-config-dropdown-menu absolute z-10 mt-1.5 w-full overflow-hidden rounded-2xl shadow-lg">
                    {PROVIDER_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => {
                          setLocalProvider({
                            ...localProvider,
                            provider: option.value,
                          });
                          setProviderDropdownOpen(false);
                        }}
                        className={`model-config-role-card-option flex w-full items-center justify-between px-4 py-3 text-sm ${localProvider.provider === option.value ? "is-active" : ""}`}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <ProviderBadge provider={option.value} size="sm" />
                          <span className="truncate">{option.label}</span>
                        </span>
                        {localProvider.provider === option.value && (
                          <Check
                            size={16}
                            style={{ color: "var(--theme-primary)" }}
                          />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Base URL */}
            <div className="space-y-1.5">
              <label
                className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Globe size={12} />
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
                className="model-config-input h-[46px] px-3 py-2.5 text-sm"
                placeholder={t("modelConfig.baseUrlPlaceholder")}
              />
            </div>

            {/* Provider Type (only for custom providers) */}
            {isCustomProvider && (
              <div className="space-y-1.5">
                <label
                  className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  <Settings2 size={12} />
                  {t("modelConfig.providerType")}
                </label>
                <div className="relative" ref={providerTypeDropdownRef}>
                  <button
                    type="button"
                    onClick={() => setProviderTypeDropdownOpen((open) => !open)}
                    className="model-config-input flex h-[46px] w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition-colors"
                    aria-haspopup="listbox"
                    aria-expanded={providerTypeDropdownOpen}
                  >
                    <span className="truncate">{selectedProviderTypeLabel}</span>
                    <ChevronDown
                      size={18}
                      className={`flex-shrink-0 transition-transform ${providerTypeDropdownOpen ? "rotate-180" : ""}`}
                      style={{ color: "var(--theme-text-secondary)" }}
                    />
                  </button>

                  {providerTypeDropdownOpen && (
                    <div className="model-config-role-card model-config-dropdown-menu absolute z-10 mt-1.5 w-full overflow-hidden rounded-2xl shadow-lg">
                      {PROVIDER_TYPE_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => {
                            setLocalProvider({
                              ...localProvider,
                              provider_type: option.value,
                            });
                            setProviderTypeDropdownOpen(false);
                          }}
                          className={`model-config-role-card-option flex w-full items-center justify-between px-4 py-3 text-sm ${(localProvider.provider_type ?? "openai_compatible") === option.value ? "is-active" : ""}`}
                        >
                          <span className="truncate">{option.label}</span>
                          {(localProvider.provider_type ?? "openai_compatible") === option.value && (
                            <Check
                              size={16}
                              style={{ color: "var(--theme-primary)" }}
                            />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* API Key - full width */}
            <div className="sm:col-span-2 space-y-1.5">
              <label
                className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Key size={12} />
                {t("modelConfig.apiKey")}
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? "text" : "password"}
                  value={apiKeyInput}
                  onChange={(e) => {
                    const nextValue = e.target.value;
                    setApiKeyInput(nextValue);
                    if (localProvider.clear_api_key) {
                      setLocalProvider({
                        ...localProvider,
                        clear_api_key: false,
                      });
                    }
                  }}
                  className="model-config-input h-[46px] px-3 py-2.5 pr-11 text-sm"
                  placeholder={t("modelConfig.apiKeyPlaceholder")}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg transition-colors"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {showApiKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {localProvider.has_api_key && !localProvider.clear_api_key && (
                <div
                  className="mt-2 flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-xs"
                  style={{
                    background: "var(--theme-surface-secondary)",
                    color: "var(--theme-text-secondary)",
                  }}
                >
                  <span>{t("modelConfig.apiKeyConfigured")}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setApiKeyInput("");
                      setLocalProvider({
                        ...localProvider,
                        clear_api_key: true,
                        has_api_key: false,
                      });
                    }}
                    className="font-medium transition-opacity hover:opacity-80"
                    style={{ color: brandColor }}
                  >
                    {t("modelConfig.clearSavedApiKey")}
                  </button>
                </div>
              )}
              {localProvider.clear_api_key && (
                <p
                  className="mt-2 text-xs"
                  style={{ color: "var(--theme-danger)" }}
                >
                  {t("modelConfig.apiKeyWillBeCleared")}
                </p>
              )}
              <p
                className="text-[11px]"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {localProvider.has_api_key && !localProvider.clear_api_key
                  ? t("modelConfig.apiKeyLeaveBlank")
                  : t("modelConfig.apiKeyEmptyHint")}
              </p>
            </div>
          </div>

          {/* ── Default Parameters ── */}
          <div
            className="model-config-provider-section rounded-2xl p-4"
          >
            <div className="flex items-center gap-2 mb-3">
              <Settings2
                size={13}
                style={{ color: brandColor }}
              />
              <span
                className="text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("modelConfig.defaultParameters")}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {([
                {
                  label: t("modelConfig.temperature"),
                  fallback: 0.7,
                  min: 0,
                  step: 0.1,
                  getValue: () => localProvider.temperature ?? 0.7,
                  setValue: (v: number) =>
                    setLocalProvider({ ...localProvider, temperature: v }),
                },
                {
                  label: t("modelConfig.maxTokens"),
                  fallback: 4096,
                  min: 1,
                  step: 1,
                  getValue: () => localProvider.max_tokens ?? 4096,
                  setValue: (v: number) =>
                    setLocalProvider({ ...localProvider, max_tokens: v }),
                },
                {
                  label: t("modelConfig.maxRetries"),
                  fallback: 3,
                  min: 0,
                  step: 1,
                  getValue: () => localProvider.max_retries ?? 3,
                  setValue: (v: number) =>
                    setLocalProvider({ ...localProvider, max_retries: v }),
                },
                {
                  label: t("modelConfig.retryDelay"),
                  fallback: 1.0,
                  min: 0,
                  step: 0.5,
                  getValue: () => localProvider.retry_delay ?? 1.0,
                  setValue: (v: number) =>
                    setLocalProvider({ ...localProvider, retry_delay: v }),
                },
              ] as const).map((field) => (
                <div key={field.label} className="space-y-1.5">
                  <label
                    className="text-[11px] font-medium"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {field.label}
                  </label>
                  <input
                    type="number"
                    min={field.min}
                    step={field.step}
                    value={field.getValue()}
                    onChange={(e) =>
                      field.setValue(
                        parseFloat(e.target.value) || field.fallback,
                      )
                    }
                    className="model-config-input px-3 py-2 text-sm"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* ── Models Section ── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span
                className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Sparkles size={12} />
                {t("modelConfig.models")}
              </span>
              <button
                onClick={addModel}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors hover:opacity-80"
                style={{
                  background: `${brandColor}15`,
                  color: brandColor,
                }}
              >
                <Plus size={12} />
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
                  brandColor={brandColor}
                />
              ))}

              {localProvider.models.length === 0 && (
                <div
                  className="model-config-empty rounded-2xl border-2 border-dashed p-8 text-center"
                >
                  <Sparkles
                    size={24}
                    className="mx-auto mb-2 opacity-25"
                    style={{ color: brandColor }}
                  />
                  <p
                    className="text-xs"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {t("modelConfig.noModelsInProvider")}
                  </p>
                  <button
                    onClick={addModel}
                    className="btn-primary mt-3 text-xs"
                    style={{ background: brandColor }}
                  >
                    <Plus size={12} className="inline mr-1 -mt-0.5" />
                    {t("modelConfig.addModel")}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ── Unsaved Changes Bar ── */}
          {hasChanges && (
            <div
              className="model-config-savebar flex flex-col gap-3 rounded-2xl px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full animate-pulse"
                  style={{ background: brandColor }}
                />
                <span
                  className="text-xs font-medium"
                  style={{ color: brandColor }}
                >
                  {t("modelConfig.unsavedChanges")}
                </span>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  onClick={handleReset}
                  className="btn-secondary px-3 py-1.5 text-xs"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleSave}
                  className="btn-primary px-4 py-1.5 text-xs"
                  style={{
                    background: brandColor,
                    boxShadow: `0 2px 8px ${brandColor}30`,
                  }}
                >
                  <Save size={13} />
                  {t("common.save")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
