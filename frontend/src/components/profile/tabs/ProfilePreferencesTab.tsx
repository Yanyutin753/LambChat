import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Settings, ChevronDown } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTheme } from "../../../contexts/ThemeContext";
import { authApi, agentConfigApi, agentApi } from "../../../services/api";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import type { AgentInfo } from "../../../types";

const NEWLINE_MODIFIER_KEY = "newlineModifier";

const LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "zh", nativeName: "中文" },
  { code: "ja", nativeName: "日本語" },
  { code: "ko", nativeName: "한국어" },
  { code: "ru", nativeName: "Русский" },
];

type NewlineModifier = "shift" | "ctrl";

const NEWLINE_OPTIONS: { key: NewlineModifier; labelKey: string }[] = [
  { key: "shift", labelKey: "profile.newlineShift" },
  { key: "ctrl", labelKey: "profile.newlineCtrl" },
];

const THEME_OPTIONS: { key: "light" | "dark"; labelKey: string }[] = [
  { key: "light", labelKey: "profile.lightTheme" },
  { key: "dark", labelKey: "profile.darkTheme" },
];

/** Reusable dropdown row */
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [dropUp, setDropUp] = useState(false);

  useEffect(() => {
    if (!open || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    setDropUp(spaceBelow < 120 && spaceAbove > spaceBelow);
  }, [open]);

  return (
    <div className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
      <span className="text-sm text-stone-700 dark:text-stone-200">
        {label}
      </span>
      <div className="relative" ref={containerRef}>
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-stone-100 dark:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-600 transition-colors min-w-[120px] justify-between"
        >
          {loading ? (
            <LoadingSpinner size="xs" />
          ) : (
            <span className="truncate">
              {renderLabel
                ? renderLabel(value)
                : selected
                  ? t(selected.labelKey)
                  : value}
            </span>
          )}
          <ChevronDown
            size={12}
            className={`shrink-0 text-stone-400 transition-transform ${
              open ? "rotate-180" : ""
            }`}
          />
        </button>
        {open && (
          <div
            className={`absolute right-0 z-10 min-w-[160px] rounded-lg bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 shadow-lg overflow-hidden ${
              dropUp ? "bottom-full mb-1" : "top-full mt-1"
            }`}
            style={{ maxHeight: "40vh", overflowY: "auto" }}
          >
            {options.map((opt) => (
              <button
                key={opt.key}
                onClick={() => onSelect(opt.key)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                  value === opt.key
                    ? "bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 font-medium"
                    : "text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"
                }`}
              >
                {renderLabel ? renderLabel(opt.key) : t(opt.labelKey)}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ProfilePreferencesTab() {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useTheme();

  // Dropdown open states
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const toggle = (key: string) =>
    setOpenDropdown((prev) => (prev === key ? null : key));

  // Newline modifier
  const [newlineModifier, setNewlineModifier] = useState<NewlineModifier>(
    () => {
      const stored = localStorage.getItem(NEWLINE_MODIFIER_KEY);
      return stored === "ctrl" ? "ctrl" : "shift";
    },
  );

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

  const handleThemeChange = (newTheme: "light" | "dark") => {
    setTheme(newTheme);
    authApi.updateMetadata({ theme: newTheme }).catch(() => {});
    setOpenDropdown(null);
  };

  const handleNewlineChange = (modifier: NewlineModifier) => {
    setNewlineModifier(modifier);
    localStorage.setItem(NEWLINE_MODIFIER_KEY, modifier);
    authApi.updateMetadata({ newlineModifier: modifier }).catch(() => {});
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

  const agentOptions = agents.map((a) => ({
    key: a.id,
    labelKey: a.name,
  }));

  const renderAgentLabel = (key: string) => {
    const agent = agents.find((a) => a.id === key);
    return agent ? t(agent.name) : key;
  };

  // Close dropdown on outside click
  useEffect(() => {
    if (!openDropdown) return;
    const close = () => setOpenDropdown(null);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [openDropdown]);

  return (
    <div className="rounded-2xl bg-stone-50 dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Settings size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
          {t("profile.preferences")}
        </h3>
      </div>

      <div className="space-y-0" onClick={(e) => e.stopPropagation()}>
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

        <SelectRow
          label={t("profile.newlineModifier")}
          value={newlineModifier}
          options={NEWLINE_OPTIONS}
          open={openDropdown === "newline"}
          onToggle={() => toggle("newline")}
          onSelect={handleNewlineChange}
        />
      </div>
    </div>
  );
}
