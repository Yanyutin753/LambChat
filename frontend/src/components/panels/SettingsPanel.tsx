import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import {
  Settings,
  RotateCcw,
  Save,
  Search,
  AlertCircle,
  Check,
  Download,
  Upload,
  Info,
} from "lucide-react";
import { AboutDialog } from "../common/AboutDialog";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { Button, Input, Select, Textarea } from "../common";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import { resolveAgentDisplayName } from "../agent/agentCatalog";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { JsonSchemaEditor } from "./JsonSchemaEditor";
import { SystemHealthSection } from "./SystemHealthSection";
import { useAuth } from "../../hooks/useAuth";
import { roleApi, agentApi, modelApi } from "../../services/api";
import type { ModelOption } from "../../services/api/model";
import { Permission, type AgentInfo } from "../../types";
import { formatDateTime } from "../../utils/datetime";
import type {
  SettingItem,
  SettingCategory,
  SettingType,
  Role,
} from "../../types";

import {
  MODEL_CONFIG_SETTING_KEYS,
  TYPE_COLORS,
} from "./SettingsPanel.constants";
import {
  buildCategoryLabels,
  buildSubcategoryLabels,
} from "./settingsPanelLabels";
import {
  buildVisibleCategories,
  groupFilteredSettings,
} from "./settingsPanelGrouping";
import { SettingsCategoryNav } from "./SettingsCategoryNav";
import { filterSettings, SETTINGS_NAV_GROUPS } from "./settingsNavigation";

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

  const CATEGORY_LABELS = useMemo<Record<SettingCategory, string>>(
    () => buildCategoryLabels((key) => t(key)),
    [t],
  );

  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] =
    useState<SettingCategory>("frontend");
  const [activeSubcategory, setActiveSubcategory] = useState<string | null>(
    null,
  );
  const contentRef = useRef<HTMLDivElement>(null);
  const isSearching = searchQuery.trim().length > 0;
  const [editValues, setEditValues] = useState<
    Record<string, string | number | boolean | object>
  >({});
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [roles, setRoles] = useState<Role[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [showAbout, setShowAbout] = useState(false);

  // Reset confirmation dialog state
  const [isResetConfirmOpen, setIsResetConfirmOpen] = useState(false);
  const [resetConfirmKey, setResetConfirmKey] = useState<string | null>(null);
  const [isResetAllConfirmOpen, setIsResetAllConfirmOpen] = useState(false);
  const [isResettingAll, setIsResettingAll] = useState(false);

  const canManage = hasPermission(Permission.SETTINGS_MANAGE);

  // Fetch roles for DEFAULT_USER_ROLE dropdown
  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const roleList = await roleApi.list({ limit: 200 });
        setRoles(roleList.roles);
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

  // Fetch model configs for settings that reference admin model configuration IDs
  useEffect(() => {
    const fetchModels = async () => {
      try {
        if (hasPermission(Permission.MODEL_ADMIN)) {
          const data = await modelApi.list(true);
          setAvailableModels(
            (data.models || [])
              .filter((model) => model.enabled && model.id)
              .map((model) => ({
                id: model.id || "",
                value: model.value,
                provider: model.provider,
                icon: model.icon,
                label: model.label,
                description: model.description,
                profile: model.profile,
              })),
          );
          return;
        }
        const data = await modelApi.listAvailable();
        setAvailableModels(data.models || []);
      } catch (err) {
        console.error("Failed to fetch models:", err);
      }
    };
    fetchModels();
  }, [hasPermission]);

  const SUBCATEGORY_LABELS = useMemo<Record<string, string>>(
    () => buildSubcategoryLabels((key) => t(key)),
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

  const filteredSettings = useMemo(
    () =>
      filterSettings(Object.values(settings?.settings ?? {}).flat(), {
        query: searchQuery,
        includeAdmin: canManage,
        category: activeCategory,
        subcategory: activeSubcategory,
        isVisible: isSettingVisible,
        translate: t,
        categoryLabels: CATEGORY_LABELS,
        subcategoryLabels: SUBCATEGORY_LABELS,
      }),
    [
      searchQuery,
      canManage,
      settings,
      activeCategory,
      activeSubcategory,
      isSettingVisible,
      t,
      CATEGORY_LABELS,
      SUBCATEGORY_LABELS,
    ],
  );

  const subcategories = useMemo(
    () =>
      groupFilteredSettings(
        (settings?.settings[activeCategory] ?? []).filter(
          (setting) =>
            (canManage || setting.frontend_visible !== false) &&
            isSettingVisible(setting),
        ),
        {
          isGlobalSearch: false,
          categoryLabels: CATEGORY_LABELS,
          subcategoryLabels: SUBCATEGORY_LABELS,
        },
      ),
    [
      settings,
      canManage,
      activeCategory,
      isSettingVisible,
      CATEGORY_LABELS,
      SUBCATEGORY_LABELS,
    ],
  );

  // Group filtered settings by category (when searching globally) or subcategory (when browsing a single category)
  const groupedSettings = useMemo(
    () =>
      groupFilteredSettings(filteredSettings, {
        isGlobalSearch: searchQuery.trim().length > 0,
        categoryLabels: CATEGORY_LABELS,
        subcategoryLabels: SUBCATEGORY_LABELS,
      }),
    [filteredSettings, CATEGORY_LABELS, SUBCATEGORY_LABELS, searchQuery],
  );

  // Categories that still expose visible settings; shared by the desktop
  // sidebar nav and the mobile chip strip so both stay in sync
  const visibleCategories = useMemo(
    () =>
      buildVisibleCategories(settings?.settings, isSettingVisible, canManage),
    [settings, isSettingVisible, canManage],
  );

  const selectCategory = useCallback((category: SettingCategory) => {
    setActiveCategory(category);
    setActiveSubcategory(null);
    setSearchQuery("");
  }, []);

  // Permissions/dependencies may remove the current category or subcategory.
  useEffect(() => {
    if (
      visibleCategories.length &&
      !visibleCategories.some(({ category }) => category === activeCategory)
    ) {
      selectCategory(visibleCategories[0].category);
    }
  }, [visibleCategories, activeCategory, selectCategory]);
  useEffect(() => {
    if (
      activeSubcategory !== null &&
      !subcategories.some((group) => group.subcategory === activeSubcategory)
    ) {
      setActiveSubcategory(null);
    }
  }, [subcategories, activeSubcategory]);
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [activeCategory, activeSubcategory, searchQuery]);

  const navigation = settings?.navigation ?? SETTINGS_NAV_GROUPS;
  const activeGroup = navigation.find((group) =>
    group.categories.includes(activeCategory),
  );

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
    if (isResettingAll) return;
    setIsResettingAll(true);
    try {
      const success = await resetAllSettings();
      if (success) {
        setEditValues({});
        toast.success(t("settings.resetAllSuccess"));
        setIsResetAllConfirmOpen(false);
      }
    } finally {
      setIsResettingAll(false);
    }
  }, [resetAllSettings, isResettingAll, t]);

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
        <div className="hidden w-60 flex-shrink-0 flex-col border-r border-[var(--glass-border)] sm:flex">
          {/* Sidebar Header */}
          <div className="flex items-center gap-2.5 px-5 py-4">
            <div className="flex size-9 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300">
              <Settings size={18} />
            </div>
            <div>
              <h2 className="text-14 font-semibold text-stone-900 dark:text-stone-100">
                {t("settings.title")}
              </h2>
              <p className="text-12 text-stone-400 dark:text-stone-500">
                {t("settings.navigation.subtitle")}
              </p>
            </div>
          </div>

          <SettingsCategoryNav
            categories={visibleCategories}
            navigation={navigation}
            activeCategory={activeCategory}
            searching={isSearching}
            labels={CATEGORY_LABELS}
            onSelect={selectCategory}
          />

          {/* Bottom actions */}
          <div className="flex gap-1.5 border-t border-[var(--glass-border)] px-3 py-2.5">
            <Button
              onClick={() => setShowAbout(true)}
              size="sm"
              leftIcon={<Info size={12} />}
              className="flex-1 py-1.5 text-12"
            >
              {t("common.about", "About")}
            </Button>
            {canManage && (
              <button
                onClick={handleResetAll}
                disabled={isLoading}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg py-1.5 text-12 font-medium text-red-500 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-900/20"
              >
                <RotateCcw size={12} />
                {t("common.resetAll")}
              </button>
            )}
          </div>
        </div>

        {/* Right Content */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Header with Category Dropdown (mobile) and Search */}
          <div className="flex-shrink-0 border-b border-[var(--glass-border)] p-3 sm:p-4">
            <SettingsCategoryNav
              mobile
              categories={visibleCategories}
              navigation={navigation}
              activeCategory={activeCategory}
              searching={isSearching}
              labels={CATEGORY_LABELS}
              onSelect={selectCategory}
            />

            {/* Search and Export/Import */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
                />
                <PanelSearchInput
                  type="text"
                  placeholder={t("settings.navigation.searchPlaceholder")}
                  aria-label={t("settings.navigation.searchPlaceholder")}
                  value={searchQuery}
                  onValueChange={setSearchQuery}
                  className="panel-search h-10"
                />
              </div>
              {canManage && (
                <>
                  <Button
                    onClick={handleExport}
                    disabled={!settings}
                    leftIcon={<Download size={16} />}
                    className="h-10 px-3"
                    title={t("settings.exportSettings")}
                    aria-label={t("settings.exportSettings")}
                  >
                    <span className="hidden sm:inline text-14">
                      {t("common.export")}
                    </span>
                  </Button>
                  <Button
                    onClick={handleImportClick}
                    disabled={!settings || isImporting}
                    loading={isImporting}
                    leftIcon={<Upload size={16} />}
                    className="h-10 px-3"
                    title={t("settings.importSettings")}
                    aria-label={t("settings.importSettings")}
                  >
                    <span className="hidden sm:inline text-14">
                      {t("common.import")}
                    </span>
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="mx-3 mt-3 flex items-center justify-between rounded-xl bg-red-50 p-3 text-14 text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-4 sm:mt-4">
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
          <div
            ref={contentRef}
            className="min-h-0 flex-1 overflow-y-auto py-2 sm:py-4 px-4"
          >
            <div className="mb-4 border-b border-[var(--glass-border)] pb-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="mb-1 text-12 text-stone-500 dark:text-stone-400">
                    {isSearching || !activeGroup
                      ? t("settings.navigation.allCategories")
                      : t(`settings.navigation.groups.${activeGroup.id}`)}
                  </p>
                  <h2 className="text-18 font-semibold text-stone-900 dark:text-stone-100">
                    {isSearching
                      ? t("settings.navigation.searchResults")
                      : CATEGORY_LABELS[activeCategory]}
                  </h2>
                  {!isSearching && activeGroup && (
                    <p className="mt-1 text-12 text-stone-500 dark:text-stone-400">
                      {t(`settings.navigation.descriptions.${activeGroup.id}`)}
                    </p>
                  )}
                </div>
                <span
                  role="status"
                  className="text-12 tabular-nums text-stone-500 dark:text-stone-400"
                >
                  {t("settings.navigation.resultCount", {
                    count: filteredSettings.length,
                  })}
                </span>
              </div>
              {isSearching ? (
                <Button
                  size="sm"
                  className="mt-2"
                  onClick={() => setSearchQuery("")}
                >
                  {t("settings.navigation.clearSearch")}
                </Button>
              ) : (
                subcategories.length > 1 && (
                  <label className="mt-3 flex flex-wrap items-center gap-2 text-12 text-stone-600 dark:text-stone-400">
                    <span>{t("settings.navigation.subcategory")}</span>
                    <select
                      value={activeSubcategory ?? "__all__"}
                      onChange={(event) =>
                        setActiveSubcategory(
                          event.target.value === "__all__"
                            ? null
                            : event.target.value,
                        )
                      }
                      className="h-10 min-w-0 max-w-full rounded-lg border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-3 text-14 text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] dark:text-stone-100"
                    >
                      <option value="__all__">
                        {t("settings.navigation.allSubcategories")}
                      </option>
                      {subcategories.map((group) => (
                        <option
                          key={group.subcategory}
                          value={group.subcategory}
                        >
                          {group.label || t("subcategories.general")} ·{" "}
                          {group.settings.length}
                        </option>
                      ))}
                    </select>
                  </label>
                )
              )}
              <p className="mt-2 text-12 text-stone-500 dark:text-stone-400">
                {canManage
                  ? t("settings.navigation.saveHint")
                  : t("settings.readOnlyNotice")}
              </p>
            </div>

            {/* System Health Monitor */}
            {!isSearching && activeGroup?.id === "infrastructure" && (
              <SystemHealthSection />
            )}

            {isLoading && !settings ? (
              <PanelLoadingState text={t("settings.loading")} />
            ) : filteredSettings.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-stone-400 dark:text-stone-500">
                <Search size={40} className="mb-2 opacity-30" />
                <p className="text-14">
                  {isSearching
                    ? t("settings.noMatch")
                    : t("settings.noSettings")}
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {groupedSettings.map((group) => (
                  <div key={group.subcategory} className="space-y-3">
                    {group.label && (
                      <h3 className="text-12 font-semibold font-serif uppercase tracking-wider text-stone-500 dark:text-stone-400">
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
                        MODEL_CONFIG_SETTING_KEYS.has(setting.key) ||
                        setting.type === "boolean" ||
                        (setting.type === "select" && setting.options);
                      const displayValue = getDisplayValue(setting);
                      const legacyModelOption =
                        MODEL_CONFIG_SETTING_KEYS.has(setting.key) &&
                        displayValue &&
                        !availableModels.some(
                          (model) => model.id === displayValue,
                        )
                          ? [
                              {
                                value: displayValue,
                                label: `${t(
                                  "settings.legacyModelValue",
                                  "Legacy value",
                                )}: ${displayValue}`,
                              },
                            ]
                          : [];

                      return (
                        <div
                          key={setting.key}
                          className="glass-card rounded-xl p-4"
                        >
                          {/* Key and Type */}
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                {isSearching && (
                                  <button
                                    onClick={() => {
                                      selectCategory(setting.category);
                                      setActiveSubcategory(
                                        setting.subcategory || "",
                                      );
                                    }}
                                    className="rounded-md bg-[var(--glass-bg-subtle)] px-2 py-1 text-12 font-medium text-[var(--theme-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
                                  >
                                    {CATEGORY_LABELS[setting.category]}
                                  </button>
                                )}
                                <code className="rounded-md bg-[var(--glass-bg-subtle)] px-2 py-0.5 text-12 font-medium text-stone-900 break-all dark:text-stone-100">
                                  {setting.key}
                                </code>
                                <span
                                  className={`tag text-11 ${
                                    TYPE_COLORS[setting.type]
                                  }`}
                                >
                                  {setting.type}
                                </span>
                              </div>
                              <p className="mt-1 text-12 text-stone-500 sm:text-14 dark:text-stone-400">
                                {t(setting.description)}
                              </p>
                            </div>
                          </div>

                          {/* Edit Input */}
                          <div className="mt-3">
                            {isSelect && (
                              <Select
                                value={displayValue}
                                onChange={(v) =>
                                  handleValueChange(
                                    setting.key,
                                    v,
                                    setting.type === "select"
                                      ? "string"
                                      : setting.type,
                                  )
                                }
                                disabled={!canManage}
                                options={
                                  setting.key === "DEFAULT_AGENT"
                                    ? agents.map((agent) => ({
                                        value: agent.id,
                                        label:
                                          resolveAgentDisplayName(
                                            agent,
                                            i18n.language,
                                            t,
                                          ) || agent.id,
                                      }))
                                    : setting.key === "DEFAULT_USER_ROLE"
                                      ? roles.map((role) => ({
                                          value: role.name,
                                          label: role.name,
                                        }))
                                      : MODEL_CONFIG_SETTING_KEYS.has(
                                            setting.key,
                                          )
                                        ? [
                                            {
                                              value: "",
                                              label:
                                                setting.key ===
                                                "DEFAULT_MODEL_ID"
                                                  ? t(
                                                      "settings.firstEnabledModel",
                                                      "First enabled model",
                                                    )
                                                  : setting.key ===
                                                      "LLM_FALLBACK_MODEL"
                                                    ? t(
                                                        "settings.noFallbackModel",
                                                        "No fallback",
                                                      )
                                                    : setting.key ===
                                                        "VIDEO_ANALYSIS_MODEL_ID"
                                                      ? t(
                                                          "settings.fallbackToImageAnalysisModel",
                                                          "Fallback to image analysis model",
                                                        )
                                                      : t(
                                                          "settings.defaultModel",
                                                          "Default model",
                                                        ),
                                            },
                                            ...legacyModelOption,
                                            ...availableModels.map((model) => ({
                                              value: model.id,
                                              label: `${model.label} (${model.value})`,
                                            })),
                                          ]
                                        : setting.type === "boolean"
                                          ? [
                                              {
                                                value: "true",
                                                label: t(
                                                  "settings.true",
                                                  "true",
                                                ),
                                              },
                                              {
                                                value: "false",
                                                label: t(
                                                  "settings.false",
                                                  "false",
                                                ),
                                              },
                                            ]
                                          : setting.options?.map((opt) => ({
                                              value: opt,
                                              label: opt,
                                            })) ?? []
                                }
                              />
                            )}
                            {setting.type === "text" && (
                              <Textarea
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
                                className="bg-[var(--theme-bg-card)] px-3 py-2 text-14 text-stone-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
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
                              <Textarea
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
                                className="max-h-[45vh] overflow-y-auto bg-[var(--theme-bg-card)] px-3 py-2 font-mono text-12 text-stone-900 disabled:cursor-not-allowed disabled:opacity-60 sm:max-h-none sm:text-14 dark:text-stone-100"
                              />
                            )}
                            {!isSelect &&
                              setting.type !== "text" &&
                              !isJson && (
                                <Input
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
                                  className="bg-[var(--theme-bg-card)] px-3 py-2 text-14 text-stone-900 disabled:cursor-not-allowed disabled:opacity-60 dark:text-stone-100"
                                />
                              )}
                          </div>

                          {/* Actions and Info */}
                          <div className="mt-3 flex flex-wrap-nowrap items-center justify-between gap-2">
                            {canManage && (
                              <div className="flex shrink-0 items-center gap-1.5">
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handleSave(setting)}
                                  disabled={!modified || isSaving}
                                  loading={isSaving}
                                  leftIcon={
                                    justSaved ? (
                                      <Check size={14} />
                                    ) : (
                                      <Save size={14} />
                                    )
                                  }
                                  className="px-3 py-1.5 text-12 sm:text-14 disabled:cursor-not-allowed"
                                >
                                  {justSaved
                                    ? t("common.saved")
                                    : t("common.save")}
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => handleReset(setting.key)}
                                  disabled={isSaving}
                                  leftIcon={<RotateCcw size={14} />}
                                  className="px-3 py-1.5 text-12 sm:text-14"
                                >
                                  {t("common.reset")}
                                </Button>
                              </div>
                            )}

                            {/* Default Value and Updated Info */}
                            <div className="hidden text-12 text-stone-400 sm:block dark:text-stone-500 max-w-full truncate">
                              {t("common.default")}:{" "}
                              {typeof setting.default_value === "object"
                                ? JSON.stringify(setting.default_value)
                                : String(setting.default_value)}
                              {setting.updated_at && (
                                <span className="ml-2 inline-flex">
                                  {formatDateTime(setting.updated_at)}
                                  {setting.updated_by &&
                                    ` · ${setting.updated_by}`}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Read-only notice */}
                          {!canManage && (
                            <div className="mt-2 rounded-lg bg-[var(--glass-bg-subtle)] px-3 py-1.5 text-12 text-stone-400 dark:text-stone-500">
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
            <div className="mt-5 flex flex-wrap gap-2 border-t border-[var(--glass-border)] pt-3 sm:hidden">
              <Button
                size="sm"
                onClick={() => setShowAbout(true)}
                leftIcon={<Info size={14} />}
              >
                {t("common.about")}
              </Button>
              {canManage && (
                <Button
                  size="sm"
                  onClick={handleResetAll}
                  disabled={isLoading}
                  leftIcon={<RotateCcw size={14} />}
                >
                  {t("common.resetAll")}
                </Button>
              )}
            </div>
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
        loading={isResettingAll}
        variant="danger"
      />
    </>
  );
}
