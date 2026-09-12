import { useState, useCallback, useEffect, useMemo } from "react";
import i18n from "i18next";
import { pluginApi } from "../services/api/plugin";
import type { PluginResponse } from "../types";

type ActiveFilter = "all" | "active" | "inactive";

export function usePlugins() {
  const [plugins, setPlugins] = useState<PluginResponse[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all");

  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const fetchPlugins = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const tagsParam =
        selectedTags.length > 0 ? selectedTags.join(",") : undefined;
      const data = await pluginApi.list({
        tags: tagsParam,
        search: debouncedSearch || undefined,
      });
      setPlugins(data.plugins ?? []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("plugins.fetchFailed", "获取插件市场失败"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [selectedTags, debouncedSearch]);

  const fetchTags = useCallback(async () => {
    try {
      const data = await pluginApi.getTags();
      setTags(data.tags ?? []);
    } catch (err) {
      console.error(i18n.t("plugins.fetchTagsFailed", "获取标签失败:"), err);
    }
  }, []);

  useEffect(() => {
    void fetchPlugins();
  }, [fetchPlugins]);

  useEffect(() => {
    void fetchTags();
  }, [fetchTags]);

  const installPlugin = useCallback(async (name: string): Promise<boolean> => {
    try {
      await pluginApi.install(name);
      setPlugins((prev) =>
        prev.map((p) =>
          p.name === name ? { ...p, installed: true, installed_version: p.version } : p,
        ),
      );
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("plugins.installFailed", "安装插件失败"),
      );
      return false;
    }
  }, []);

  const updatePlugin = useCallback(async (name: string): Promise<boolean> => {
    try {
      await pluginApi.update(name);
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("plugins.updateFailed", "更新插件失败"),
      );
      return false;
    }
  }, []);

  const uninstallPlugin = useCallback(async (name: string): Promise<boolean> => {
    try {
      await pluginApi.uninstall(name);
      setPlugins((prev) =>
        prev.map((p) =>
          p.name === name
            ? { ...p, installed: false, installed_version: null }
            : p,
        ),
      );
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("plugins.uninstallFailed", "卸载插件失败"),
      );
      return false;
    }
  }, []);

  const activatePlugin = useCallback(
    async (name: string, isActive: boolean): Promise<boolean> => {
      try {
        await pluginApi.activate(name, isActive);
        setPlugins((prev) =>
          prev.map((p) =>
            p.name === name ? { ...p, status: isActive ? "active" : "deactivated" } : p,
          ),
        );
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("plugins.activateFailed", "操作失败"),
        );
        return false;
      }
    },
    [],
  );

  const deletePlugin = useCallback(async (name: string): Promise<boolean> => {
    try {
      await pluginApi.deletePlugin(name);
      setPlugins((prev) => prev.filter((p) => p.name !== name));
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("plugins.deleteFailed", "删除插件失败"),
      );
      return false;
    }
  }, []);

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }, []);

  const clearFilters = useCallback(() => {
    setSelectedTags([]);
    setSearchQuery("");
    setActiveFilter("all");
  }, []);

  const filteredPlugins = useMemo(() => {
    return plugins.filter((plugin) => {
      if (activeFilter === "active" && plugin.status !== "active") return false;
      if (activeFilter === "inactive" && plugin.status === "active") return false;
      return true;
    });
  }, [plugins, activeFilter]);

  return {
    plugins: filteredPlugins,
    tags,
    isLoading,
    error,
    selectedTags,
    searchQuery,
    setSearchQuery,
    activeFilter,
    setActiveFilter,
    toggleTag,
    clearFilters,
    fetchPlugins,
    installPlugin,
    updatePlugin,
    uninstallPlugin,
    activatePlugin,
    deletePlugin,
    clearError: () => setError(null),
  };
}
