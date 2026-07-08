const AGENT_TEAM_PLUGIN_ID = "agent_team";
const AGENT_TEAM_SELECTED_TEAM_OPTION = "SELECTED_TEAM_ID";

export type PluginOptionsMetadata = Record<string, Record<string, unknown>>;

export interface PluginOptionPath {
  pluginId: string;
  key: string;
}

export interface AgentLike {
  id: string;
}

export interface ScopedPluginOptionLike {
  plugin_id?: string;
  pluginId?: string;
  key: string;
  effective?: boolean;
  suppresses_core_persona_selector?: boolean;
  suppressesCorePersonaSelector?: boolean;
  legacy_payload_keys?: readonly string[] | null;
  legacyPayloadKeys?: readonly string[] | null;
  visible_when?: PluginOptionVisibleWhen | null;
  visibleWhen?: PluginOptionVisibleWhen | null;
}

export interface PluginOptionVisibleWhen {
  agent_id?: string | null;
  route?: string | null;
  scope?: string | null;
  permissions?: string[] | null;
}

export interface PluginOptionVisibilityContext {
  agentId?: string | null;
  route?: string | null;
  scope?: string | null;
  permissions?: readonly string[] | null;
}

export interface MetadataWithPluginOptions {
  plugin_options?: PluginOptionsMetadata | null;
  team_id?: unknown;
}

export function pluginOptionsFromMetadata(
  metadata: MetadataWithPluginOptions | null | undefined,
): PluginOptionsMetadata {
  const rawOptions = metadata?.plugin_options;
  if (!rawOptions || typeof rawOptions !== "object") return {};
  return Object.fromEntries(
    Object.entries(rawOptions).flatMap(([pluginId, values]) => {
      if (!pluginId || !values || typeof values !== "object") return [];
      return [[pluginId, { ...values }]];
    }),
  );
}

export function pluginOptionFromMetadata(
  metadata: MetadataWithPluginOptions | null | undefined,
  pluginId: string,
  key: string,
): unknown {
  return pluginOptionsFromMetadata(metadata)[pluginId]?.[key];
}

export function pluginOptionFromValues(
  values: PluginOptionsMetadata | null | undefined,
  pluginId: string,
  key: string,
): unknown {
  return values?.[pluginId]?.[key];
}

export function withPluginOption<T extends Record<string, unknown>>(
  metadata: T,
  pluginId: string,
  key: string,
  value: unknown,
): T & { plugin_options?: PluginOptionsMetadata } {
  const next: T & { plugin_options?: PluginOptionsMetadata } = { ...metadata };
  const pluginOptions = pluginOptionsFromMetadata(
    next as MetadataWithPluginOptions,
  );
  const pluginValues = { ...(pluginOptions[pluginId] ?? {}) };

  if (value === null || value === undefined || value === "") {
    delete pluginValues[key];
  } else {
    pluginValues[key] = value;
  }

  if (Object.keys(pluginValues).length > 0) {
    pluginOptions[pluginId] = pluginValues;
  } else {
    delete pluginOptions[pluginId];
  }

  if (Object.keys(pluginOptions).length > 0) {
    next.plugin_options = pluginOptions;
  } else {
    delete next.plugin_options;
  }

  return next;
}

export function selectedAgentTeamIdFromMetadata(
  metadata: MetadataWithPluginOptions | null | undefined,
): string | null {
  const selectedTeamId = pluginOptionFromMetadata(
    metadata,
    AGENT_TEAM_PLUGIN_ID,
    AGENT_TEAM_SELECTED_TEAM_OPTION,
  );
  if (typeof selectedTeamId === "string" && selectedTeamId.trim()) {
    return selectedTeamId;
  }

  const legacyTeamId = metadata?.team_id;
  return typeof legacyTeamId === "string" && legacyTeamId.trim()
    ? legacyTeamId
    : null;
}

export function pluginOptionPathFromDeclaration(
  option: ScopedPluginOptionLike,
): PluginOptionPath {
  return {
    pluginId: option.plugin_id ?? option.pluginId ?? "",
    key: option.key,
  };
}

export function legacyPayloadKeysForPluginOption(
  option: ScopedPluginOptionLike,
): readonly string[] {
  return option.legacy_payload_keys ?? option.legacyPayloadKeys ?? [];
}

