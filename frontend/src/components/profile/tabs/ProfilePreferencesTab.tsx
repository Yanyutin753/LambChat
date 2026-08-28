import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Settings, ChevronRight, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTheme } from "../../../contexts/ThemeContext";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { useAuth } from "../../../hooks/useAuth";
import { Brain } from "lucide-react";
import { authApi, agentConfigApi, agentApi } from "../../../services/api";
import { DEFAULT_THINKING_LEVEL_STORAGE_KEY } from "../../layout/AppContent/useAgentOptions";
import { SkeletonLine } from "../../skeletons";
import { resolveAgentDisplayName } from "../../agent/agentCatalog";
import type { AgentInfo } from "../../../types";
import type { Theme } from "../../../utils/themeDom";
import {
  parseSendModifier,
  SEND_MODIFIER_STORAGE_KEY,
  type SendModifier,
} from "../../../hooks/sendModifier";

const LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "zh", nativeName: "中文" },
  { code: "ja", nativeName: "日本語" },
  { code: "ko", nativeName: "한국어" },
  { code: "ru", nativeName: "Русский" },
];

type ThinkingLevel = "low" | "medium" | "high" | "max";

const NEWLINE_OPTIONS: { key: SendModifier; labelKey: string }[] = [
  { key: "enter", labelKey: "profile.newlineEnter" },
  { key: "ctrl", labelKey: "profile.newlineCtrl" },
  { key: "shift", labelKey: "profile.newlineShift" },
];

const THEME_OPTIONS: { key: Theme; labelKey: string }[] = [
  { key: "light", labelKey: "profile.lightTheme" },
  { key: "dark", labelKey: "profile.darkTheme" },
  { key: "sepia", labelKey: "profile.sepiaTheme" },
];

const THINKING_LEVEL_OPTIONS: { key: ThinkingLevel; labelKey: string }[] = [
  { key: "low", labelKey: "agentOptions.enableThinking.options.low" },
  { key: "medium", labelKey: "agentOptions.enableThinking.options.medium" },
  { key: "high", labelKey: "agentOptions.enableThinking.options.high" },
  { key: "max", labelKey: "agentOptions.enableThinking.options.max" },
];

