import { useCallback, useEffect, useState } from "react";
import i18n from "i18next";
import { pluginRuntimeApi } from "../services/api/pluginRuntime";
import { dispatchPluginRuntimeUpdated } from "../utils/pluginRuntimeEvents";
import type {
  ArchivedPluginPackagesResponse,
  PluginResourcesResponse,
  PluginPackageImportResponse,
  PluginPackageReviewResponse,
  PluginPackageRestoreResponse,
  PluginDataResponse,
  PluginRuntimeAuditResponse,
  PluginRuntimeListResponse,
  PluginSettingsResponse,
  PluginUninstallDryRunResponse,
  PluginUninstallResponse,
} from "../types";

interface UsePluginRuntimeOptions {
  enabled?: boolean;
}

export function usePluginRuntime(options: UsePluginRuntimeOptions = {}) {
  const enabled = options.enabled ?? true;
  const [data, setData] = useState<PluginRuntimeListResponse | null>(null);
  const [resourcesByPlugin, setResourcesByPlugin] = useState<
    Record<string, PluginResourcesResponse>
  >({});
  const [dryRunsByPlugin, setDryRunsByPlugin] = useState<
    Record<string, PluginUninstallDryRunResponse>
  >({});
  const [auditByPlugin, setAuditByPlugin] = useState<
    Record<string, PluginRuntimeAuditResponse>
  >({});
  const [settingsByPlugin, setSettingsByPlugin] = useState<
    Record<string, PluginSettingsResponse>
  >({});
  const [dataByPlugin, setDataByPlugin] = useState<Record<string, PluginDataResponse>>({});
  const [packageReviewByPlugin, setPackageReviewByPlugin] = useState<
    Record<string, PluginPackageReviewResponse>
  >({});
  const [packageImportResult, setPackageImportResult] = useState<PluginPackageImportResponse | null>(null);
  const [archivedPackages, setArchivedPackages] = useState<ArchivedPluginPackagesResponse | null>(null);
  const [packageRestoreResult, setPackageRestoreResult] = useState<PluginPackageRestoreResponse | null>(null);
  const [lastUninstallResult, setLastUninstallResult] = useState<PluginUninstallResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailLoadingPlugin, setDetailLoadingPlugin] = useState<string | null>(
    null,
  );
  const [stateChangingPlugin, setStateChangingPlugin] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const fetchPlugins = useCallback(async () => {
    if (!enabled) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      setData(await pluginRuntimeApi.list());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.fetchFailed", "Failed to load plugins"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [enabled]);

  const fetchPluginDetails = useCallback(async (
    pluginId: string,
    options: { includeAudit?: boolean } = {},
  ) => {
    if (!enabled) return;
    setDetailLoadingPlugin(pluginId);
    setError(null);
    try {
      const [resources, dryRun, pluginData] = await Promise.all([
        pluginRuntimeApi.listResources(pluginId),
        pluginRuntimeApi.getUninstallDryRun(pluginId),
        pluginRuntimeApi.getPluginData(pluginId),
      ]);
      const pluginSettings = await pluginRuntimeApi.listSettings(pluginId);
      setResourcesByPlugin((prev) => ({ ...prev, [pluginId]: resources }));
      setDryRunsByPlugin((prev) => ({ ...prev, [pluginId]: dryRun }));
      setDataByPlugin((prev) => ({ ...prev, [pluginId]: pluginData }));
      setSettingsByPlugin((prev) => ({ ...prev, [pluginId]: pluginSettings }));
      try {
        const packageReview = await pluginRuntimeApi.getPackageReview(pluginId);
        setPackageReviewByPlugin((prev) => ({ ...prev, [pluginId]: packageReview }));
      } catch {
        setPackageReviewByPlugin((prev) => {
          const next = { ...prev };
          delete next[pluginId];
          return next;
        });
      }
      if (options.includeAudit) {
        const audit = await pluginRuntimeApi.listAudit(pluginId);
        setAuditByPlugin((prev) => ({ ...prev, [pluginId]: audit }));
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t(
              "pluginRuntime.fetchDetailsFailed",
              "Failed to load plugin details",
            ),
      );
    } finally {
      setDetailLoadingPlugin(null);
    }
  }, [enabled]);

  const updatePluginSetting = useCallback(async (
    pluginId: string,
    key: string,
    value: unknown,
  ) => {
    if (!enabled) return false;
    setDetailLoadingPlugin(pluginId);
    setError(null);
    try {
      const pluginSettings = await pluginRuntimeApi.updateSetting(pluginId, key, value);
      setSettingsByPlugin((prev) => ({ ...prev, [pluginId]: pluginSettings }));
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t(
              "pluginRuntime.settings.updateFailed",
              "Failed to update plugin setting",
            ),
      );
      return false;
    } finally {
      setDetailLoadingPlugin(null);
    }
  }, [enabled]);

  const exportPlugin = useCallback(async (pluginId: string) => {
    if (!enabled) return false;
    setDetailLoadingPlugin(pluginId);
    setError(null);
    try {
      const blob = await pluginRuntimeApi.exportPluginPackageArchive(pluginId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${pluginId}-plugin-package.zip`;
      link.click();
      URL.revokeObjectURL(url);
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.exportFailed", "Failed to export plugin"),
      );
      return false;
    } finally {
      setDetailLoadingPlugin(null);
    }
  }, [enabled]);

  const importPlugin = useCallback(async (rawJson: string, restoreState = false) => {
    if (!enabled) return false;
    setIsLoading(true);
    setError(null);
    try {
      const payload = JSON.parse(rawJson) as Record<string, unknown>;
      await pluginRuntimeApi.importPlugin(payload, restoreState);
      await fetchPlugins();
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.importFailed", "Failed to import plugin"),
      );
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [enabled, fetchPlugins]);

  const importPackage = useCallback(async (sourcePath: string, dryRun = true) => {
    if (!enabled) return false;
    setIsLoading(true);
    setError(null);
    try {
      const result = await pluginRuntimeApi.importPackage(sourcePath, dryRun);
      setPackageImportResult(result);
      await fetchPlugins();
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.importFailed", "Failed to import plugin"),
      );
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [enabled, fetchPlugins]);

  const fetchArchivedPackages = useCallback(async () => {
    if (!enabled) return;
    try {
      setArchivedPackages(await pluginRuntimeApi.listArchivedPackages());
    } catch {
      setArchivedPackages(null);
    }
  }, [enabled]);

  const restoreArchivedPackage = useCallback(async (archiveId: string) => {
    if (!enabled) return false;
    setIsLoading(true);
    setError(null);
    try {
      const result = await pluginRuntimeApi.restoreArchivedPackage(archiveId);
      setPackageRestoreResult(result);
      await fetchPlugins();
      await fetchArchivedPackages();
      dispatchPluginRuntimeUpdated();
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.restoreFailed", "Failed to restore plugin package"),
      );
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [enabled, fetchArchivedPackages, fetchPlugins]);

  const reviewPluginPackage = useCallback(async (pluginId: string, reason?: string) => {
    if (!enabled) return false;
    setStateChangingPlugin(pluginId);
    setError(null);
    try {
      const result = await pluginRuntimeApi.reviewPluginPackage(pluginId, reason);
      setPackageReviewByPlugin((prev) => ({ ...prev, [pluginId]: result }));
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.reviewFailed", "Failed to review plugin package"),
      );
      return false;
    } finally {
      setStateChangingPlugin(null);
    }
  }, [enabled]);

  const resetPluginData = useCallback(async (pluginId: string) => {
    if (!enabled) return false;
    setDetailLoadingPlugin(pluginId);
    setError(null);
    try {
      const pluginData = await pluginRuntimeApi.resetPluginData(pluginId);
      setDataByPlugin((prev) => ({ ...prev, [pluginId]: pluginData }));
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.dataResetFailed", "Failed to reset plugin data"),
      );
      return false;
    } finally {
      setDetailLoadingPlugin(null);
    }
  }, [enabled]);

  const uninstallPlugin = useCallback(async (pluginId: string) => {
    if (!enabled) return false;
    setStateChangingPlugin(pluginId);
    setError(null);
    try {
      const dryRun =
        dryRunsByPlugin[pluginId] ?? await pluginRuntimeApi.getUninstallDryRun(pluginId);
      const result = await pluginRuntimeApi.uninstallPlugin(pluginId, dryRun.snapshot_id, true);
      setLastUninstallResult(result);
      await fetchPlugins();
      await fetchArchivedPackages();
      dispatchPluginRuntimeUpdated();
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("pluginRuntime.uninstallFailed", "Failed to uninstall plugin"),
      );
      return false;
    } finally {
      setStateChangingPlugin(null);
    }
  }, [dryRunsByPlugin, enabled, fetchArchivedPackages, fetchPlugins]);

  const setPluginEnabled = useCallback(async (pluginId: string, nextEnabled: boolean) => {
    if (!enabled) return;
    setStateChangingPlugin(pluginId);
    setError(null);
    try {
      const updatedPlugin = nextEnabled
        ? await pluginRuntimeApi.enable(pluginId)
        : await pluginRuntimeApi.disable(pluginId);
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          plugins: prev.plugins.map((plugin) =>
            plugin.plugin_id === pluginId ? updatedPlugin : plugin,
          ),
        };
      });
      dispatchPluginRuntimeUpdated();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t(
              "pluginRuntime.updateStateFailed",
              "Failed to update plugin state",
            ),
      );
    } finally {
      setStateChangingPlugin(null);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      setResourcesByPlugin({});
      setDryRunsByPlugin({});
      setAuditByPlugin({});
      setSettingsByPlugin({});
      setDataByPlugin({});
      setPackageReviewByPlugin({});
      setPackageImportResult(null);
      setArchivedPackages(null);
      setPackageRestoreResult(null);
      setLastUninstallResult(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    fetchPlugins();
    fetchArchivedPackages();
  }, [enabled, fetchArchivedPackages, fetchPlugins]);

  return {
    data,
    plugins: data?.plugins ?? [],
    resourcesByPlugin,
    dryRunsByPlugin,
    auditByPlugin,
    settingsByPlugin,
    dataByPlugin,
    packageReviewByPlugin,
    packageImportResult,
    archivedPackages,
    packageRestoreResult,
    lastUninstallResult,
    isLoading,
    detailLoadingPlugin,
    stateChangingPlugin,
    error,
    fetchPlugins,
    fetchPluginDetails,
    setPluginEnabled,
    updatePluginSetting,
    exportPlugin,
    importPlugin,
    importPackage,
    fetchArchivedPackages,
    restoreArchivedPackage,
    reviewPluginPackage,
    resetPluginData,
    uninstallPlugin,
    clearError: () => setError(null),
  };
}
