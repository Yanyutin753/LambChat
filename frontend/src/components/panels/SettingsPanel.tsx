import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import {
  Settings,
  RotateCcw,
  Save,
  Search,
  AlertCircle,
  Check,
  ChevronDown,
  Download,
  Upload,
  Info,
} from "lucide-react";
import { AboutDialog } from "../common/AboutDialog";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { PanelLoadingState } from "../common/PanelLoadingState";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { JsonSchemaEditor } from "./JsonSchemaEditor";
import { useAuth } from "../../hooks/useAuth";
import { roleApi, agentApi } from "../../services/api";
import { Permission, type AgentInfo } from "../../types";
import type {
  SettingItem,
  SettingCategory,
  SettingType,
  Role,
} from "../../types";

const CATEGORY_ORDER: SettingCategory[] = [
  "frontend",
  "agent",
  "llm",
  "session",
  "mongodb",
  "redis",
  "checkpoint",
  "long_term_storage",
  "memory",
  "memory_embedding",
  "memory_search",
  "memory_storage",
  "security",
  "email",
  "captcha",
  "s3",
  "file_upload",
  "sandbox",
  "skills",
  "tools",
  "tracing",
  "user",
  "oauth",
];

const TYPE_COLORS: Record<SettingType, string> = {
  string: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
  text: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
  number:
    "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  boolean:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  json: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
  select: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
};

