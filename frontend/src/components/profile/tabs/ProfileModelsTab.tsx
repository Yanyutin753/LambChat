import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Cpu, ChevronDown } from "lucide-react";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { ModelIconImg } from "../../agent/modelIcon.tsx";

export function ProfileModelsTab() {
  const { t } = useTranslation();
  const { availableModels } = useSettingsContext();
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggle = (id: string) =>
    setExpanded((prev) => (prev === id ? null : id));

  return (
    <div className="rounded-2xl bg-stone-50 dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Cpu size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
          {t("profile.modelIntro")}
        </h3>
      </div>

      {!availableModels || availableModels.length === 0 ? (
        <p className="text-sm text-stone-400 dark:text-stone-500 py-4 text-center">
          {t("profile.noModels")}
        </p>
      ) : (
        <div className="space-y-1.5">
          {availableModels.map((model) => (
            <div
              key={model.id}
              className="rounded-lg bg-white dark:bg-stone-800/60 border border-stone-100 dark:border-stone-700/50 overflow-hidden"
            >
              <button
                onClick={() => toggle(model.id)}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-stone-50 dark:hover:bg-stone-700/30 transition-colors"
              >
                <ModelIconImg
                  model={model.value}
                  provider={model.provider}
                  size={22}
                />
                <span className="flex-1 min-w-0 text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
                  {model.label}
                </span>
                {model.provider && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-stone-100 dark:bg-stone-700 text-stone-500 dark:text-stone-400 shrink-0">
                    {model.provider}
                  </span>
                )}
                {model.description && (
                  <ChevronDown
                    size={14}
                    className={`shrink-0 text-stone-400 transition-transform duration-200 ${
                      expanded === model.id ? "rotate-180" : ""
                    }`}
                  />
                )}
              </button>
              {expanded === model.id && model.description && (
                <div className="px-3 pb-2.5 pt-0">
                  <p className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed">
                    {model.description}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
