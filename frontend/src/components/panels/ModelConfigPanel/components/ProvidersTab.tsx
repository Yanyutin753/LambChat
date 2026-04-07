/**
 * Providers tab content
 */
import { Cpu, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderEditor } from "./ProviderEditor";
import type { ModelProviderConfig } from "../../../../types";

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
        className="text-sm px-1 hidden sm:block"
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
            style={{
              background: "var(--theme-primary-light)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
            }}
          >
            <Cpu size={36} style={{ color: "var(--theme-primary)" }} />
          </div>
          <p
            className="text-sm font-medium mb-1"
            style={{ color: "var(--theme-text)" }}
          >
            {t("modelConfig.noProviders")}
          </p>
          <p
            className="text-xs"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            Add your first AI provider to get started
          </p>
        </div>
      )}

      <button
        onClick={onAdd}
        className="w-full rounded-2xl border-2 border-dashed p-5 text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2 hover:border-solid"
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

export default ProvidersTab;
