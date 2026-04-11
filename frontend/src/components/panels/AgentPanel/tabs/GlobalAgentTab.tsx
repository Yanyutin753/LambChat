import { useState, useEffect } from "react";
import { Bot, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../../common/LoadingSpinner";
import { ToggleSwitch } from "../shared/ToggleSwitch";
import type { AgentConfig } from "../../../../types";

interface GlobalAgentTabProps {
  agents: AgentConfig[];
  onUpdate: (agents: AgentConfig[]) => Promise<void>;
  isLoading: boolean;
  isSaving: boolean;
}

export function GlobalAgentTab({
  agents,
  onUpdate,
  isLoading,
  isSaving,
}: GlobalAgentTabProps) {
  const { t } = useTranslation();
  const [localAgents, setLocalAgents] = useState<AgentConfig[]>(agents);

  useEffect(() => {
    setLocalAgents(agents);
  }, [agents]);

  const toggleAgent = (agentId: string) => {
    setLocalAgents((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, enabled: !a.enabled } : a)),
    );
  };

  const handleSave = async () => {
    try {
      await onUpdate(localAgents);
    } catch (err) {
      console.error("Failed to save:", err);
    }
  };

  const hasChanges = JSON.stringify(localAgents) !== JSON.stringify(agents);

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-stone-500 dark:text-stone-400 px-1 leading-relaxed">
        {t("agentConfig.globalDescription")}
      </p>

      <div className="grid gap-3">
        {localAgents.map((agent) => (
          <div
            key={agent.id}
            className="group flex items-center justify-between rounded-xl border border-stone-200/60 bg-white/70 p-4 transition-all duration-200 hover:border-stone-300/80 hover:bg-white/90 hover:shadow-md hover:shadow-stone-200/20 dark:border-stone-700/40 dark:bg-stone-800/40 dark:hover:border-stone-600/60 dark:hover:bg-stone-800/70 dark:hover:shadow-stone-900/20"
          >
            <div className="flex items-center gap-3.5 min-w-0 flex-1">
              <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-stone-100 to-stone-200/80 dark:from-stone-700/80 dark:to-stone-800/60 ring-1 ring-stone-200/50 dark:ring-stone-700/50 shadow-sm">
                <Bot size={24} className="text-stone-600 dark:text-stone-400" />
              </div>
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate tracking-tight font-serif">
                  {t(agent.name)}
                </h4>
                <p className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5 hidden sm:block">
                  {t(agent.description)}
                </p>
              </div>
            </div>

            <ToggleSwitch
              enabled={agent.enabled}
              onToggle={() => toggleAgent(agent.id)}
              ariaLabel={
                agent.enabled
                  ? t("agentConfig.disableAgent", { name: t(agent.name) })
                  : t("agentConfig.enableAgent", { name: t(agent.name) })
              }
            />
          </div>
        ))}
      </div>

      {hasChanges && (
        <div className="flex justify-end pt-3">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm"
          >
            {isSaving ? (
              <>
                <LoadingSpinner size="sm" />
                {t("common.saving")}
              </>
            ) : (
              <>
                <Save size={16} />
                {t("common.save")}
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
