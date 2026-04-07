/**
 * Model 配置管理面板组件
 * 管理员配置 Provider 分组、凭证和模型
 * 主题适配设计
 */

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Save,
  AlertCircle,
  RefreshCw,
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
  Shield,
  Check,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { modelConfigApi, roleApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { ModelProviderConfig, ModelConfig, Role } from "../../types";

// Tab types
type TabType = "providers" | "roles";

// Modern toggle switch component
function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <button
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-200 ${
        checked ? "" : "bg-stone-200 dark:bg-stone-700"
      }`}
      style={checked ? { background: "var(--theme-primary)" } : undefined}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-md transition-transform duration-200 ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

// Provider icon badge using theme color
function ProviderBadge({ provider }: { provider: string }) {
  return (
    <div
      className="flex items-center justify-center w-10 h-10 rounded-xl text-white font-bold text-sm"
      style={{
        background: "var(--theme-primary)",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
      }}
    >
      {provider.charAt(0).toUpperCase()}
    </div>
  );
}

// ============================================
// Provider Tab Component
// ============================================

interface ProviderEditorProps {
  provider: ModelProviderConfig;
  onUpdate: (updated: ModelProviderConfig) => void;
  onDelete: () => void;
}

function ProviderEditor({ provider, onUpdate, onDelete }: ProviderEditorProps) {
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
            <div className="flex items-center gap-2 mt-1">
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
            <div className="grid gap-4 grid-cols-2 sm:grid-cols-4">
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

interface ModelEditorProps {
  model: ModelConfig;
  onUpdate: (updated: ModelConfig) => void;
  onDelete: () => void;
}

function ModelEditor({ model, onUpdate, onDelete }: ModelEditorProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex items-center gap-3 rounded-xl border p-3 transition-colors"
      style={{
        borderColor: "var(--theme-border)",
        background: "var(--theme-bg-card)",
      }}
    >
      <input
        type="text"
        value={model.value}
        onChange={(e) => onUpdate({ ...model, value: e.target.value })}
        className="flex-1 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
        style={{
          border: "1px solid var(--theme-border)",
          background: "var(--theme-bg)",
          color: "var(--theme-text)",
        }}
        placeholder={t("modelConfig.modelValuePlaceholder")}
      />
      <input
        type="text"
        value={model.label}
        onChange={(e) => onUpdate({ ...model, label: e.target.value })}
        className="flex-1 rounded-lg px-3 py-2 text-sm outline-none transition-colors"
        style={{
          border: "1px solid var(--theme-border)",
          background: "var(--theme-bg)",
          color: "var(--theme-text)",
        }}
        placeholder={t("modelConfig.modelLabelPlaceholder")}
      />
      <button
        onClick={onDelete}
        className="flex-shrink-0 p-2 text-stone-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
      >
        <Trash2 size={16} />
      </button>
    </div>
  );
}

// ============================================
// Providers Tab
// ============================================

function ProvidersTab({
  providers,
  onUpdate,
  onAdd,
}: {
  providers: ModelProviderConfig[];
  onUpdate: (providers: ModelProviderConfig[]) => void;
  onAdd: () => void;
}) {
  const { t } = useTranslation();

  const updateProvider = (index: number, updated: ModelProviderConfig) => {
    const newProviders = [...providers];
    newProviders[index] = updated;
    onUpdate(newProviders);
  };

  const deleteProvider = (index: number) => {
    onUpdate(providers.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <p
        className="text-sm px-1"
        style={{ color: "var(--theme-text-secondary)" }}
      >
        {t("modelConfig.providersDescription")}
      </p>

      <div className="space-y-4">
        {providers.map((provider, idx) => (
          <ProviderEditor
            key={idx}
            provider={provider}
            onUpdate={(updated) => updateProvider(idx, updated)}
            onDelete={() => deleteProvider(idx)}
          />
        ))}
      </div>

      {providers.length === 0 && (
        <div
          className="flex flex-col items-center justify-center py-16 rounded-2xl"
          style={{ background: "var(--theme-bg)" }}
        >
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: "var(--theme-primary-light)" }}
          >
            <Cpu size={36} style={{ color: "var(--theme-primary)" }} />
          </div>
          <p
            className="text-sm font-medium"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {t("modelConfig.noProviders")}
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            Add your first AI provider to get started
          </p>
        </div>
      )}

      <button
        onClick={onAdd}
        className="w-full rounded-2xl border-2 border-dashed p-5 text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2"
        style={{
          borderColor: "var(--theme-border)",
          color: "var(--theme-text-secondary)",
        }}
      >
        <Plus size={20} />
        {t("modelConfig.addProvider")}
      </button>
    </div>
  );
}

// ============================================
// Roles Tab
// ============================================

function RolesTab({
  roles,
  roleModelsMap,
  flatModels,
  onUpdate,
  isLoading,
}: {
  roles: Role[];
  roleModelsMap: Record<string, string[]>;
  flatModels: ModelConfig[];
  onUpdate: (roleId: string, modelIds: string[]) => void;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [selectedRole, setSelectedRole] = useState<string | null>(
    roles.length > 0 ? roles[0].id : null,
  );
  const [localRoleModels, setLocalRoleModels] =
    useState<Record<string, string[]>>(roleModelsMap);
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);

  useEffect(() => {
    setLocalRoleModels(roleModelsMap);
  }, [roleModelsMap]);

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const currentRoleModels = selectedRole
    ? localRoleModels[selectedRole] || []
    : [];

  const toggleModel = (modelId: string) => {
    if (!selectedRole) return;
    setLocalRoleModels((prev) => {
      const current = prev[selectedRole] || [];
      if (current.includes(modelId)) {
        return {
          ...prev,
          [selectedRole]: current.filter((id) => id !== modelId),
        };
      }
      return { ...prev, [selectedRole]: [...current, modelId] };
    });
  };

  const handleSave = () => {
    if (!selectedRole) return;
    try {
      onUpdate(selectedRole, localRoleModels[selectedRole] || []);
    } catch (err) {
      console.error("Failed to save role models:", err);
    }
  };

  const selectedRoleData = roles.find((r) => r.id === selectedRole);
  const hasChanges = selectedRole
    ? JSON.stringify(localRoleModels[selectedRole]) !==
      JSON.stringify(roleModelsMap[selectedRole])
    : false;

  // Group models by provider for display
  const groupedModels: Record<string, ModelConfig[]> = {};
  const ungrouped: ModelConfig[] = [];
  for (const m of flatModels) {
    if (m.provider) {
      if (!groupedModels[m.provider]) groupedModels[m.provider] = [];
      groupedModels[m.provider].push(m);
    } else {
      ungrouped.push(m);
    }
  }

  return (
    <div className="space-y-4">
      <p
        className="text-sm px-1"
        style={{ color: "var(--theme-text-secondary)" }}
      >
        {t("modelConfig.rolesDescription")}
      </p>

      {/* Role selector */}
      <div className="sm:hidden">
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex w-full items-center justify-between rounded-xl px-4 py-3.5 text-sm font-medium transition-colors"
            style={{
              border: "1px solid var(--theme-border)",
              background: "var(--theme-bg-card)",
              color: "var(--theme-text)",
            }}
          >
            <span className="flex items-center gap-2">
              <Shield size={16} style={{ color: "var(--theme-primary)" }} />
              {selectedRoleData?.name || t("modelConfig.selectRole")}
            </span>
            <ChevronDown
              size={18}
              className="transition-transform"
              style={{ color: "var(--theme-text-secondary)" }}
            />
          </button>

          {roleDropdownOpen && (
            <div
              className="absolute z-10 mt-2 w-full rounded-xl shadow-xl overflow-hidden"
              style={{
                border: "1px solid var(--theme-border)",
                background: "var(--theme-bg-card)",
              }}
            >
              {roles.map((role) => (
                <button
                  key={role.id}
                  onClick={() => {
                    setSelectedRole(role.id);
                    setRoleDropdownOpen(false);
                  }}
                  className={`flex w-full items-center justify-between px-4 py-3.5 text-sm first:rounded-t-xl last:rounded-b-xl transition-colors ${
                    selectedRole === role.id ? "" : ""
                  }`}
                  style={
                    selectedRole === role.id
                      ? {
                          background: "var(--theme-primary-light)",
                          color: "var(--theme-text)",
                        }
                      : { color: "var(--theme-text-secondary)" }
                  }
                >
                  <span>{role.name}</span>
                  {selectedRole === role.id && (
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

      {/* Desktop role tabs */}
      <div
        className="hidden sm:flex gap-1 p-1 rounded-xl overflow-x-auto"
        style={{ background: "var(--theme-bg)" }}
      >
        {roles.map((role) => (
          <button
            key={role.id}
            onClick={() => setSelectedRole(role.id)}
            className={`flex-shrink-0 px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
              selectedRole === role.id ? "" : ""
            }`}
            style={
              selectedRole === role.id
                ? {
                    background: "var(--theme-bg-card)",
                    color: "var(--theme-text)",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                  }
                : { color: "var(--theme-text-secondary)" }
            }
          >
            <Shield size={14} style={{ color: "var(--theme-primary)" }} />
            {role.name}
          </button>
        ))}
      </div>

      {selectedRole && (
        <>
          <div
            className="rounded-2xl p-5 space-y-4"
            style={{
              background: "var(--theme-bg-card)",
              border: "1px solid var(--theme-border)",
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <Shield size={18} style={{ color: "var(--theme-primary)" }} />
              <h4
                className="text-sm font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("modelConfig.selectModelsForRole", {
                  roleName: selectedRoleData?.name,
                })}
              </h4>
              <span
                className="ml-auto text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {currentRoleModels.length} selected
              </span>
            </div>

            {/* Grouped models */}
            {Object.entries(groupedModels).map(([provider, models]) => (
              <div key={provider} className="space-y-2">
                <div
                  className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-1"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {provider}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {models.map((model) => {
                    const isEnabled = currentRoleModels.includes(model.value);
                    return (
                      <label
                        key={model.value}
                        className={`flex items-center gap-3 rounded-xl p-3 cursor-pointer transition-all duration-200 ${
                          isEnabled ? "shadow-sm" : ""
                        }`}
                        style={
                          isEnabled
                            ? {
                                background: "var(--theme-primary-light)",
                                boxShadow: "0 0 0 1px var(--theme-primary)",
                              }
                            : {
                                background: "var(--theme-bg-card)",
                                border: "1px solid var(--theme-border)",
                              }
                        }
                      >
                        <Toggle
                          checked={isEnabled}
                          onChange={() => toggleModel(model.value)}
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {model.label}
                          </div>
                          {model.description && (
                            <div
                              className="text-xs truncate hidden sm:block mt-0.5"
                              style={{ color: "var(--theme-text-secondary)" }}
                            >
                              {model.description}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}

            {ungrouped.length > 0 && Object.keys(groupedModels).length > 0 && (
              <div
                className="border-t my-4"
                style={{ borderColor: "var(--theme-border)" }}
              />
            )}

            {ungrouped.length > 0 && (
              <div className="space-y-2">
                <div
                  className="text-xs font-semibold uppercase tracking-wider px-1"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  Other Models
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {ungrouped.map((model) => {
                    const isEnabled = currentRoleModels.includes(model.value);
                    return (
                      <label
                        key={model.value}
                        className={`flex items-center gap-3 rounded-xl p-3 cursor-pointer transition-all duration-200 ${
                          isEnabled ? "shadow-sm" : ""
                        }`}
                        style={
                          isEnabled
                            ? {
                                background: "var(--theme-primary-light)",
                                boxShadow: "0 0 0 1px var(--theme-primary)",
                              }
                            : {
                                background: "var(--theme-bg-card)",
                                border: "1px solid var(--theme-border)",
                              }
                        }
                      >
                        <Toggle
                          checked={isEnabled}
                          onChange={() => toggleModel(model.value)}
                        />
                        <div className="min-w-0 flex-1">
                          <div
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {model.label}
                          </div>
                          {model.description && (
                            <div
                              className="text-xs truncate hidden sm:block mt-0.5"
                              style={{ color: "var(--theme-text-secondary)" }}
                            >
                              {model.description}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {flatModels.length === 0 && (
              <div className="text-center py-8">
                <Sparkles
                  size={32}
                  className="mx-auto mb-3"
                  style={{ color: "var(--theme-text-secondary)" }}
                />
                <p
                  className="text-sm"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {t("modelConfig.noModels")}
                </p>
              </div>
            )}
          </div>

          {hasChanges && (
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
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
        </>
      )}
    </div>
  );
}

// ============================================
// Main Panel
// ============================================

export function ModelConfigPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>("providers");
  const [isLoading, setIsLoading] = useState(true);
  const [_isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [providers, setProviders] = useState<ModelProviderConfig[]>([]);
  const [flatModels, setFlatModels] = useState<ModelConfig[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleModelsMap, setRoleModelsMap] = useState<Record<string, string[]>>(
    {},
  );

  const canManage = hasPermission(Permission.MODEL_ADMIN);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [providerConfig, roleList] = await Promise.all([
        canManage ? modelConfigApi.getProviderConfig() : Promise.resolve(null),
        roleApi.list(),
      ]);

      if (providerConfig) {
        setProviders(providerConfig.providers);
        setFlatModels(providerConfig.flat_models);
      }

      setRoles(roleList || []);

      if (canManage) {
        const roleModelPromises = (roleList || []).map(async (role: Role) => {
          try {
            const assignment = await modelConfigApi.getRoleModels(role.id);
            return { roleId: role.id, models: assignment.allowed_models };
          } catch {
            return { roleId: role.id, models: [] };
          }
        });
        const roleModelResults = await Promise.all(roleModelPromises);
        const map: Record<string, string[]> = {};
        roleModelResults.forEach(({ roleId, models }) => {
          map[roleId] = models;
        });
        setRoleModelsMap(map);
      }
    } catch (err) {
      const errorMsg = (err as Error).message || t("modelConfig.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [canManage, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSaveProviders = async (newProviders: ModelProviderConfig[]) => {
    if (!canManage) return;
    setIsSaving(true);
    try {
      const result = await modelConfigApi.updateProviderConfig(newProviders);
      setProviders(result.providers);
      setFlatModels(result.flat_models);
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddProvider = () => {
    const newProvider: ModelProviderConfig = {
      provider: "openai",
      label: t("modelConfig.newProvider"),
      base_url: undefined,
      api_key: undefined,
      temperature: 0.7,
      max_tokens: 4096,
      max_retries: 3,
      retry_delay: 1.0,
      models: [],
    };
    setProviders([...providers, newProvider]);
  };

  const handleUpdateRoleModels = async (roleId: string, modelIds: string[]) => {
    if (!canManage) return;
    try {
      await modelConfigApi.updateRoleModels(roleId, modelIds);
      setRoleModelsMap((prev) => ({ ...prev, [roleId]: modelIds }));
      toast.success(t("modelConfig.saveSuccess"));
    } catch (err) {
      toast.error((err as Error).message || t("modelConfig.saveFailed"));
      throw err;
    }
  };

  const handleRefresh = () => {
    loadData();
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      <PanelHeader
        title={t("modelConfig.title")}
        icon={<Cpu size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            <RefreshCw
              size={16}
              className="hover:rotate-180 transition-transform duration-500"
            />
            <span className="hidden sm:inline">{t("common.refresh")}</span>
          </button>
        }
      />

      {error && (
        <div
          className="mx-4 mt-4 flex items-center gap-3 rounded-2xl p-4 text-sm sm:mx-6"
          style={{
            background: "rgba(239, 68, 68, 0.08)",
            color: "#ef4444",
            border: "1px solid rgba(239, 68, 68, 0.2)",
          }}
        >
          <AlertCircle size={20} className="flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {canManage && (
        <div className="mx-4 mt-3 sm:mx-6 sm:mt-4">
          <div
            className="inline-flex gap-1 p-1.5 rounded-2xl"
            style={{ background: "var(--theme-bg)" }}
          >
            <button
              onClick={() => setActiveTab("providers")}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 min-w-[110px] justify-center"
              style={
                activeTab === "providers"
                  ? {
                      background: "var(--theme-bg-card)",
                      color: "var(--theme-text)",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
                    }
                  : {
                      color: "var(--theme-text-secondary)",
                      background: "transparent",
                    }
              }
            >
              <LayoutGrid size={16} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.providersTab")}
            </button>
            <button
              onClick={() => setActiveTab("roles")}
              className="px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 min-w-[110px] justify-center"
              style={
                activeTab === "roles"
                  ? {
                      background: "var(--theme-bg-card)",
                      color: "var(--theme-text)",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
                    }
                  : {
                      color: "var(--theme-text-secondary)",
                      background: "transparent",
                    }
              }
            >
              <Shield size={16} style={{ color: "var(--theme-primary)" }} />
              {t("modelConfig.rolesTab")}
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {canManage ? (
          activeTab === "providers" ? (
            <ProvidersTab
              providers={providers}
              onUpdate={handleSaveProviders}
              onAdd={handleAddProvider}
            />
          ) : (
            <RolesTab
              roles={roles}
              roleModelsMap={roleModelsMap}
              flatModels={flatModels}
              onUpdate={handleUpdateRoleModels}
              isLoading={isLoading}
            />
          )
        ) : (
          <div
            className="flex flex-col items-center justify-center py-20 rounded-3xl"
            style={{ background: "var(--theme-bg)" }}
          >
            <div
              className="w-24 h-24 rounded-3xl flex items-center justify-center mb-6"
              style={{
                background: "var(--theme-primary-light)",
                boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
              }}
            >
              <Cpu size={40} style={{ color: "var(--theme-primary)" }} />
            </div>
            <p
              className="text-base font-semibold mb-2"
              style={{ color: "var(--theme-text)" }}
            >
              {t("modelConfig.noPermission")}
            </p>
            <p
              className="text-sm mt-1 max-w-[260px] text-center"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              You need admin permissions to manage models
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default ModelConfigPanel;
