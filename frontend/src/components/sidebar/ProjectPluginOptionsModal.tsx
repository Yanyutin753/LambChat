import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Save, X } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import type { CoreScopedPluginOptionContribution } from "../../extensions/coreContributions";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { pluginRuntimeApi } from "../../services/api/pluginRuntime";
import { projectApi } from "../../services/api/project";
import type { Project } from "../../types";
import type { ExtensionScopedOption } from "../../types/pluginRuntime";
import { renderProjectOptionField } from "./projectOptionRenderers";

interface ProjectPluginOptionsModalProps {
  project: Project | null;
  onClose: () => void;
}

type OptionValues = Record<string, unknown>;

function getStoredValue(values: OptionValues, option: CoreScopedPluginOptionContribution) {
  const pluginValues = values[option.pluginId];
  if (pluginValues && typeof pluginValues === "object" && !Array.isArray(pluginValues)) {
    const value = (pluginValues as Record<string, unknown>)[option.key];
    if (value !== undefined) return value;
  }
  return option.defaultValue ?? null;
}

function hasStoredValue(
  values: OptionValues,
  option: CoreScopedPluginOptionContribution,
): boolean {
  const pluginValues = values[option.pluginId];
  if (!pluginValues || typeof pluginValues !== "object" || Array.isArray(pluginValues)) {
    return false;
  }
  const value = (pluginValues as Record<string, unknown>)[option.key];
  return value !== null && value !== undefined && value !== "";
}

function setStoredValue(
  values: OptionValues,
  option: CoreScopedPluginOptionContribution,
  value: unknown,
): OptionValues {
  return {
    ...values,
    [option.pluginId]: {
      ...((values[option.pluginId] as Record<string, unknown> | undefined) ?? {}),
      [option.key]: value,
    },
  };
}

function coerceOptionValue(option: CoreScopedPluginOptionContribution, value: unknown) {
  if (value === "" || value === undefined) return null;
  if (option.type === "number") {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : null;
  }
  if (option.type === "boolean") return Boolean(value);
  if (option.type === "json") {
    if (typeof value !== "string") return value;
    try {
      return JSON.parse(value);
    } catch {
      throw new Error(`Invalid JSON for ${option.id}`);
    }
  }
  return value;
}

function optionFromHost(
  option: ExtensionScopedOption,
): CoreScopedPluginOptionContribution {
  return {
    id: option.id,
    pluginId: option.plugin_id,
    pluginEnabled: option.plugin_enabled,
    effective: option.effective,
    pluginStatus: option.plugin_status,
    key: option.key,
    type: option.type,
    label: option.label,
    description: option.description,
    defaultValue: option.default_value,
    group: option.group,
    order: option.order,
    options: option.options,
    jsonSchema: option.json_schema,
    renderer: option.renderer,
    suppressesCorePersonaSelector: option.suppresses_core_persona_selector ?? false,
    legacyPayloadKeys: option.legacy_payload_keys ?? [],
    visibleWhen: option.visible_when,
    area: "project_option",
  };
}

