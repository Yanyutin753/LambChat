import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { personaPresetApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { usePersonaPresets } from "../../hooks/usePersonaPresets";
import { Permission } from "../../types";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetSnapshot,
} from "../../types";

const SESSION_CONFIG_KEY = "lambchat_session_config";

export type ScopeFilter = "all" | "global" | "user";

function readPersonaPresetId(): string | null {
  try {
    const raw = localStorage.getItem(SESSION_CONFIG_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.personaPresetId || null;
  } catch {
    return null;
  }
}

export interface PersonaRouteState {
  personaPresetId?: string;
  personaSnapshot?: PersonaPresetSnapshot;
}

const BACKEND_ERROR_MAP: Record<string, string> = {
  persona_preset_not_found: "personaPresets.presetNotFound",
  persona_preset_no_edit_permission: "personaPresets.noEditPermission",
  persona_preset_no_delete_permission: "personaPresets.noDeletePermission",
  persona_preset_no_admin_permission: "personaPresets.noAdminPermission",
};

function translateBackendError(message: string, t: TFunction): string {
  const i18nKey = BACKEND_ERROR_MAP[message];
  return i18nKey ? t(i18nKey, i18nKey) : message;
}

const PAGE_SIZE = 12;

export function usePersonaPlaza() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.PERSONA_PRESET_READ);
  const canWrite = hasPermission(Permission.PERSONA_PRESET_WRITE);
  const canAdmin = hasPermission(Permission.PERSONA_PRESET_ADMIN);

  const {
    presets,
    isLoading,
    isMutating,
    error,
    usePreset: activatePreset,
    copyPreset,
    createPreset,
    updatePreset,
    deletePreset,
  } = usePersonaPresets({ enabled: canRead });

  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [showModal, setShowModal] = useState(false);
  const [editingPreset, setEditingPreset] = useState<PersonaPreset | null>(
    null,
  );
  const [editorScope, setEditorScope] = useState<"user" | "global">("user");
  const [deleteTarget, setDeleteTarget] = useState<PersonaPreset | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isScopeOpen, setIsScopeOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  const scopeBtnRef = useRef<HTMLButtonElement>(null);
  const tagBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setSelectedPresetId(readPersonaPresetId());
  }, []);

  const allTags = useMemo(
    () => Array.from(new Set(presets.flatMap((p) => p.tags))).sort(),
    [presets],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return presets.filter((preset) => {
      const matchesQuery =
        !q ||
        preset.name.toLowerCase().includes(q) ||
        preset.description.toLowerCase().includes(q) ||
        preset.system_prompt.toLowerCase().includes(q);
      const matchesTag = !activeTag || preset.tags.includes(activeTag);
      const matchesScope =
        scopeFilter === "all" || preset.scope === scopeFilter;
      return matchesQuery && matchesTag && matchesScope;
    });
  }, [presets, query, activeTag, scopeFilter]);

  useEffect(() => {
    setPage(1);
  }, [query, activeTag, scopeFilter]);

  const paged = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  const globalCount = useMemo(
    () => presets.filter((p) => p.scope === "global").length,
    [presets],
  );
  const userCount = useMemo(
    () => presets.filter((p) => p.scope === "user").length,
    [presets],
  );

  const handleUse = useCallback(
    async (preset: PersonaPreset) => {
      const snapshot = await activatePreset(preset.id);
      if (snapshot) {
        setSelectedPresetId(preset.id);
        try {
          const raw = localStorage.getItem(SESSION_CONFIG_KEY);
          const existing = raw ? JSON.parse(raw) : {};
          localStorage.setItem(
            SESSION_CONFIG_KEY,
            JSON.stringify({
              ...existing,
              personaPresetId: preset.id,
              personaSnapshot: snapshot,
            }),
          );
        } catch {
          // Ignore local session cache write failures.
        }
        navigate(`/chat?persona=${preset.id}`, {
          state: {
            personaPresetId: preset.id,
            personaSnapshot: snapshot,
          } satisfies PersonaRouteState,
        });
        toast.success(
          t("personaPresets.useSuccess", "已切换到角色「{{name}}」", {
            name: preset.name,
          }),
        );
      } else if (error) {
        toast.error(translateBackendError(error, t));
      }
    },
    [activatePreset, navigate, t, error],
  );

  const handleClear = useCallback(() => {
    setSelectedPresetId(null);
    try {
      const raw = localStorage.getItem(SESSION_CONFIG_KEY);
      const existing = raw ? JSON.parse(raw) : {};
      localStorage.setItem(
        SESSION_CONFIG_KEY,
        JSON.stringify({
          ...existing,
          personaPresetId: null,
          personaSnapshot: null,
        }),
      );
    } catch {
      // Ignore local session cache write failures.
    }
    toast.success(t("personaPresets.clearSuccess", "已清除当前角色"));
  }, [t]);

  const handleCopy = useCallback(
    async (preset: PersonaPreset) => {
      const ok = await copyPreset(preset.id);
      if (ok) {
        toast.success(
          t("personaPresets.copySuccess", "已复制角色「{{name}}」", {
            name: preset.name,
          }),
        );
      } else if (error) {
        toast.error(translateBackendError(error, t));
      }
    },
    [copyPreset, t, error],
  );

  const openModal = (
    preset: PersonaPreset | null,
    scope: "user" | "global" = preset?.scope ?? "user",
  ) => {
    setEditingPreset(preset);
    setEditorScope(scope);
    setShowModal(true);
  };

  const closeModal = useCallback(() => {
    setShowModal(false);
    setEditingPreset(null);
    setEditorScope("user");
  }, []);

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const ok = await deletePreset(deleteTarget.id);
    setIsDeleting(false);
    if (ok) {
      toast.success(
        t("personaPresets.deleteSuccess", "角色「{{name}}」已删除", {
          name: deleteTarget.name,
        }),
      );
      if (selectedPresetId === deleteTarget.id) handleClear();
    } else if (error) {
      toast.error(translateBackendError(error, t));
    }
    setDeleteTarget(null);
  }, [deleteTarget, deletePreset, selectedPresetId, handleClear, t, error]);

  const toggleTag = (tag: string) =>
    setActiveTag((prev) => (prev === tag ? null : tag));
  const handleScopeSelect = useCallback((key: ScopeFilter) => {
    setScopeFilter(key);
  }, []);
  const clearFilters = () => {
    setActiveTag(null);
    setQuery("");
  };

  const scopeTabs = [
    {
      key: "all" as ScopeFilter,
      label: t("personaPresets.all", "全部"),
      icon: "Users" as const,
      count: presets.length,
    },
    {
      key: "global" as ScopeFilter,
      label: t("personaPresets.official", "官方"),
      icon: "Sparkles" as const,
      count: globalCount,
    },
    {
      key: "user" as ScopeFilter,
      label: t("personaPresets.mine", "我的"),
      icon: "User" as const,
      count: userCount,
    },
  ];

  const hasActiveFilters = !!activeTag || query.length > 0;

  // --- Export ---
  const handleExport = useCallback(async () => {
    const PAGE_LIMIT = 200;
    let allData: typeof presets = [];
    let skip = 0;
    try {
      while (true) {
        const res = await personaPresetApi.list({ skip, limit: PAGE_LIMIT });
        allData = allData.concat(res.presets);
        skip += res.presets.length;
        if (skip >= res.total || res.presets.length < PAGE_LIMIT) break;
      }
    } catch {
      toast.error(t("personaPresets.exportFailed", "导出失败"));
      return;
    }

    const exportData = allData.map((p) => ({
      name: p.name,
      description: p.description,
      avatar: p.avatar ?? null,
      tags: p.tags,
      system_prompt: p.system_prompt,
      skill_names: p.skill_names,
      scope: p.scope,
      visibility: p.visibility,
      status: p.status,
    }));
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lambchat-personas-${new Date()
      .toISOString()
      .slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(
      t("personaPresets.exportSuccess", "已导出 {{count}} 个角色", {
        count: exportData.length,
      }),
    );
  }, [t]);

  // --- Import ---
  const importInputRef = useRef<HTMLInputElement>(null);
  const [isImporting, setIsImporting] = useState(false);

  const handleImport = useCallback(() => {
    importInputRef.current?.click();
  }, []);

  const handleImportFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      // Reset so re-selecting same file fires onChange
      e.target.value = "";

      let items: PersonaPresetCreate[];
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed)) throw new Error("not_array");
        items = parsed.map((item: Record<string, unknown>) => ({
          name: String(item.name ?? ""),
          description: item.description ? String(item.description) : undefined,
          avatar: item.avatar !== undefined ? String(item.avatar) : undefined,
          tags: Array.isArray(item.tags) ? item.tags.map(String) : undefined,
          system_prompt: String(item.system_prompt ?? ""),
          skill_names: Array.isArray(item.skill_names)
            ? item.skill_names.map(String)
            : undefined,
          scope: item.scope === "global" ? "global" : "user",
          visibility: item.visibility === "private" ? "private" : "public",
          status:
            item.status === "draft"
              ? "draft"
              : item.status === "archived"
                ? "archived"
                : "published",
        }));
        const invalid = items.filter((it) => !it.name || !it.system_prompt);
        if (invalid.length > 0) throw new Error("invalid_items");
      } catch {
        toast.error(
          t("personaPresets.importInvalidFile", "导入失败：文件格式不正确"),
        );
        return;
      }

      setIsImporting(true);
      let imported = 0;
      let failed = 0;
      for (const data of items) {
        const result = await createPreset(data);
        if (result) imported++;
        else failed++;
      }
      setIsImporting(false);

      if (imported > 0) {
        toast.success(
          t("personaPresets.importSuccess", "成功导入 {{count}} 个角色", {
            count: imported,
          }),
        );
      }
      if (failed > 0) {
        toast.error(
          t("personaPresets.importPartialFail", "{{count}} 个角色导入失败", {
            count: failed,
          }),
        );
      }
    },
    [createPreset, t],
  );

  return {
    isLoading,
    isMutating,
    presets,
    canRead,
    canWrite,
    canAdmin,
    query,
    setQuery,
    activeTag,
    scopeFilter,
    selectedPresetId,
    filtered,
    paged,
    total: filtered.length,
    page,
    pageSize: PAGE_SIZE,
    setPage,
    allTags,
    scopeTabs,
    hasActiveFilters,
    clearFilters,
    toggleTag,
    handleScopeSelect,
    handleUse,
    handleClear,
    handleCopy,
    handleDelete,
    deleteTarget,
    setDeleteTarget,
    isDeleting,
    isScopeOpen,
    setIsScopeOpen,
    isFilterOpen,
    setIsFilterOpen,
    scopeBtnRef,
    tagBtnRef,
    showModal,
    closeModal,
    openModal,
    editingPreset,
    editorScope,
    createPreset,
    updatePreset,
    handleExport,
    handleImport,
    handleImportFile,
    importInputRef,
    isImporting,
  };
}
