import type {
  ExtensionManifest,
  ExtensionRegistryListOptions,
  ExtensionType,
  PluginManifest,
  PluginNavItem,
  PluginPanel,
  PluginRegistryListOptions,
  PluginRoute,
} from "./types";

export class RegistryDuplicateError extends Error {
  constructor(kind: "extension" | "plugin", id: string) {
    super(`${kind} already registered: ${id}`);
    this.name = "RegistryDuplicateError";
  }
}

function normalizeStringList(values: readonly string[] | undefined): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values ?? []) {
    const normalized = value.trim();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      result.push(normalized);
    }
  }
  return result;
}

function isEnabled(value: boolean | undefined): boolean {
  return value !== false;
}

function contributionListOptions(
  options: PluginRegistryListOptions,
): PluginRegistryListOptions {
  return { enabled: options.enabled ?? true };
}

export function normalizeExtensionManifest(
  manifest: ExtensionManifest,
): ExtensionManifest {
  return {
    ...manifest,
    id: manifest.id.trim(),
    tags: normalizeStringList(manifest.tags),
    capabilities: normalizeStringList(manifest.capabilities),
    permissions: normalizeStringList(manifest.permissions),
    installState: manifest.installState ?? "builtin",
    enabled: isEnabled(manifest.enabled),
  };
}

export function collectPluginPermissions(manifest: PluginManifest): string[] {
  return normalizeStringList([
    ...(manifest.permissions ?? []),
    ...collectContributionPermissions(manifest.routes),
    ...collectContributionPermissions(manifest.panels),
    ...collectContributionPermissions(manifest.navItems),
  ]);
}

function collectContributionPermissions(
  contributions: Array<{ requiredPermissions?: string[] }> | undefined,
): string[] {
  return (contributions ?? []).flatMap(
    (contribution) => contribution.requiredPermissions ?? [],
  );
}

export class ExtensionRegistry {
  private readonly items = new Map<string, ExtensionManifest>();

  constructor(manifests: readonly ExtensionManifest[] = []) {
    for (const manifest of manifests) {
      this.register(manifest);
    }
  }

  register(manifest: ExtensionManifest): ExtensionManifest {
    const normalized = normalizeExtensionManifest(manifest);
    if (!normalized.id) {
      throw new Error("extension id cannot be blank");
    }
    if (this.items.has(normalized.id)) {
      throw new RegistryDuplicateError("extension", normalized.id);
    }
    this.items.set(normalized.id, normalized);
    return normalized;
  }

  get(id: string): ExtensionManifest | undefined {
    return this.items.get(id);
  }

  list(options: ExtensionRegistryListOptions = {}): ExtensionManifest[] {
    return Array.from(this.items.values()).filter((manifest) => {
      if (options.type && manifest.type !== options.type) {
        return false;
      }
      if (options.enabled !== undefined && isEnabled(manifest.enabled) !== options.enabled) {
        return false;
      }
      return true;
    });
  }

  permissions(options: { enabledOnly?: boolean } = {}): string[] {
    const enabledOnly = options.enabledOnly ?? true;
    return normalizeStringList(
      this.list()
        .filter((manifest) => !enabledOnly || isEnabled(manifest.enabled))
        .flatMap((manifest) => manifest.permissions ?? []),
    );
  }
}

export class PluginRegistry {
  private readonly items = new Map<string, PluginManifest>();

  constructor(manifests: readonly PluginManifest[] = []) {
    for (const manifest of manifests) {
      this.register(manifest);
    }
  }

  register(manifest: PluginManifest): PluginManifest {
    const id = manifest.id.trim();
    if (!id) {
      throw new Error("plugin id cannot be blank");
    }
    if (this.items.has(id)) {
      throw new RegistryDuplicateError("plugin", id);
    }
    const normalized = { ...manifest, id };
    this.items.set(id, normalized);
    return normalized;
  }

  get(id: string): PluginManifest | undefined {
    return this.items.get(id);
  }

  list(options: PluginRegistryListOptions = {}): PluginManifest[] {
    return Array.from(this.items.values()).filter((manifest) => {
      if (options.enabled !== undefined) {
        return isEnabled(manifest.enabledByDefault) === options.enabled;
      }
      return true;
    });
  }

  routes(options: PluginRegistryListOptions = {}): PluginRoute[] {
    return this.list(contributionListOptions(options)).flatMap((manifest) =>
      (manifest.routes ?? []).filter((route) => isEnabled(route.enabled)),
    );
  }

  panels(options: PluginRegistryListOptions = {}): PluginPanel[] {
    return this.list(contributionListOptions(options)).flatMap((manifest) =>
      (manifest.panels ?? []).filter((panel) => isEnabled(panel.enabled)),
    );
  }

  navItems(options: PluginRegistryListOptions = {}): PluginNavItem[] {
    return this.list(contributionListOptions(options))
      .flatMap((manifest) =>
        (manifest.navItems ?? []).filter((item) => isEnabled(item.enabled)),
      )
      .sort((left, right) => (left.order ?? 100) - (right.order ?? 100));
  }

  settingsSections(options: PluginRegistryListOptions = {}): string[] {
    return normalizeStringList(
      this.list(contributionListOptions(options)).flatMap(
        (manifest) => manifest.settingsSections ?? [],
      ),
    );
  }

  toolRenderers(options: PluginRegistryListOptions = {}): string[] {
    return normalizeStringList(
      this.list(contributionListOptions(options)).flatMap(
        (manifest) => manifest.toolRenderers ?? [],
      ),
    );
  }

  i18nNamespaces(options: PluginRegistryListOptions = {}): string[] {
    return normalizeStringList(
      this.list(contributionListOptions(options)).flatMap(
        (manifest) => manifest.i18nNamespaces ?? [],
      ),
    );
  }

  permissions(options: { enabledOnly?: boolean } = {}): string[] {
    const enabledOnly = options.enabledOnly ?? true;
    return normalizeStringList(
      this.list({ enabled: enabledOnly ? true : undefined }).flatMap((manifest) =>
        collectPluginPermissions(manifest),
      ),
    );
  }

  asExtensionRegistry(options: { publisher?: string } = {}): ExtensionRegistry {
    const publisher = options.publisher ?? "core";
    return new ExtensionRegistry(
      this.list().map((manifest) => ({
        id: manifest.id,
        type: "plugin" as ExtensionType,
        name: manifest.name,
        version: manifest.version,
        publisher,
        capabilities: ["plugin"],
        permissions: collectPluginPermissions(manifest),
        installState: manifest.core ? "builtin" : "installed",
        enabled: isEnabled(manifest.enabledByDefault),
        compatibility: { apiVersion: manifest.apiVersion },
      })),
    );
  }
}
