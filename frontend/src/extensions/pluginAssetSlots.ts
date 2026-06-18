import {
  buildPluginAssetSlotContributions,
  type CorePluginAssetSlotContribution,
  type PluginRuntimeContributionStates,
} from "./coreContributions";

export const PLUGIN_FRONTEND_ASSET_SCHEMA = "lambchat.plugin.frontend-assets.v1";

export interface PluginAssetSlotRegistryEntry {
  id: string;
  pluginId: string;
  slot: string;
  assetSchema: string;
  assets: readonly string[];
  mountPath: string;
}

function isSafeRelativeAssetPath(assetPath: string): boolean {
  const normalized = assetPath.replace(/\\/g, "/").trim();
  if (!normalized || normalized.startsWith("/") || normalized.includes(":")) {
    return false;
  }
  return normalized.split("/").every((part) => part && part !== "." && part !== "..");
}

function toRegistryEntry(
  contribution: CorePluginAssetSlotContribution,
): PluginAssetSlotRegistryEntry | null {
  if (contribution.assetSchema !== PLUGIN_FRONTEND_ASSET_SCHEMA) return null;
  const assets = contribution.assets.filter(isSafeRelativeAssetPath);
  if (assets.length !== contribution.assets.length) return null;
  return {
    id: contribution.id,
    pluginId: contribution.pluginId,
    slot: contribution.slot,
    assetSchema: contribution.assetSchema,
    assets,
    mountPath: contribution.mountPath,
  };
}

export function listPluginAssetSlots(
  runtimePlugins?: PluginRuntimeContributionStates,
): PluginAssetSlotRegistryEntry[] {
  return buildPluginAssetSlotContributions(runtimePlugins).flatMap((contribution) => {
    const entry = toRegistryEntry(contribution);
    return entry ? [entry] : [];
  });
}

export function findPluginAssetSlot(
  slot: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): PluginAssetSlotRegistryEntry | undefined {
  return listPluginAssetSlots(runtimePlugins).find((entry) => entry.slot === slot);
}

export function hasPluginAssetSlot(
  slot: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return findPluginAssetSlot(slot, runtimePlugins) !== undefined;
}

export function buildPluginAssetUrl(
  entry: PluginAssetSlotRegistryEntry,
  assetPath: string,
): string | null {
  const normalized = assetPath.replace(/\\/g, "/").trim();
  if (!isSafeRelativeAssetPath(normalized)) return null;
  if (!entry.assets.includes(normalized)) return null;
  return `${entry.mountPath}${normalized}`;
}
