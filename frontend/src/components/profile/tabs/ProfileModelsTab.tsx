import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { CatalogStatus } from "../../common/CatalogStatus";
import { ModelIconImg } from "../../agent/modelIcon.tsx";

export function ProfileModelsTab() {
  const { t } = useTranslation();
  const contentRef = useRef<HTMLDivElement>(null);
  const { availableModels, modelsLoading, modelsError, reloadModels } =
    useSettingsContext();
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggle = (id: string) =>
    setExpanded((prev) => (prev === id ? null : id));

  return (
    <div ref={contentRef} tabIndex={-1} className="space-y-3 outline-none">
      <CatalogStatus
        focusTargetRef={contentRef}
        label={t("nav.models")}
        loading={modelsLoading}
        error={modelsError}
        onRetry={reloadModels}
      />
      {availableModels?.length === 0 && !modelsLoading && !modelsError ? (
        <p className="text-14 profile-empty">{t("profile.noModels")}</p>
      ) : (
        <div className="space-y-1.5">
          {availableModels?.map((model) => (
            <div key={model.id} className="profile-model">
              <button
                onClick={() => toggle(model.id)}
                aria-expanded={
                  model.description ? expanded === model.id : undefined
                }
                disabled={!model.description}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-theme-bg-subtle dark:hover:bg-stone-700/30 transition-colors"
              >
                <ModelIconImg
                  model={model.value}
                  provider={model.provider}
                  icon={model.icon}
                  size={22}
                />
                <span className="flex-1 min-w-0 text-14 font-medium font-serif text-theme-text dark:text-stone-200 truncate">
                  {model.label}
                </span>
                {model.provider && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-10 font-medium font-serif capitalize bg-theme-bg-subtle dark:bg-stone-700 text-theme-text-secondary dark:text-stone-400 shrink-0">
                    {model.provider}
                  </span>
                )}
                {model.description && (
                  <ChevronDown
                    size={14}
                    className={`shrink-0 text-theme-text-tertiary transition-transform duration-200 ${
                      expanded === model.id ? "rotate-180" : ""
                    }`}
                  />
                )}
              </button>
              {expanded === model.id && model.description && (
                <div className="profile-model-description">
                  <p className="text-12 text-theme-text-secondary dark:text-stone-400 leading-relaxed">
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