/** Reusable selection row — opens a centered dialog popup */
function SelectRow<T extends string>({
  label,
  value,
  options,
  open,
  onToggle,
  onSelect,
  loading,
  renderLabel,
}: {
  label: string;
  value: T;
  options: readonly { key: T; labelKey: string }[];
  open: boolean;
  onToggle: () => void;
  onSelect: (key: T) => void;
  loading?: boolean;
  renderLabel?: (key: T) => string;
}) {
  const { t } = useTranslation();
  const selected = options.find((o) => o.key === value);

  return (
    <>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between py-3 first:pt-0 last:pb-0 text-left"
      >
        <span className="text-sm text-stone-700 dark:text-stone-200">
          {label}
        </span>
        <span className="flex items-center gap-1 text-xs text-stone-500 dark:text-stone-400">
          {loading ? (
            <SkeletonLine width="w-16" />
          ) : (
            <span className="truncate max-w-[140px]">
              {renderLabel
                ? renderLabel(value)
                : selected
                  ? t(selected.labelKey)
                  : value}
            </span>
          )}
          <ChevronRight size={14} className="shrink-0 text-stone-400" />
        </span>
      </button>
      {open &&
        createPortal(
          <div
            className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center animate-fade-in"
            onClick={onToggle}
          >
            <div className="absolute inset-0 bg-black/40" />
            <div
              className="relative z-10 w-[300px] max-h-[60dvh] rounded-2xl bg-theme-bg-card dark:bg-stone-800 border border-stone-200 dark:border-stone-700 shadow-2xl overflow-hidden animate-scale-in"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-5 pt-4 pb-2">
                <h4 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
                  {label}
                </h4>
              </div>
              <div className="overflow-y-auto max-h-[50dvh] pb-2">
                {options.map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => onSelect(opt.key)}
                    className={`w-full text-left px-5 py-2.5 text-sm transition-colors ${
                      value === opt.key
                        ? "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 font-medium"
                        : "text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700/50"
                    }`}
                  >
                    <span className="flex items-center justify-between">
                      {renderLabel ? renderLabel(opt.key) : t(opt.labelKey)}
                      {value === opt.key && (
                        <Check size={14} className="text-amber-500 shrink-0" />
                      )}
                    </span>
                  </button>
                ))}
              </div>
              <div className="border-t border-stone-100 dark:border-stone-700/50 px-5 py-3">
                <button
                  onClick={onToggle}
                  className="w-full text-center text-xs font-medium text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 transition-colors"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

export function ProfilePreferencesTab() {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useTheme();
  const { availableModels, defaultModel } = useSettingsContext();
  const { enableMemory } = useSettingsContext();
  const { user } = useAuth();
  const [memoryEnabled, setMemoryEnabled] = useState(
    user?.metadata?.memoryEnabled !== false,
  );

  const handleMemoryToggle = useCallback(() => {
    const next = !memoryEnabled;
    setMemoryEnabled(next);
    authApi.updateMetadata({ memoryEnabled: next }).catch(() => {
      setMemoryEnabled(!next);
      toast.error(t("common.operationFailed"));
    });
  }, [memoryEnabled, t]);

  // Dropdown open states
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const toggle = (key: string) =>
    setOpenDropdown((prev) => (prev === key ? null : key));

  // Send shortcut preference (Enter, Ctrl/⌘+Enter, or Shift+Enter sends)
  const [newlineModifier, setNewlineModifier] = useState<SendModifier>(() =>
    parseSendModifier(localStorage.getItem(SEND_MODIFIER_STORAGE_KEY)),
  );
  const [defaultThinkingLevel, setDefaultThinkingLevel] =
    useState<ThinkingLevel>(() => {
      // "off" 档已下线：历史存量值降级到最低档
      const stored = localStorage.getItem(DEFAULT_THINKING_LEVEL_STORAGE_KEY);
      if (
        stored === "low" ||
        stored === "medium" ||
        stored === "high" ||
        stored === "max"
      ) {
        return stored;
      }
      return "low";
    });

  // Default model preference
  const [selectedModelId, setSelectedModelId] = useState<string>(() => {
    return localStorage.getItem("defaultModelId") || "";
  });
  const [, setSelectedModelValue] = useState<string>(() => {
    return localStorage.getItem("defaultModel") || defaultModel;
  });

  // Agent preference
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgentPref, setCurrentAgentPref] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsSaving, setAgentsSaving] = useState(false);

  const loadAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const [agentsRes, prefRes] = await Promise.all([
        agentApi.list(),
        agentConfigApi
          .getUserPreference()
          .catch(() => ({ default_agent_id: null })),
      ]);
      setAgents(agentsRes.agents || []);
      setCurrentAgentPref(prefRes.default_agent_id);
      setSelectedAgent(
        prefRes.default_agent_id || agentsRes.default_agent || "",
      );
    } catch {
      // silent — dropdown will show empty
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  // Handlers
  const handleLanguageChange = (code: string) => {
    i18n.changeLanguage(code);
    localStorage.setItem("language", code);
    authApi.updateMetadata({ language: code }).catch(() => {});
    setOpenDropdown(null);
  };

  const handleThemeChange = (newTheme: Theme) => {
    setTheme(newTheme);
    authApi.updateMetadata({ theme: newTheme }).catch(() => {});
    setOpenDropdown(null);
  };

  const handleNewlineChange = (modifier: SendModifier) => {
    setNewlineModifier(modifier);
    localStorage.setItem(SEND_MODIFIER_STORAGE_KEY, modifier);
    authApi.updateMetadata({ newlineModifier: modifier }).catch(() => {});
    setOpenDropdown(null);
  };

  const handleModelChange = (modelId: string) => {
    const model = availableModels?.find((m) => m.id === modelId);
    const modelValue = model?.value || "";
    setSelectedModelId(modelId);
    setSelectedModelValue(modelValue);
    localStorage.setItem("defaultModelId", modelId);
    localStorage.setItem("defaultModel", modelValue);
    authApi
      .updateMetadata({ defaultModel: modelValue, defaultModelId: modelId })
      .catch(() => {});
    window.dispatchEvent(
      new CustomEvent("model-preference-updated", {
        detail: { modelId, modelValue },
      }),
    );
    setOpenDropdown(null);
  };

  const handleAgentChange = async (agentId: string) => {
    setSelectedAgent(agentId);
    setOpenDropdown(null);
    setAgentsSaving(true);
    try {
      await agentConfigApi.setUserPreference(agentId);
      setCurrentAgentPref(agentId);
      toast.success(t("agentConfig.preferenceSaved"));
      window.dispatchEvent(new CustomEvent("agent-preference-updated"));
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.saveFailed"));
      setSelectedAgent(currentAgentPref || "");
    } finally {
      setAgentsSaving(false);
    }
  };

  const handleThinkingLevelChange = (level: ThinkingLevel) => {
    setDefaultThinkingLevel(level);
    localStorage.setItem(DEFAULT_THINKING_LEVEL_STORAGE_KEY, level);
    authApi.updateMetadata({ defaultThinkingLevel: level }).catch(() => {});
    window.dispatchEvent(
      new CustomEvent("thinking-preference-updated", {
        detail: level,
      }),
    );
    setOpenDropdown(null);
  };

  const agentOptions = agents.map((a) => ({
    key: a.id,
    labelKey: a.name,
  }));

  const renderAgentLabel = (key: string) => {
    const agent = agents.find((a) => a.id === key);
    return agent ? resolveAgentDisplayName(agent, i18n.language, t) : key;
  };

  // Show ⌘ instead of Ctrl on Apple platforms for the ctrl send modifier
  const isMac =
    typeof navigator !== "undefined" &&
    /Mac|iPhone|iPad|iPod/.test(
      navigator.platform || navigator.userAgent || "",
    );
  const renderNewlineLabel = (key: SendModifier) => {
    const opt = NEWLINE_OPTIONS.find((o) => o.key === key);
    if (!opt) return key;
    const label = t(opt.labelKey);
    return isMac && key === "ctrl" ? label.replace("Ctrl", "⌘") : label;
  };

  return (
    <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Settings size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="font-semibold font-serif uppercase tracking-wide text-stone-400 dark:text-stone-500">
          {t("profile.preferences")}
        </h3>
      </div>

      <div className="space-y-0">
        {enableMemory && (
          <button
            onClick={handleMemoryToggle}
            className="flex w-full items-center justify-between py-3 first:pt-0 last:pb-0 text-left"
          >
            <span className="flex items-center gap-2 text-sm text-stone-700 dark:text-stone-200">
              <Brain size={15} className="text-amber-500 dark:text-amber-400" />
              {t("profile.memoryToggle")}
            </span>
            <span
              className={`relative h-5 w-9 rounded-full transition-colors ${
                memoryEnabled
                  ? "bg-amber-500"
                  : "bg-stone-300 dark:bg-stone-600"
              }`}
              role="switch"
              aria-checked={memoryEnabled}
              aria-label={t("profile.memoryToggle")}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
                  memoryEnabled ? "left-[1.15rem]" : "left-0.5"
                }`}
              />
            </span>
          </button>
        )}

        <SelectRow
          label={t("profile.language")}
          value={i18n.language}
          options={LANGUAGES.map((l) => ({
            key: l.code,
            labelKey: "",
          }))}
          open={openDropdown === "language"}
          onToggle={() => toggle("language")}
          onSelect={handleLanguageChange}
          renderLabel={(code) =>
            LANGUAGES.find((l) => l.code === code)?.nativeName || code
          }
        />

        <SelectRow
          label={t("profile.theme")}
          value={theme}
          options={THEME_OPTIONS}
          open={openDropdown === "theme"}
          onToggle={() => toggle("theme")}
          onSelect={handleThemeChange}
        />

        <SelectRow
          label={t("agentConfig.defaultAgent")}
          value={selectedAgent}
          options={agentOptions}
          open={openDropdown === "agent"}
          onToggle={() => toggle("agent")}
          onSelect={handleAgentChange}
          loading={agentsLoading || agentsSaving}
          renderLabel={renderAgentLabel}
        />

        {availableModels && availableModels.length > 0 && (
          <SelectRow
            label={t("profile.defaultModel")}
            value={selectedModelId}
            options={availableModels.map((m) => ({
              key: m.id,
              labelKey: "",
            }))}
            open={openDropdown === "model"}
            onToggle={() => toggle("model")}
            onSelect={handleModelChange}
            renderLabel={(id) => {
              const m = availableModels.find((m) => m.id === id);
              return m ? m.label : id;
            }}
          />
        )}

        <SelectRow
          label={t("profile.defaultThinking")}
          value={defaultThinkingLevel}
          options={THINKING_LEVEL_OPTIONS}
          open={openDropdown === "thinking"}
          onToggle={() => toggle("thinking")}
          onSelect={handleThinkingLevelChange}
        />

        <SelectRow
          label={t("profile.newlineModifier")}
          value={newlineModifier}
          options={NEWLINE_OPTIONS}
          open={openDropdown === "newline"}
          onToggle={() => toggle("newline")}
          onSelect={handleNewlineChange}
          renderLabel={renderNewlineLabel}
        />
      </div>
    </div>
  );
}