export function importLegacyPayloadPluginOptions(
  payload: Record<string, unknown> | null | undefined,
  declarations: readonly ScopedPluginOptionLike[] | null | undefined,
  existingValues: PluginOptionsMetadata | null | undefined = pluginOptionsFromMetadata(payload),
): PluginOptionsMetadata {
  let metadata: { plugin_options?: PluginOptionsMetadata } = {
    plugin_options: pluginOptionsFromMetadata({ plugin_options: existingValues ?? {} }),
  };
  for (const option of declarations ?? []) {
    const pluginId = option.plugin_id ?? option.pluginId;
    if (!pluginId || !option.key) continue;
    if (pluginOptionFromValues(metadata.plugin_options, pluginId, option.key) !== undefined) {
      continue;
    }
    for (const legacyKey of legacyPayloadKeysForPluginOption(option)) {
      const value = payload?.[legacyKey];
      if (typeof value === "string" && value.trim()) {
        metadata = withPluginOption(metadata, pluginId, option.key, value);
        break;
      }
    }
  }
  return metadata.plugin_options ?? {};
}

export function firstEffectivePluginOptionPath(
  options: readonly ScopedPluginOptionLike[] | null | undefined,
  { effectiveOnly = false }: { effectiveOnly?: boolean } = {},
): PluginOptionPath | null {
  const option = options?.find(
    (item) =>
      Boolean(item.plugin_id ?? item.pluginId) &&
      Boolean(item.key) &&
      (!effectiveOnly || item.effective !== false),
  );
  return option ? pluginOptionPathFromDeclaration(option) : null;
}

export function matchesPluginOptionVisibleWhen(
  visibleWhen: PluginOptionVisibleWhen | null | undefined,
  context: PluginOptionVisibilityContext = {},
): boolean {
  if (!visibleWhen) return true;
  if (visibleWhen.agent_id && visibleWhen.agent_id !== (context.agentId ?? null)) {
    return false;
  }
  if (visibleWhen.route && visibleWhen.route !== (context.route ?? null)) {
    return false;
  }
  if (visibleWhen.scope && visibleWhen.scope !== (context.scope ?? null)) {
    return false;
  }
  if (visibleWhen.permissions?.length) {
    const available = new Set(context.permissions ?? []);
    return visibleWhen.permissions.every((permission) => available.has(permission));
  }
  return true;
}

export function pluginOptionVisibleWhen(
  option: ScopedPluginOptionLike,
): PluginOptionVisibleWhen | null | undefined {
  return option.visible_when ?? option.visibleWhen;
}

export function filterPluginOptionsByVisibleWhen<T extends ScopedPluginOptionLike>(
  options: readonly T[] | null | undefined,
  context: PluginOptionVisibilityContext = {},
): T[] {
  return (options ?? []).filter((option) =>
    matchesPluginOptionVisibleWhen(pluginOptionVisibleWhen(option), context),
  );
}

export function pluginOptionSuppressesCorePersonaSelector(
  option: ScopedPluginOptionLike,
): boolean {
  return Boolean(
    option.suppresses_core_persona_selector ?? option.suppressesCorePersonaSelector,
  );
}

export function hasEffectiveCorePersonaSuppressingOption(
  options: readonly ScopedPluginOptionLike[] | null | undefined,
): boolean {
  return Boolean(
    options?.some(
      (option) =>
        option.effective !== false && pluginOptionSuppressesCorePersonaSelector(option),
    ),
  );
}

export function retainPluginOptionsForDeclarations(
  values: PluginOptionsMetadata | null | undefined,
  declarations: readonly ScopedPluginOptionLike[] | null | undefined,
): PluginOptionsMetadata {
  const allowed = new Set(
    (declarations ?? []).flatMap((option) => {
      const pluginId = option.plugin_id ?? option.pluginId;
      return pluginId && option.key ? [`${pluginId}.${option.key}`] : [];
    }),
  );
  if (allowed.size === 0) return {};

  const current = pluginOptionsFromMetadata({ plugin_options: values ?? {} });
  const retained: PluginOptionsMetadata = {};
  for (const [pluginId, pluginValues] of Object.entries(current)) {
    for (const [key, value] of Object.entries(pluginValues)) {
      if (!allowed.has(`${pluginId}.${key}`)) continue;
      retained[pluginId] = { ...(retained[pluginId] ?? {}), [key]: value };
    }
  }
  return retained;
}
