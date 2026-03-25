import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Save, Check, AlertCircle } from "lucide-react";
import { toast } from "react-hot-toast";
import { AgentInfo } from "../../types";
import { agentConfigApi, agentApi } from "../../services/api";
import { LoadingSpinner } from "../common/LoadingSpinner";

export function UserAgentPreferencePanel() {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [availableAgents, setAvailableAgents] = useState<AgentInfo[]>([]);
  const [currentPreference, setCurrentPreference] = useState<string | null>(
    null,
  );
  const [selectedAgent, setSelectedAgent] = useState<string>("");

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [agentsRes, preferenceRes] = await Promise.all([
        agentApi.list(),
        agentConfigApi
          .getUserPreference()
          .catch(() => ({ default_agent_id: null })),
      ]);

      setAvailableAgents(agentsRes.agents || []);
      setCurrentPreference(preferenceRes.default_agent_id);
      setSelectedAgent(
        preferenceRes.default_agent_id || agentsRes.default_agent || "",
      );
    } catch (err) {
      const errorMsg = (err as Error).message || t("agentConfig.loadFailed");
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSave = async () => {
    if (!selectedAgent) return;

    setIsSaving(true);
    try {
      await agentConfigApi.setUserPreference(selectedAgent);
      setCurrentPreference(selectedAgent);
      toast.success(t("agentConfig.preferenceSaved"));
      window.dispatchEvent(new CustomEvent("agent-preference-updated"));
    } catch (err) {
      toast.error((err as Error).message || t("agentConfig.saveFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  const hasChanges = selectedAgent !== currentPreference;

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-sm">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="rounded-xl bg-stone-50 dark:bg-stone-700/50 p-3 sm:p-4">
        {availableAgents.length === 0 ? (
          <p className="text-sm text-stone-500 dark:text-stone-400 py-2">
            {t("agentConfig.noAvailableAgents")}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {availableAgents.map((agent) => (
              <label
                key={agent.id}
                className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 transition-colors ${
                  selectedAgent === agent.id
                    ? "border-amber-400/60 bg-amber-50/70 dark:border-amber-500/30 dark:bg-amber-900/15"
                    : "border-transparent bg-white/60 dark:bg-stone-600/40 hover:bg-white dark:hover:bg-stone-600/70"
                }`}
              >
                <input
                  type="radio"
                  name="defaultAgent"
                  value={agent.id}
                  checked={selectedAgent === agent.id}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="shrink-0"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                    {t(agent.name)}
                  </span>
                  <span className="block text-xs text-stone-500 dark:text-stone-400 mt-0.5 truncate">
                    {t(agent.description)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {hasChanges && (
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={isSaving || !selectedAgent}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 dark:disabled:bg-amber-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2 text-sm"
          >
            {isSaving ? (
              <>
                <LoadingSpinner size="sm" />
                {t("common.saving")}
              </>
            ) : (
              <>
                <Save size={15} />
                {t("common.save")}
              </>
            )}
          </button>
        </div>
      )}

      {currentPreference && !hasChanges && (
        <div className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
          <Check
            size={16}
            className="text-green-500 dark:text-green-400 shrink-0"
          />
          <span className="truncate">
            {t("agentConfig.currentPreference", {
              agentName: t(
                availableAgents.find((a) => a.id === currentPreference)?.name ||
                  currentPreference,
              ),
            })}
          </span>
        </div>
      )}
    </div>
  );
}