function DefaultOptionField({
  option,
  value,
  disabled,
  onChange,
}: {
  option: CoreScopedPluginOptionContribution;
  value: unknown;
  disabled?: boolean;
  onChange: (value: unknown) => void;
}) {
  if (option.type === "boolean") {
    return (
      <label className="inline-flex items-center gap-2 text-sm text-stone-600 dark:text-stone-300">
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 rounded border-stone-300 text-stone-700 focus:ring-stone-400 dark:border-stone-600"
        />
        Enabled
      </label>
    );
  }

  if (option.type === "select" && option.options?.length) {
    return (
      <select
        value={typeof value === "string" ? value : ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        className="w-full rounded-md border border-stone-200 bg-white px-2 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      >
        <option value="">None</option>
        {option.options.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    );
  }

  if (option.type === "text" || option.type === "json") {
    return (
      <textarea
        value={option.type === "json" && typeof value !== "string" ? JSON.stringify(value ?? {}, null, 2) : String(value ?? "")}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        rows={option.type === "json" ? 5 : 3}
        className="w-full resize-y rounded-md border border-stone-200 bg-white px-2 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      />
    );
  }

  return (
    <input
      type={option.type === "number" ? "number" : "text"}
      value={typeof value === "string" || typeof value === "number" ? value : ""}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-md border border-stone-200 bg-white px-2 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-stone-400 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
    />
  );
}

export function ProjectPluginOptionsModal({
  project,
  onClose,
}: ProjectPluginOptionsModalProps) {
  const { t } = useTranslation();
  const [values, setValues] = useState<OptionValues>({});
  const [options, setOptions] = useState<CoreScopedPluginOptionContribution[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const isOpen = Boolean(project);
  useBodyScrollLock(isOpen);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      pluginRuntimeApi.listProjectOptions({ includeInactive: true }),
      projectApi.getPluginOptions(project.id),
    ])
      .then(([optionResponse, valueResponse]) => {
        if (cancelled) return;
        setOptions(optionResponse.options.map(optionFromHost));
        setValues(valueResponse.plugin_options);
      })
      .catch((error) => {
        console.error("Failed to load project plugin options:", error);
        if (!cancelled) {
          setOptions([]);
          setValues({});
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [project]);

  if (!project) return null;

  const visibleOptions = options.filter((option) => {
    if (option.effective !== false) return true;
    return hasStoredValue(values, option);
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      for (const option of visibleOptions) {
        const value = coerceOptionValue(option, getStoredValue(values, option));
        await projectApi.updatePluginOption(project.id, option.pluginId, option.key, value);
      }
      toast.success(t("sidebar.projectOptionsSaved", "Project options saved"));
      onClose();
    } catch (error) {
      console.error("Failed to save project plugin options:", error);
      toast.error(t("sidebar.projectOptionsSaveFailed", "Failed to save project options"));
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <div
      data-yields-sidebar
      className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-center justify-center"
    >
      <div className="absolute inset-0 bg-black/40" onClick={saving ? undefined : onClose} />
      <div className="relative flex max-h-[86dvh] w-[92vw] max-w-lg flex-col overflow-hidden rounded-xl border border-stone-200 bg-white shadow-2xl dark:border-stone-700 dark:bg-stone-900">
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4 dark:border-stone-700">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-stone-800 dark:text-stone-100">
              {t("sidebar.projectOptions", "Project options")}
            </h3>
            <p className="truncate text-xs text-stone-400 dark:text-stone-500">
              {project.name}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            className="flex h-7 w-7 items-center justify-center rounded-md text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700 disabled:opacity-50 dark:hover:bg-stone-800 dark:hover:text-stone-200"
          >
            <X size={15} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-8 text-center text-sm text-stone-400">Loading...</div>
          ) : visibleOptions.length === 0 ? (
            <div className="py-8 text-center text-sm text-stone-400">
              No plugin project options
            </div>
          ) : (
            <div className="space-y-4">
              {visibleOptions.map((option) => {
                const value = getStoredValue(values, option);
                const inactive = option.effective === false;
                const fieldDisabled = saving || inactive;
                const customField = renderProjectOptionField({
                  option,
                  value,
                  disabled: fieldDisabled,
                  onChange: (nextValue) =>
                    setValues((current) => setStoredValue(current, option, nextValue)),
                });
                return (
                  <div key={option.id} className="space-y-1.5">
                    <div className="flex items-center justify-between gap-3">
                      <label className="text-sm font-medium text-stone-700 dark:text-stone-200">
                        {t(option.label, option.label)}
                      </label>
                      <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                        {option.pluginId}
                      </span>
                    </div>
                    {!option.effective && (
                      <p className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                        {t(
                          "sidebar.projectOptionInactive",
                          "This plugin is disabled. The value is saved but currently has no effect.",
                        )}
                      </p>
                    )}
                    {option.description && (
                      <p className="text-xs text-stone-400 dark:text-stone-500">
                        {t(option.description, option.description)}
                      </p>
                    )}
                    {customField ?? (
                      <DefaultOptionField
                        option={option}
                        value={value}
                        disabled={fieldDisabled}
                        onChange={(nextValue) =>
                          setValues((current) => setStoredValue(current, option, nextValue))
                        }
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-stone-200 px-5 py-3 dark:border-stone-700">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-lg px-3 py-2 text-sm font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-800 disabled:opacity-50 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading || visibleOptions.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-stone-800 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-white"
          >
            <Save size={14} />
            {t("common.save", "Save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
