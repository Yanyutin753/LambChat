/**
 * Providers tab content
 */
import { Cpu, Plus, Pencil, Trash2, Globe, Sparkles, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderBadge } from "./ProviderBadge";
import type { ModelProviderConfig } from "../../../../types";
import { getProviderMeta } from "../../../../types/model";

function ProvidersTab({
  providers,
  legacyMigrationApplied,
  legacyInheritedProviders,
  onAdd,
  onEdit,
  onDelete,
}: {
  providers: ModelProviderConfig[];
  legacyMigrationApplied: boolean;
  legacyInheritedProviders: string[];
  onAdd: () => void;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void | Promise<void>;
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-4">
      {legacyMigrationApplied && (
        <div className="model-config-migration-card rounded-3xl px-4 py-4 sm:px-5">
          <div className="flex items-start gap-3">
            <div className="model-config-migration-card__icon flex h-10 w-10 items-center justify-center rounded-2xl">
              <ShieldCheck size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-[var(--theme-text)]">
                  {t("modelConfig.migrationAppliedTitle")}
                </p>
                <span className="model-config-migration-badge">
                  <Sparkles size={12} />
                  {t("modelConfig.migrationAppliedBadge")}
                </span>
              </div>
              <p className="mt-1 text-sm text-[var(--theme-text-secondary)]">
                {t("modelConfig.migrationAppliedDescription")}
              </p>
            </div>
          </div>
        </div>
      )}

      {providers.length > 0 && (
        <div className="model-config-subtle-card rounded-2xl px-4 py-3 text-sm text-[var(--theme-text-secondary)]">
          {t("modelConfig.providersDescription")}
        </div>
      )}

      <div className="space-y-3">
        {providers.map((provider, idx) => (
          <ProviderSummaryCard
            key={idx}
            provider={provider}
            isLegacyInherited={legacyInheritedProviders.includes(provider.provider)}
            onEdit={() => onEdit(idx)}
            onDelete={() => onDelete(idx)}
          />
        ))}
      </div>

      {providers.length === 0 && (
        <div className="model-config-empty flex flex-col items-center justify-center rounded-3xl px-6 py-16 text-center shadow-sm">
          <div className="model-config-empty-icon mb-4 flex h-16 w-16 items-center justify-center rounded-2xl">
            <Cpu size={28} style={{ color: "var(--theme-primary)" }} />
          </div>
          <p className="mb-1 text-sm font-medium text-[var(--theme-text)]">
            {t("modelConfig.noProviders")}
          </p>
          <p className="mb-4 max-w-[320px] text-xs text-[var(--theme-text-secondary)]">
            {t("modelConfig.noProvidersDescription")}
          </p>
          <button onClick={onAdd} className="btn-primary">
            <Plus size={14} />
            {t("modelConfig.addProvider")}
          </button>
        </div>
      )}

    </div>
  );
}

function ProviderSummaryCard({
  provider,
  isLegacyInherited,
  onEdit,
  onDelete,
}: {
  provider: ModelProviderConfig;
  isLegacyInherited: boolean;
  onEdit: () => void;
  onDelete: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const meta = getProviderMeta(provider.provider);
  const brandColor = meta?.color || "#78716c";
  const modelCount = provider.models.length;

  return (
    <div className="model-config-provider-card rounded-3xl p-4 shadow-sm sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <ProviderBadge provider={provider.provider} size="sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-[var(--theme-text)] sm:text-base">
                {provider.label || meta?.display_name || provider.provider}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span
                  className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                  style={{
                    backgroundColor: `${brandColor}15`,
                    color: brandColor,
                  }}
                >
                  {meta?.display_name || provider.provider}
                </span>
                <span className="text-xs text-[var(--theme-text-secondary)]">
                  {t("modelConfig.modelCount", { count: modelCount })}
                </span>
                {isLegacyInherited && (
                  <span className="model-config-migration-badge">
                    <Sparkles size={12} />
                    {t("modelConfig.inheritedFromLegacy")}
                  </span>
                )}
              </div>
            </div>
          </div>

          {provider.base_url && (
            <div className="mt-4 flex items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
              <Globe size={13} />
              <span className="truncate">{provider.base_url}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button onClick={onEdit} className="btn-icon" title={t("common.edit")}>
            <Pencil size={16} />
          </button>
          <button
            onClick={onDelete}
            className="btn-icon model-config-icon-button--danger"
            title={t("modelConfig.deleteProvider")}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default ProvidersTab;
