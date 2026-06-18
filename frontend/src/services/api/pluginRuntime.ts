import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getValidAccessToken, redirectToLogin } from "./tokenManager";
import type {
  PluginRuntimeContributionStatesResponse,
  ArchivedPluginPackagesResponse,
  PluginDataResponse,
  PluginExportResponse,
  PluginImportResponse,
  PluginPackagesResponse,
  PluginPackageImportResponse,
  PluginPackageReviewResponse,
  PluginPackageRestoreResponse,
  PluginPackageExportResponse,
  PluginSettingsResponse,
  PluginResourcesResponse,
  PluginRuntimeAuditResponse,
  PluginRuntimeListResponse,
  PluginRuntimePlugin,
  PluginUninstallDryRunResponse,
  PluginUninstallResponse,
} from "../../types";

const PLUGIN_RUNTIME_API = `${API_BASE}/api/extensions/plugins`;

async function authFetchBlob(url: string): Promise<Blob> {
  const headers: HeadersInit = {
    "Accept-Language": navigator.language || "en",
  };
  const token = await getValidAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers });
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(message || `Request failed: ${response.statusText}`);
  }
  return response.blob();
}

export const pluginRuntimeApi = {
  async list() {
    return authFetch<PluginRuntimeListResponse>(`${PLUGIN_RUNTIME_API}/`);
  },

  async listContributionStates() {
    return authFetch<PluginRuntimeContributionStatesResponse>(
      `${PLUGIN_RUNTIME_API}/contribution-states`,
      { skipAuth: true },
    );
  },

  async listPackages() {
    return authFetch<PluginPackagesResponse>(`${PLUGIN_RUNTIME_API}/packages`);
  },

  async scanPackages() {
    return authFetch<PluginPackagesResponse>(`${PLUGIN_RUNTIME_API}/packages/scan`, {
      method: "POST",
    });
  },

  async importPackage(sourcePath: string, dryRun = true) {
    return authFetch<PluginPackageImportResponse>(`${PLUGIN_RUNTIME_API}/packages/import`, {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath, dry_run: dryRun }),
    });
  },

  async listArchivedPackages() {
    return authFetch<ArchivedPluginPackagesResponse>(`${PLUGIN_RUNTIME_API}/packages/archived`);
  },

  async restoreArchivedPackage(archiveId: string) {
    return authFetch<PluginPackageRestoreResponse>(
      `${PLUGIN_RUNTIME_API}/packages/archived/${encodeURIComponent(archiveId)}/restore`,
      { method: "POST" },
    );
  },

  async getPackageReview(pluginId: string) {
    return authFetch<PluginPackageReviewResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/package-review`,
    );
  },

  async reviewPluginPackage(pluginId: string, reason?: string) {
    return authFetch<PluginPackageReviewResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/package-review`,
      {
        method: "POST",
        body: JSON.stringify({ reason: reason || null }),
      },
    );
  },

  async get(pluginId: string) {
    return authFetch<PluginRuntimePlugin>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}`,
    );
  },

  async enable(pluginId: string) {
    return authFetch<PluginRuntimePlugin>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/enable`,
      { method: "POST" },
    );
  },

  async disable(pluginId: string) {
    return authFetch<PluginRuntimePlugin>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/disable`,
      { method: "POST" },
    );
  },

  async listResources(pluginId: string) {
    return authFetch<PluginResourcesResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/resources`,
    );
  },

  async getUninstallDryRun(pluginId: string) {
    return authFetch<PluginUninstallDryRunResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/uninstall-dry-run`,
    );
  },

  async exportPlugin(pluginId: string) {
    return authFetch<PluginExportResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/export`,
    );
  },

  async exportPluginPackage(pluginId: string) {
    return authFetch<PluginPackageExportResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/package-export`,
    );
  },

  async exportPluginPackageArchive(pluginId: string) {
    return authFetchBlob(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/package-archive`,
    );
  },

  async importPlugin(payload: Record<string, unknown>, restoreState = false) {
    return authFetch<PluginImportResponse>(`${PLUGIN_RUNTIME_API}/import`, {
      method: "POST",
      body: JSON.stringify({ payload, restore_state: restoreState }),
    });
  },

  async uninstallPlugin(pluginId: string, snapshotId: string, confirmed = true) {
    return authFetch<PluginUninstallResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/uninstall`,
      {
        method: "POST",
        body: JSON.stringify({ snapshot_id: snapshotId, confirmed }),
      },
    );
  },

  async listAudit(pluginId: string) {
    return authFetch<PluginRuntimeAuditResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/audit`,
    );
  },

  async listSettings(pluginId: string) {
    return authFetch<PluginSettingsResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/settings`,
    );
  },

  async getPluginData(pluginId: string) {
    return authFetch<PluginDataResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/data`,
    );
  },

  async resetPluginData(pluginId: string) {
    return authFetch<PluginDataResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/data/reset`,
      { method: "POST" },
    );
  },

  async updateSetting(pluginId: string, key: string, value: unknown) {
    return authFetch<PluginSettingsResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/settings/${encodeURIComponent(key)}`,
      {
        method: "PUT",
        body: JSON.stringify({ value }),
      },
    );
  },

  async resetSetting(pluginId: string, key: string) {
    return authFetch<PluginSettingsResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/settings/${encodeURIComponent(key)}/reset`,
      { method: "POST" },
    );
  },

  async importLegacySettings(pluginId: string) {
    return authFetch<PluginSettingsResponse>(
      `${PLUGIN_RUNTIME_API}/${encodeURIComponent(pluginId)}/settings/import-legacy`,
      { method: "POST" },
    );
  },
};