export function SettingsPanel() {
  const { t } = useTranslation();
  const {
    settings,
    isLoading,
    error,
    savingKeys,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
  } = useSettingsContext();
  const { hasPermission } = useAuth();

  const CATEGORY_LABELS: Record<SettingCategory, string> = {
    frontend: t("categories.frontend"),
    agent: t("categories.agent"),
    llm: t("categories.llm"),
    session: t("categories.session"),
    skills: t("categories.skills"),
    mongodb: t("categories.mongodb"),
    redis: t("categories.redis"),
    checkpoint: t("categories.checkpoint"),
    long_term_storage: t("categories.long_term_storage"),
    memory: t("categories.memory"),
    memory_embedding: t("categories.memory_embedding"),
    memory_search: t("categories.memory_search"),
    memory_storage: t("categories.memory_storage"),
    security: t("categories.security"),
    email: t("categories.email"),
    captcha: t("categories.captcha"),
    sandbox: t("categories.sandbox"),
    s3: t("categories.s3"),
    file_upload: t("categories.file_upload"),
    tools: t("categories.tools"),
    tracing: t("categories.tracing"),
    user: t("categories.user"),
    oauth: t("categories.oauth"),
  };

  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] =
    useState<SettingCategory>("frontend");
  const [editValues, setEditValues] = useState<
    Record<string, string | number | boolean | object>
  >({});
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [roles, setRoles] = useState<Role[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [showAbout, setShowAbout] = useState(false);

  // Reset confirmation dialog state
  const [isResetConfirmOpen, setIsResetConfirmOpen] = useState(false);
  const [resetConfirmKey, setResetConfirmKey] = useState<string | null>(null);
  const [isResetAllConfirmOpen, setIsResetAllConfirmOpen] = useState(false);

  const canManage = hasPermission(Permission.SETTINGS_MANAGE);

  // Fetch roles for DEFAULT_USER_ROLE dropdown
  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const roleList = await roleApi.list();
        setRoles(roleList);
      } catch (err) {
        console.error("Failed to fetch roles:", err);
      }
    };
    fetchRoles();
  }, []);

  // Fetch agents for DEFAULT_AGENT dropdown
  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const data = await agentApi.list();
        setAgents(data.agents || []);
      } catch (err) {
        console.error("Failed to fetch agents:", err);
      }
    };
    fetchAgents();
  }, []);

  // Get settings for active category
  const categorySettings = settings?.settings[activeCategory] ?? [];

  const SUBCATEGORY_LABELS = useMemo<Record<string, string>>(
    () => ({
      display: t("subcategories.display"),
      contact: t("subcategories.contact"),
      general: t("subcategories.general"),
      retry: t("subcategories.retry"),
      cache: t("subcategories.cache"),
      title: t("subcategories.title"),
      events: t("subcategories.events"),
      daytona: t("subcategories.daytona"),
      e2b: t("subcategories.e2b"),
      mcp: t("subcategories.mcp"),
      deferred: t("subcategories.deferred"),
      connection: t("subcategories.connection"),
      langsmith: t("subcategories.langsmith"),
      jwt: t("subcategories.jwt"),
      service: t("subcategories.service"),
      turnstile: t("subcategories.turnstile"),
      bucket: t("subcategories.bucket"),
      limits: t("subcategories.limits"),
      storage: t("subcategories.storage"),
      pool: t("subcategories.pool"),
      postgres: t("subcategories.postgres"),
      registration: t("subcategories.registration"),
      google: t("subcategories.google"),
      github: t("subcategories.github"),
      apple: t("subcategories.apple"),
      api: t("subcategories.api"),
      index: t("subcategories.index"),
      rerank: t("subcategories.rerank"),
      llm: t("subcategories.llm"),
      policy: t("subcategories.policy"),
    }),
    [t],
  );

  // Check if a setting should be visible based on depends_on
  const isSettingVisible = useCallback(
    (setting: SettingItem): boolean => {
      if (!setting.depends_on) {
        return true;
      }

      const allSettings = settings
        ? Object.values(settings.settings).flat()
        : [];

      if (typeof setting.depends_on === "string") {
        const parentSetting = allSettings.find(
          (s) => s.key === setting.depends_on,
        );
        if (!parentSetting) {
          return true;
        }
        const parentValue = editValues[setting.depends_on as string];
        if (parentValue !== undefined) {
          return parentValue === true;
        }
        return parentSetting.value === true;
      } else {
        const { key, value: expectedValue } = setting.depends_on;
        const parentSetting = allSettings.find((s) => s.key === key);
        if (!parentSetting) {
          return true;
        }
        const parentValue = editValues[key];
        if (parentValue !== undefined) {
          return parentValue === expectedValue;
        }
        return parentSetting.value === expectedValue;
      }
    },
    [settings, editValues],
  );

  // Filter settings by search query and visibility
  const filteredSettings = categorySettings.filter((setting) => {
    const matchesSearch =
      setting.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
      setting.description.toLowerCase().includes(searchQuery.toLowerCase());
    const isVisible = isSettingVisible(setting);
    return matchesSearch && isVisible;
  });

  // Group filtered settings by subcategory
  const groupedSettings = useMemo(() => {
    const groups: {
      subcategory: string;
      label: string;
      settings: typeof filteredSettings;
    }[] = [];
    const map = new Map<string, typeof filteredSettings>();
    for (const s of filteredSettings) {
      const key = s.subcategory || "";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(s);
    }
    for (const [key, items] of map) {
      groups.push({
        subcategory: key,
        label: key ? SUBCATEGORY_LABELS[key] || key : "",
        settings: items,
      });
    }
    return groups;
  }, [filteredSettings, SUBCATEGORY_LABELS]);

  // Handle value change
  const handleValueChange = useCallback(
    (key: string, value: string, type: SettingType) => {
      let parsedValue: string | number | boolean | object;

      if (type === "boolean") {
        parsedValue = value === "true";
      } else if (type === "number") {
        parsedValue = Number(value);
      } else if (type === "json") {
        try {
          parsedValue = JSON.parse(value);
        } catch {
          parsedValue = value;
        }
      } else {
        parsedValue = value;
      }

      setEditValues((prev) => ({ ...prev, [key]: parsedValue }));
    },
    [],
  );

  // Check if value is modified
  const isModified = useCallback(
    (setting: SettingItem) => {
      const editValue = editValues[setting.key];
      if (editValue === undefined) return false;

      // Compare stringified values for complex types
      return JSON.stringify(editValue) !== JSON.stringify(setting.value);
    },
    [editValues],
  );

  // Handle save
  const handleSave = useCallback(
    async (setting: SettingItem) => {
      const editValue = editValues[setting.key];
      if (editValue === undefined) return;

      const success = await updateSetting(setting.key, editValue);
      if (success) {
        // Show saved indicator
        setSavedKeys((prev) => new Set(prev).add(setting.key));
        // Clear edit value
        setEditValues((prev) => {
          const next = { ...prev };
          delete next[setting.key];
          return next;
        });
        // Show success toast
        toast.success(t("settings.saved"));
        // Remove saved indicator after 2 seconds
        setTimeout(() => {
          setSavedKeys((prev) => {
            const next = new Set(prev);
            next.delete(setting.key);
            return next;
          });
        }, 2000);
      }
    },
    [editValues, updateSetting, t],
  );

  // Handle reset to default
  const handleReset = useCallback(async (key: string) => {
    setResetConfirmKey(key);
    setIsResetConfirmOpen(true);
  }, []);

  const confirmReset = useCallback(async () => {
    if (!resetConfirmKey) return;
    const success = await resetSetting(resetConfirmKey);
    if (success) {
      // Clear edit value
      setEditValues((prev) => {
        const next = { ...prev };
        delete next[resetConfirmKey];
        return next;
      });
      toast.success(t("settings.resetSuccess"));
    }
    setIsResetConfirmOpen(false);
    setResetConfirmKey(null);
  }, [resetConfirmKey, resetSetting, t]);

  const cancelReset = () => {
    setIsResetConfirmOpen(false);
    setResetConfirmKey(null);
  };

  // Handle reset all
  const handleResetAll = useCallback(async () => {
    setIsResetAllConfirmOpen(true);
  }, []);

  const confirmResetAll = useCallback(async () => {
    const success = await resetAllSettings();
    if (success) {
      setEditValues({});
      toast.success(t("settings.resetAllSuccess"));
    }
    setIsResetAllConfirmOpen(false);
  }, [resetAllSettings, t]);

  const cancelResetAll = () => {
    setIsResetAllConfirmOpen(false);
  };

  const handleExport = useCallback(() => {
    exportSettings();
    toast.success(t("settings.exportSuccess"));
  }, [exportSettings, t]);

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleImport = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      setIsImporting(true);
      try {
        const result = await importSettings(file);
        if (result.success) {
          toast.success(
            t("settings.importSuccess", { count: result.updatedCount }),
          );
          if (result.errors.length > 0) {
            toast.error(result.errors.join(", "));
          }
        } else {
          toast.error(result.errors.join(", "));
        }
      } finally {
        setIsImporting(false);
        // Reset file input
        if (event.target) {
          event.target.value = "";
        }
      }
    },
    [importSettings, t],
  );

  // Get display value for input
  const getDisplayValue = useCallback(
    (setting: SettingItem) => {
      const editValue = editValues[setting.key];
      if (editValue !== undefined) {
        if (setting.type === "json") {
          return typeof editValue === "string"
            ? editValue
            : JSON.stringify(editValue, null, 2);
        }
        return String(editValue);
      }
      if (setting.type === "json") {
        return typeof setting.value === "string"
          ? setting.value
          : JSON.stringify(setting.value, null, 2);
      }
      return String(setting.value);
    },
    [editValues],
  );

  // Clear saved indicator on unmount
  useEffect(() => {
    return () => {
      setSavedKeys(new Set());
    };
  }, []);

  return (
    <>
      <div className="glass-shell flex h-full flex-col sm:flex-row">
        {/* Hidden file input for import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleImport}
          className="hidden"
        />

        {/* Left Sidebar - Categories (hidden on mobile) */}
        <div className="hidden w-56 flex-shrink-0 flex-col border-r border-[var(--glass-border)] sm:flex">
          {/* Sidebar Header */}
          <div className="flex items-center gap-2.5 px-5 py-4">
            <div className="[&>svg]:size-[18px] flex size-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-stone-100 to-stone-50 text-stone-600 shadow-sm ring-1 ring-stone-200/60 dark:from-stone-800 dark:to-stone-900 dark:text-stone-300 dark:ring-stone-700/50">
              <Settings size={18} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-stone-900 dark:text-stone-100 font-serif">
                {t("settings.title")}
              </h2>
              <p className="text-[11px] text-stone-400 dark:text-stone-500">
                {t("settings.modelConfigDescription", "管理应用配置")}
              </p>
            </div>
          </div>

          {/* Category List */}
          <nav className="flex-1 overflow-y-auto px-3 py-2">
            {CATEGORY_ORDER.map((category) => {
              const count = settings?.settings[category]?.length ?? 0;
              const isActive = activeCategory === category;
              return (
                <button
                  key={category}
                  onClick={() => setActiveCategory(category)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-[13px] transition-all duration-150 ${
                    isActive
                      ? "bg-[var(--glass-bg)] font-semibold text-stone-900 dark:text-stone-100 shadow-sm"
                      : "font-medium text-stone-500 hover:bg-[var(--glass-bg-subtle)] dark:text-stone-400"
                  }`}
                >
                  <span className="flex items-center justify-between">
                    {CATEGORY_LABELS[category]}
                    <span className="ml-2 text-[11px] tabular-nums opacity-40">
                      {count}
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>

          {/* Bottom actions */}
          <div className="flex gap-1.5 border-t border-[var(--glass-border)] px-3 py-2.5">
            <button
              onClick={() => setShowAbout(true)}
              className="btn-secondary flex flex-1 items-center justify-center gap-1 py-1.5 text-xs"
            >
              <Info size={12} />
              {t("common.about", "About")}
            </button>
            {canManage && (
              <button
                onClick={handleResetAll}
                disabled={isLoading}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-900/20"
              >
                <RotateCcw size={12} />
                {t("common.resetAll")}
              </button>
            )}
          </div>
        </div>

        {/* Right Content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Header with Category Dropdown (mobile) and Search */}
          <div className="flex-shrink-0 border-b border-[var(--glass-border)] p-3 sm:p-4">
            {/* Mobile Category Selector */}
            <div className="mb-2 sm:hidden">
              <div className="relative">
                <select
                  value={activeCategory}
                  onChange={(e) =>
                    setActiveCategory(e.target.value as SettingCategory)
                  }
                  className="w-full appearance-none rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-subtle)] py-2 pl-3 pr-8 text-sm font-medium text-stone-900 focus:outline-none dark:text-stone-100"
                >
                  {CATEGORY_ORDER.map((category) => (
                    <option key={category} value={category}>
                      {CATEGORY_LABELS[category]} (
                      {settings?.settings[category]?.length ?? 0})
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={18}
                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
                />
              </div>
            </div>

            {/* Search and Export/Import */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
                />
                <input
                  type="text"
                  placeholder={t("settings.searchPlaceholder")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="panel-search h-10"
                />
              </div>
              {canManage && (
                <>
                  <button
                    onClick={handleExport}
                    disabled={!settings}
                    className="btn-secondary flex items-center gap-1.5 px-3 h-10"
                    title={t("settings.exportSettings")}
                  >
                    <Download size={16} />
                    <span className="hidden sm:inline text-sm">
                      {t("common.export")}
                    </span>
                  </button>
                  <button
                    onClick={handleImportClick}
                    disabled={!settings || isImporting}
                    className="btn-secondary flex items-center gap-1.5 px-3 h-10"
                    title={t("settings.importSettings")}
                  >
                    <span className="inline-flex h-4 w-4 items-center justify-center">
                      {isImporting ? (
                        <LoadingSpinner
                          size="sm"
                          color="text-[var(--theme-primary)]"
                        />
                      ) : (
                        <Upload size={16} />
                      )}
                    </span>
                    <span className="hidden sm:inline text-sm">
                      {t("common.import")}
                    </span>
                  </button>
                </>
              )}
            </div>

            {/* Mobile Reset All Button */}
            {canManage && (
              <button
                onClick={handleResetAll}
                disabled={isLoading}
                className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-[var(--glass-bg-subtle)] px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 sm:hidden dark:border-red-900/50 dark:text-red-400 dark:hover:bg-red-900/20"
              >
                <RotateCcw size={12} />
                {t("common.resetAll")}
              </button>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="mx-3 mt-3 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-4 sm:mt-4">
              <span>{error}</span>
              <button
                onClick={clearError}
                className="ml-2 opacity-60 hover:opacity-100"
              >
                <AlertCircle size={16} />
              </button>
            </div>
          )}

          {/* Settings List */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-6">
            {isLoading && !settings ? (
              <PanelLoadingState text={t("settings.loading")} />
            ) : filteredSettings.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-stone-400 dark:text-stone-500">
                <Search size={40} className="mb-2 opacity-30" />
                <p className="text-sm">
                  {searchQuery
                    ? t("settings.noMatch")
                    : t("settings.noSettings")}
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {groupedSettings.map((group) => (
                  <div key={group.subcategory} className="space-y-3">
                    {group.label && (
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500">
                        {group.label}
                      </h3>
                    )}
                    {group.settings.map((setting) => {
                      const isSaving = savingKeys.has(setting.key);
                      const modified = isModified(setting);
                      const justSaved = savedKeys.has(setting.key);
                      const isJson = setting.type === "json";
                      const isSelect =
                        setting.key === "DEFAULT_AGENT" ||
                        setting.key === "DEFAULT_USER_ROLE" ||
                        setting.type === "boolean" ||
                        (setting.type === "select" && setting.options);

                      return (
                        <div
                          key={setting.key}
                          className="glass-card rounded-xl p-4"
                        >
                          {/* Key and Type */}
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <code className="rounded-md bg-[var(--glass-bg-subtle)] px-2 py-0.5 text-xs font-medium text-stone-900 break-all dark:text-stone-100">
                                  {setting.key}
                                </code>
                                <span
                                  className={`tag text-[11px] ${
                                    TYPE_COLORS[setting.type]
                                  }`}
                                >
                                  {setting.type}
                                </span>
                              </div>
                              <p className="mt-1 text-xs text-stone-500 sm:text-sm dark:text-stone-400">
                                {t(setting.description)}
                              </p>
                            </div>
                          </div>

                          {/* Edit Input */}
                          <div className="mt-3">
                            {isSelect && (
                              <div className="relative">
                                <select
                                  value={getDisplayValue(setting)}
                                  onChange={(e) =>
                                    handleValueChange(
                                      setting.key,
                                      e.target.value,
                                      setting.type === "select"
                                        ? "string"
                                        : setting.type,
                                    )
                                  }
                                  disabled={!canManage}
                                  className="w-full appearance-none rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] py-2 pl-3 pr-9 text-sm text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
                                >
                                  {setting.key === "DEFAULT_AGENT" ? (
                                    agents.map((agent) => (
                                      <option key={agent.id} value={agent.id}>
                                        {t(agent.name || agent.id)}
                                      </option>
                                    ))
                                  ) : setting.key === "DEFAULT_USER_ROLE" ? (
                                    roles.map((role) => (
                                      <option key={role.id} value={role.name}>
                                        {role.name}
                                      </option>
                                    ))
                                  ) : setting.type === "boolean" ? (
                                    <>
                                      <option value="true">true</option>
                                      <option value="false">false</option>
                                    </>
                                  ) : (
                                    setting.options?.map((opt) => (
                                      <option key={opt} value={opt}>
                                        {opt}
                                      </option>
                                    ))
                                  )}
                                </select>
                                <ChevronDown
                                  size={16}
                                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
                                />
                              </div>
                            )}
                            {setting.type === "text" && (
                              <textarea
                                value={getDisplayValue(setting)}
                                onChange={(e) =>
                                  handleValueChange(
                                    setting.key,
                                    e.target.value,
                                    setting.type,
                                  )
                                }
                                disabled={!canManage}
                                rows={8}
                                className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 py-2 text-sm text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
                              />
                            )}
                            {isJson && setting.json_schema && (
                              <JsonSchemaEditor
                                value={
                                  typeof getDisplayValue(setting) === "string"
                                    ? JSON.parse(
                                        getDisplayValue(setting) || "[]",
                                      )
                                    : getDisplayValue(setting)
                                }
                                schema={setting.json_schema}
                                disabled={!canManage}
                                onChange={(val) =>
                                  handleValueChange(
                                    setting.key,
                                    JSON.stringify(val),
                                    setting.type,
                                  )
                                }
                              />
                            )}
                            {isJson && !setting.json_schema && (
                              <textarea
                                value={getDisplayValue(setting)}
                                onChange={(e) =>
                                  handleValueChange(
                                    setting.key,
                                    e.target.value,
                                    setting.type,
                                  )
                                }
                                disabled={!canManage}
                                rows={20}
                                className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 py-2 font-mono text-xs text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm dark:text-stone-100"
                              />
                            )}
                            {!isSelect &&
                              setting.type !== "text" &&
                              !isJson && (
                                <input
                                  type={
                                    setting.type === "number"
                                      ? "number"
                                      : "text"
                                  }
                                  value={getDisplayValue(setting)}
                                  onChange={(e) =>
                                    handleValueChange(
                                      setting.key,
                                      e.target.value,
                                      setting.type,
                                    )
                                  }
                                  disabled={!canManage}
                                  className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 py-2 text-sm text-stone-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
                                />
                              )}
                          </div>

                          {/* Actions and Info */}
                          <div className="mt-3 flex flex-wrap-nowrap items-center justify-between gap-2">
                            {canManage && (
                              <div className="flex shrink-0 items-center gap-1.5">
                                <button
                                  onClick={() => handleSave(setting)}
                                  disabled={!modified || isSaving}
                                  className="btn-primary flex items-center gap-1 px-3 py-1.5 text-xs sm:text-sm disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {justSaved ? (
                                    <>
                                      <Check size={14} />
                                      {t("common.saved")}
                                    </>
                                  ) : (
                                    <>
                                      <Save size={14} />
                                      {t("common.save")}
                                    </>
                                  )}
                                </button>
                                <button
                                  onClick={() => handleReset(setting.key)}
                                  disabled={isSaving}
                                  className="btn-secondary flex items-center gap-1 px-3 py-1.5 text-xs sm:text-sm disabled:opacity-50"
                                >
                                  <RotateCcw size={14} />
                                  {t("common.reset")}
                                </button>
                              </div>
                            )}

                            {/* Default Value and Updated Info */}
                            <div className="hidden text-xs text-stone-400 sm:block dark:text-stone-500 max-w-full truncate">
                              {t("common.default")}:{" "}
                              {typeof setting.default_value === "object"
                                ? JSON.stringify(setting.default_value)
                                : String(setting.default_value)}
                              {setting.updated_at && (
                                <span className="ml-2 inline-flex">
                                  {new Date(
                                    setting.updated_at,
                                  ).toLocaleString()}
                                  {setting.updated_by &&
                                    ` · ${setting.updated_by}`}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Read-only notice */}
                          {!canManage && (
                            <div className="mt-2 rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-1.5 text-xs text-stone-400 dark:text-stone-500">
                              {t("settings.readOnlyNotice")}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      <AboutDialog isOpen={showAbout} onClose={() => setShowAbout(false)} />

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isResetConfirmOpen}
        title={t("settings.resetConfirm", { key: resetConfirmKey || "" })}
        message={t("settings.resetConfirmMessage", {
          key: resetConfirmKey || "",
        })}
        confirmText={t("common.reset")}
        cancelText={t("common.cancel")}
        onConfirm={confirmReset}
        onCancel={cancelReset}
        variant="warning"
      />

      {/* Reset All Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isResetAllConfirmOpen}
        title={t("settings.resetAllConfirm")}
        message={t("settings.resetAllConfirmMessage")}
        confirmText={t("common.resetAll")}
        cancelText={t("common.cancel")}
        onConfirm={confirmResetAll}
        onCancel={cancelResetAll}
        variant="danger"
      />
    </>
  );
}
