import { Settings2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ExtensionScopedOption } from "../../../types";
import { ChannelTeamSelect } from "./ChannelTeamSelect";

export type ChannelPluginOptionValues = Record<string, Record<string, unknown>>;

interface ChannelPluginOptionsProps {
  options: readonly ExtensionScopedOption[];
  values: ChannelPluginOptionValues;
  disabled?: boolean;
  onChange: (pluginId: string, key: string, value: unknown) => void;
}

interface ChannelOptionRendererProps {
  option: ExtensionScopedOption;
  value: unknown;
  disabled?: boolean;
  inactive?: boolean;
  onChange: (value: unknown) => void;
}

type ChannelOptionRenderer = (props: ChannelOptionRendererProps) => ReactNode;

function valueFor(
  values: ChannelPluginOptionValues,
  pluginId: string,
  key: string,
): unknown {
  return values[pluginId]?.[key];
}

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function asInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
}

function parseJsonValue(value: string): unknown {
  if (!value.trim()) return null;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function optionInputType(option: ExtensionScopedOption): "text" | "number" {
  return option.type === "number" ? "number" : "text";
}

function AgentTeamChannelTeamSelect({
  value,
  disabled,
  inactive,
  onChange,
}: ChannelOptionRendererProps) {
  return (
    <ChannelTeamSelect
      value={typeof value === "string" ? value : null}
      onChange={onChange}
      disabled={disabled}
      loadTeams={!inactive}
    />
  );
}

const CHANNEL_OPTION_RENDERERS: Record<string, ChannelOptionRenderer> = {
  "agent_team.TeamSelectOption": AgentTeamChannelTeamSelect,
};

export function ChannelPluginOptions({
  options,
  values,
  disabled,
  onChange,
}: ChannelPluginOptionsProps) {
  const { t } = useTranslation();
  const visibleOptions = options.filter((option) => {
    if (option.effective !== false) return true;
    return hasValue(valueFor(values, option.plugin_id, option.key));
  });

  if (!visibleOptions.length) return null;

  return (
    <div className="space-y-3">
      <div className="es-section-title flex items-center gap-1.5">
        <Settings2 size={14} />
        {t("channel.pluginOptions", "Plugin Options")}
      </div>
      {visibleOptions.map((option) => {
        const currentValue = valueFor(values, option.plugin_id, option.key);
        const fieldId = `${option.plugin_id}.${option.key}`;
        const inactive = option.effective === false;
        const fieldDisabled = disabled || inactive;

        const inactiveNotice = inactive ? (
          <p className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            {t(
              "channel.pluginOptionInactive",
              "Plugin disabled; saved value is retained but will not apply.",
            )}
          </p>
        ) : null;

        const CustomRenderer = option.renderer
          ? CHANNEL_OPTION_RENDERERS[option.renderer]
          : null;

        if (CustomRenderer) {
          return (
            <div key={fieldId}>
              <CustomRenderer
                option={option}
                value={currentValue}
                disabled={fieldDisabled}
                inactive={inactive}
                onChange={(value) => onChange(option.plugin_id, option.key, value)}
              />
              {inactiveNotice}
            </div>
          );
        }

        if (option.type === "boolean") {
          return (
            <label key={fieldId} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--theme-border)] bg-[var(--glass-bg-subtle)] px-3 py-2">
              <span className="min-w-0">
                <span className="block text-sm font-medium text-[var(--theme-text)]">
                  {t(option.label, option.label || option.key)}
                </span>
                {option.description && (
                  <span className="block text-xs text-[var(--theme-text-secondary)]">
                    {t(option.description, option.description)}
                  </span>
                )}
              </span>
              <input
                type="checkbox"
                checked={Boolean(currentValue)}
                disabled={fieldDisabled}
                onChange={(event) =>
                  onChange(option.plugin_id, option.key, event.target.checked)
                }
              />
              {inactiveNotice}
            </label>
          );
        }

        if (option.type === "select" && option.options?.length) {
          return (
            <div key={fieldId} className="es-field">
              <label className="es-label">{t(option.label, option.label || option.key)}</label>
              <select
                value={asInputValue(currentValue)}
                disabled={fieldDisabled}
                onChange={(event) =>
                  onChange(option.plugin_id, option.key, event.target.value || null)
                }
                className="glass-input es-input"
              >
                <option value="">{t("common.none", "None")}</option>
                {option.options.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              {inactiveNotice}
            </div>
          );
        }

        if (option.type === "json" || option.type === "text") {
          return (
            <div key={fieldId} className="es-field">
              <label className="es-label">{t(option.label, option.label || option.key)}</label>
              <textarea
                value={
                  typeof currentValue === "object" && currentValue !== null
                    ? JSON.stringify(currentValue, null, 2)
                    : asInputValue(currentValue)
                }
                disabled={fieldDisabled}
                rows={3}
                onChange={(event) =>
                  onChange(
                    option.plugin_id,
                    option.key,
                    option.type === "json"
                      ? parseJsonValue(event.target.value)
                      : event.target.value,
                  )
                }
                className="glass-input es-input min-h-[5rem] resize-y"
              />
              {inactiveNotice}
            </div>
          );
        }

        return (
          <div key={fieldId} className="es-field">
            <label className="es-label">{t(option.label, option.label || option.key)}</label>
            <input
              type={optionInputType(option)}
              value={asInputValue(currentValue)}
              disabled={fieldDisabled}
              onChange={(event) =>
                onChange(
                  option.plugin_id,
                  option.key,
                  option.type === "number"
                    ? Number(event.target.value || 0)
                    : event.target.value || null,
                )
              }
              className="glass-input es-input"
            />
            {inactiveNotice}
          </div>
        );
      })}
    </div>
  );
}
