import type { AvailableModel } from "../../contexts/SettingsContext";
import {
  hasEffectiveCorePersonaSuppressingOption,
  importLegacyPayloadPluginOptions,
  legacyPayloadKeysForPluginOption,
  pluginOptionFromMetadata,
  pluginOptionsFromMetadata,
  retainPluginOptionsForDeclarations,
  withPluginOption,
} from "../../extensions/pluginOptions";
import type {
  PluginOptionsMetadata,
  ScopedPluginOptionLike,
} from "../../extensions/pluginOptions";

export function getAgentOptionsFromScheduledTaskPayload(
  payload: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const options = payload?.agent_options;
  return options && typeof options === "object" && !Array.isArray(options)
    ? (options as Record<string, unknown>)
    : {};
}

export function withoutScheduledTaskModelOptions(
  options: Record<string, unknown>,
): Record<string, unknown> {
  const next = { ...options };
  delete next.model_id;
  delete next.model;
  delete next._resolved_model_config;
  delete next._resolved_supports_vision;
  delete next._resolved_image_url_to_base64;
  delete next._resolved_fallback_model;
  delete next._resolved_model_profile;
  return next;
}

export function getScheduledTaskPersonaPresetId(
  payload: Record<string, unknown> | undefined,
): string {
  const value = payload?.persona_preset_id;
  return typeof value === "string" ? value : "";
}

export function getScheduledTaskPluginOptionStringValue(
  payload: Record<string, unknown> | undefined,
  option: ScopedPluginOptionLike,
): string {
  const pluginId = option.plugin_id ?? option.pluginId;
  if (!pluginId) return "";

  const value = pluginOptionFromMetadata(payload, pluginId, option.key);
  if (typeof value === "string" && value.trim()) return value;

  for (const legacyKey of legacyPayloadKeysForPluginOption(option)) {
    const legacyValue = payload?.[legacyKey];
    if (typeof legacyValue === "string" && legacyValue.trim()) {
      return legacyValue;
    }
  }
  return "";
}

function applyPluginOptionValues(
  payload: Record<string, unknown>,
  values: PluginOptionsMetadata | undefined,
): Record<string, unknown> {
  let nextPayload = payload;
  for (const [pluginId, pluginValues] of Object.entries(values ?? {})) {
    for (const [key, value] of Object.entries(pluginValues)) {
      nextPayload = withPluginOption(nextPayload, pluginId, key, value);
    }
  }
  return nextPayload;
}

function applyDeclaredPluginOptions(
  payload: Record<string, unknown>,
  originalPayload: Record<string, unknown>,
  values: PluginOptionsMetadata | undefined,
  declarations: readonly ScopedPluginOptionLike[],
): Record<string, unknown> {
  const imported = importLegacyPayloadPluginOptions(originalPayload, declarations);
  const merged = applyPluginOptionValues(
    { ...payload, plugin_options: imported },
    values,
  );
  const retained = retainPluginOptionsForDeclarations(
    pluginOptionsFromMetadata(merged),
    declarations,
  );

  if (Object.keys(retained).length > 0) {
    return { ...merged, plugin_options: retained };
  }

  const nextPayload = { ...merged };
  delete nextPayload.plugin_options;
  return nextPayload;
}

export function buildScheduledTaskInputPayload(
  payload: Record<string, unknown>,
  {
    modelId,
    modelValue,
    availableModels,
    personaPresetId = "",
    pluginOptionValues,
    pluginOptionDeclarations,
  }: {
    agentId?: string;
    modelId: string;
    modelValue: string;
    availableModels: AvailableModel[] | null;
    personaPresetId?: string;
    pluginOptionValues?: PluginOptionsMetadata;
    pluginOptionDeclarations?: readonly ScopedPluginOptionLike[];
  },
): Record<string, unknown> {
  const selectedModel = availableModels?.find((model) => model.id === modelId);
  const nextAgentOptions = {
    ...withoutScheduledTaskModelOptions(
      getAgentOptionsFromScheduledTaskPayload(payload),
    ),
    ...(modelId ? { model_id: modelId } : {}),
    ...(selectedModel?.value || modelValue
      ? { model: selectedModel?.value || modelValue }
      : {}),
  };
  const nextPayload = { ...payload };
  delete nextPayload.agent_options;
  delete nextPayload.persona_preset_id;
  delete nextPayload.team_id;
  if (Object.keys(nextAgentOptions).length > 0) {
    nextPayload.agent_options = nextAgentOptions;
  }

  const hasPluginOptionDeclarations = Boolean(pluginOptionDeclarations?.length);
  if (hasPluginOptionDeclarations) {
    delete nextPayload.plugin_options;
    Object.assign(
      nextPayload,
      applyDeclaredPluginOptions(
        nextPayload,
        payload,
        pluginOptionValues,
        pluginOptionDeclarations ?? [],
      ),
    );
    if (personaPresetId && !hasEffectiveCorePersonaSuppressingOption(pluginOptionDeclarations)) {
      nextPayload.persona_preset_id = personaPresetId;
    }
    return nextPayload;
  }

  const currentPluginOptions = pluginOptionsFromMetadata(nextPayload);
  delete nextPayload.plugin_options;
  Object.assign(
    nextPayload,
    applyPluginOptionValues(
      { ...nextPayload, plugin_options: currentPluginOptions },
      pluginOptionValues,
    ),
  );
  if (personaPresetId && !hasPluginOptionDeclarations) {
    nextPayload.persona_preset_id = personaPresetId;
  }
  return nextPayload;
}
