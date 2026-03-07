import { useState, useCallback, useEffect, useRef } from "react";
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
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useSettingsContext } from "../../contexts/SettingsContext";
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
  "database",
  "long_term_storage",
  "security",
  "s3",
  "sandbox",
  "skills",
  "tools",
  "tracing",
  "user",
];

const TYPE_COLORS: Record<SettingType, string> = {
  string: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  text: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
  number:
    "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  boolean:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  json: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
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
    database: t("categories.database"),
    long_term_storage: t("categories.long_term_storage"),
    security: t("categories.security"),
    sandbox: t("categories.sandbox"),
    s3: t("categories.s3"),
    tools: t("categories.tools"),
    tracing: t("categories.tracing"),
    user: t("categories.user"),
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
      <div className="flex h-full flex-col sm:flex-row">
        {/* Hidden file input for import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleImport}
          className="hidden"
        />
        {/* Left Sidebar - Categories (hidden on mobile) */}
        <div className="hidden w-48 flex-shrink-0 flex-col border-r border-gray-200 bg-gray-50 sm:flex dark:border-stone-700 dark:bg-stone-800">
          {/* Sidebar Header */}
          <div className="flex items-center gap-2 border-b border-gray-200 p-3 dark:border-stone-700">
            <Settings size={20} className="text-gray-600 dark:text-stone-400" />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-stone-100">
              {t("settings.title")}
            </h2>
          </div>

          {/* Category List */}
          <nav className="flex-1 overflow-y-auto p-2">
            {CATEGORY_ORDER.map((category) => {
              const count = settings?.settings[category]?.length ?? 0;
              return (
                <button
                  key={category}
                  onClick={() => setActiveCategory(category)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                    activeCategory === category
                      ? "bg-blue-100 text-blue-700 dark:bg-amber-900/40 dark:text-amber-300"
                      : "text-gray-600 hover:bg-gray-100 dark:text-stone-400 dark:hover:bg-stone-700"
                  }`}
                >
                  <span>{CATEGORY_LABELS[category]}</span>
                  <span className="ml-1.5 text-xs opacity-60">({count})</span>
                </button>
              );
            })}
          </nav>

          {/* About Button */}
          <div className="border-t border-gray-200 p-2 dark:border-stone-700">
            <button
              onClick={() => setShowAbout(true)}
              className="flex w-full items-center justify-center gap-1 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
            >
              <Info size={12} />
              {t("common.about", "About")}
            </button>
          </div>

          {/* Reset All Button */}
          {canManage && (
            <div className="border-t border-gray-200 p-2 dark:border-stone-700">
              <button
                onClick={handleResetAll}
                disabled={isLoading}
                className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:bg-stone-900 dark:text-red-400 dark:hover:bg-red-900/20"
              >
                <RotateCcw size={12} />
                {t("common.resetAll")}
              </button>
            </div>
          )}
        </div>

        {/* Right Content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Header with Category Dropdown (mobile) and Search */}
          <div className="flex-shrink-0 border-b border-gray-200 bg-white p-3 dark:border-stone-700 dark:bg-stone-900">
            {/* Mobile Category Selector */}
            <div className="mb-2 sm:hidden">
              <div className="relative">
                <select
                  value={activeCategory}
                  onChange={(e) =>
                    setActiveCategory(e.target.value as SettingCategory)
                  }
                  className="w-full appearance-none rounded-lg border border-gray-200 bg-gray-50 py-2 pl-3 pr-8 text-sm font-medium text-gray-900 focus:border-blue-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
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
                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-stone-500"
                />
              </div>
            </div>

            {/* Search and Export/Import */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-stone-500"
                />
                <input
                  type="text"
                  placeholder={t("settings.searchPlaceholder")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-gray-50 py-2 pl-9 pr-3 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-amber-500"
                />
              </div>
              {canManage && (
                <>
                  <button
                    onClick={handleExport}
                    disabled={!settings}
                    className="flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
                    title="Export settings"
                  >
                    <Download size={18} />
                    <span className="hidden sm:inline">
                      {t("common.export")}
                    </span>
                  </button>
                  <button
                    onClick={handleImportClick}
                    disabled={!settings || isImporting}
                    className="flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
                    title="Import settings"
                  >
                    <Upload size={18} />
                    <span className="hidden sm:inline">
                      {isImporting ? t("common.importing") : t("common.import")}
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
                className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 sm:hidden dark:border-red-900/50 dark:bg-stone-900 dark:text-red-400 dark:hover:bg-red-900/20"
              >
                <RotateCcw size={12} />
                {t("common.resetAll")}
              </button>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="mx-4 mt-4 flex items-center justify-between rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
              <span>{error}</span>
              <button
                onClick={clearError}
                className="hover:text-red-900 dark:hover:text-red-300"
              >
                <AlertCircle size={18} />
              </button>
            </div>
          )}

          {/* Settings List */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-4">
            {isLoading && !settings ? (
              <div className="flex h-full items-center justify-center text-gray-500 dark:text-stone-400">
                {t("settings.loading")}
              </div>
            ) : filteredSettings.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-gray-500 dark:text-stone-400">
                <Search
                  size={48}
                  className="mb-2 text-gray-300 dark:text-stone-600"
                />
                <p>
                  {searchQuery
                    ? t("settings.noMatch")
                    : t("settings.noSettings")}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredSettings.map((setting) => {
                  const isSaving = savingKeys.has(setting.key);
                  const modified = isModified(setting);
                  const justSaved = savedKeys.has(setting.key);
                  const isJson = setting.type === "json";

                  return (
                    <div
                      key={setting.key}
                      className="rounded-lg border border-gray-200 bg-white p-3 sm:p-4 dark:border-stone-700 dark:bg-stone-900"
                    >
                      {/* Key and Type */}
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="rounded bg-gray-100 px-2 py-0.5 text-xs sm:text-sm font-medium text-gray-900 break-all dark:bg-stone-800 dark:text-stone-100">
                              {setting.key}
                            </code>
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                TYPE_COLORS[setting.type]
                              }`}
                            >
                              {setting.type}
                            </span>
                          </div>
                          <p className="mt-1 text-xs sm:text-sm text-gray-600 dark:text-stone-400">
                            {setting.description}
                          </p>
                        </div>
                      </div>

                      {/* Edit Input */}
                      <div className="mt-3">
                        {setting.key === "DEFAULT_AGENT" ? (
                          <select
                            value={getDisplayValue(setting)}
                            onChange={(e) =>
                              handleValueChange(
                                setting.key,
                                e.target.value,
                                setting.type,
                              )
                            }
                            disabled={!canManage}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          >
                            {agents.map((agent) => (
                              <option key={agent.id} value={agent.id}>
                                {agent.name || agent.id}
                              </option>
                            ))}
                          </select>
                        ) : setting.key === "DEFAULT_USER_ROLE" ? (
                          <select
                            value={getDisplayValue(setting)}
                            onChange={(e) =>
                              handleValueChange(
                                setting.key,
                                e.target.value,
                                setting.type,
                              )
                            }
                            disabled={!canManage}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          >
                            {roles.map((role) => (
                              <option key={role.id} value={role.name}>
                                {role.name}
                              </option>
                            ))}
                          </select>
                        ) : setting.type === "boolean" ? (
                          <select
                            value={getDisplayValue(setting)}
                            onChange={(e) =>
                              handleValueChange(
                                setting.key,
                                e.target.value,
                                setting.type,
                              )
                            }
                            disabled={!canManage}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          >
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        ) : setting.type === "text" ? (
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
                            rows={4}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          />
                        ) : isJson ? (
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
                            rows={4}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 font-mono text-xs sm:text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          />
                        ) : (
                          <input
                            type={setting.type === "number" ? "number" : "text"}
                            value={getDisplayValue(setting)}
                            onChange={(e) =>
                              handleValueChange(
                                setting.key,
                                e.target.value,
                                setting.type,
                              )
                            }
                            disabled={!canManage}
                            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500"
                          />
                        )}
                      </div>

                      {/* Actions and Info */}
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                        <div className="flex items-center gap-2">
                          {canManage && (
                            <>
                              <button
                                onClick={() => handleSave(setting)}
                                disabled={!modified || isSaving}
                                className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs sm:text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-amber-600 dark:hover:bg-amber-700"
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
                                className="flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs sm:text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
                              >
                                <RotateCcw size={14} />
                                {t("common.reset")}
                              </button>
                            </>
                          )}
                        </div>

                        {/* Default Value and Updated Info - hidden on mobile */}
                        <div className="hidden text-xs text-gray-400 sm:block dark:text-stone-500">
                          <span className="mr-2">
                            {t("common.default")}:{" "}
                            {typeof setting.default_value === "object"
                              ? JSON.stringify(setting.default_value)
                              : String(setting.default_value)}
                          </span>
                          {setting.updated_at && (
                            <span>
                              {t("common.lastUpdated")}:{" "}
                              {new Date(setting.updated_at).toLocaleString()}
                              {setting.updated_by &&
                                ` ${t("common.by")} ${setting.updated_by}`}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Read-only notice */}
                      {!canManage && (
                        <div className="mt-2 rounded bg-gray-50 px-2 py-1 text-xs text-gray-500 dark:bg-stone-800 dark:text-stone-500">
                          {t("settings.readOnlyNotice")}
                        </div>
                      )}
                    </div>
                  );
                })}
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
