import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  UserRound,
  Plus,
  Copy,
  Pencil,
  Check,
  X,
  Users,
  User,
  Sparkles,
  Tag,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { useAuth } from "../../hooks/useAuth";
import { usePersonaPresets } from "../../hooks/usePersonaPresets";
import type { PersonaPreset } from "../../types";
import { Permission } from "../../types";

const SESSION_CONFIG_KEY = "lambchat_session_config";

function readPersonaPresetId(): string | null {
  try {
    const raw = localStorage.getItem(SESSION_CONFIG_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.personaPresetId || null;
  } catch {
    return null;
  }
}

const AVATAR_GRADIENTS = [
  "from-violet-500 to-purple-600",
  "from-blue-500 to-cyan-500",
  "from-rose-500 to-pink-500",
  "from-amber-500 to-orange-500",
  "from-emerald-500 to-teal-500",
  "from-indigo-500 to-blue-500",
  "from-fuchsia-500 to-pink-500",
  "from-sky-500 to-blue-600",
];

function getAvatarGradient(id: string) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = id.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

type ScopeFilter = "all" | "global" | "user";

export function PersonaPlazaPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(Permission.PERSONA_PRESET_READ);
  const canWrite = hasPermission(Permission.PERSONA_PRESET_WRITE);

  const {
    presets,
    isLoading,
    isMutating,
    usePreset,
    copyPreset,
    createPreset,
    updatePreset,
  } = usePersonaPresets({ enabled: canRead });

  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [editingPreset, setEditingPreset] = useState<PersonaPreset | null>(
    null,
  );
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    system_prompt: "",
    tags: "",
    skill_names: "",
  });
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    setSelectedPresetId(readPersonaPresetId());
  }, []);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 2500);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const tags = useMemo(
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
      const snapshot = await usePreset(preset.id);
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
        } catch {}
        setToast(t("personaPresets.useSuccess", "已选择角色"));
      }
    },
    [usePreset, t],
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
    } catch {}
    setToast(t("personaPresets.clearSuccess", "已清除角色"));
  }, [t]);

  const handleCopy = useCallback(
    async (preset: PersonaPreset) => {
      const result = await copyPreset(preset.id);
      if (result) {
        setToast(t("personaPresets.copySuccess", "已复制到我的角色"));
      }
    },
    [copyPreset, t],
  );

  const startEdit = (preset: PersonaPreset | null) => {
    setEditingPreset(preset);
    setShowEditor(true);
    setDraft({
      name: preset?.name || "",
      description: preset?.description || "",
      system_prompt: preset?.system_prompt || "",
      tags: preset?.tags.join(", ") || "",
      skill_names: preset?.skill_names.join(", ") || "",
    });
  };

  const handleSave = useCallback(async () => {
    if (!draft.name.trim() || !draft.system_prompt.trim()) return;
    const data = {
      name: draft.name.trim(),
      description: draft.description.trim() || undefined,
      system_prompt: draft.system_prompt.trim(),
      tags: draft.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      skill_names: draft.skill_names
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    if (editingPreset) {
      await updatePreset(editingPreset.id, data);
    } else {
      await createPreset(data);
    }
    setShowEditor(false);
    setEditingPreset(null);
    setToast(t("common.saveSuccess", "保存成功"));
  }, [draft, editingPreset, createPreset, updatePreset, t]);

  const scopeTabs: {
    key: ScopeFilter;
    label: string;
    icon: typeof Users;
    count: number;
  }[] = [
    {
      key: "all",
      label: t("personaPresets.all", "全部"),
      icon: Users,
      count: presets.length,
    },
    {
      key: "global",
      label: t("personaPresets.official", "官方"),
      icon: Sparkles,
      count: globalCount,
    },
    {
      key: "user",
      label: t("personaPresets.mine", "我的"),
      icon: User,
      count: userCount,
    },
  ];

  return (
    <div className="glass-shell flex h-full flex-col min-h-0 animate-fade-in">
      <PanelHeader
        title={t("personaPresets.title", "角色广场")}
        subtitle={t("personaPresets.subtitle", "选择一个角色开始对话")}
        icon={<UserRound />}
        searchValue={query}
        onSearchChange={setQuery}
        searchPlaceholder={t("personaPresets.search", "搜索角色名称、描述...")}
        actions={
          canWrite ? (
            <button
              type="button"
              onClick={() => startEdit(null)}
              className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium shadow-sm transition-all hover:shadow-md active:scale-[0.98]"
              style={{
                background: "var(--theme-primary)",
                color: "var(--theme-bg)",
              }}
            >
              <Plus size={16} />
              <span className="hidden sm:inline">
                {t("personaPresets.createMine", "新建角色")}
              </span>
            </button>
          ) : undefined
        }
      >
        {/* Tag filter row */}
        {tags.length > 0 && (
          <div className="mt-2 flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
            <Tag size={13} className="mr-1 shrink-0 text-stone-400" />
            <button
              type="button"
              onClick={() => setActiveTag(null)}
              className="shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors"
              style={{
                background: !activeTag
                  ? "var(--theme-primary)"
                  : "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                color: !activeTag
                  ? "var(--theme-bg)"
                  : "var(--theme-text-secondary)",
                border: `1px solid ${
                  !activeTag ? "var(--theme-primary)" : "var(--theme-border)"
                }`,
              }}
            >
              {t("personaPresets.allTags", "全部")}
            </button>
            {tags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                className="shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors"
                style={{
                  background:
                    activeTag === tag
                      ? "var(--theme-primary)"
                      : "var(--glass-bg-subtle, color-mix(in srgb, var(--theme-bg) 80%, white))",
                  color:
                    activeTag === tag
                      ? "var(--theme-bg)"
                      : "var(--theme-text-secondary)",
                  border: `1px solid ${
                    activeTag === tag
                      ? "var(--theme-primary)"
                      : "var(--theme-border)"
                  }`,
                }}
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </PanelHeader>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="p-3 sm:p-6 xl:p-8">
          {/* Scope tabs */}
          <div className="glass-card-subtle mb-4 flex items-center gap-1 rounded-xl p-1">
            {scopeTabs.map(({ key, label, icon: Icon, count }) => (
              <button
                key={key}
                type="button"
                onClick={() => setScopeFilter(key)}
                className="flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all"
                style={{
                  background:
                    scopeFilter === key ? "var(--glass-bg)" : "transparent",
                  color:
                    scopeFilter === key
                      ? "var(--theme-text)"
                      : "var(--theme-text-secondary)",
                  boxShadow:
                    scopeFilter === key ? "var(--glass-shadow)" : "none",
                }}
              >
                <Icon size={15} />
                <span className="hidden sm:inline">{label}</span>
                <span
                  className="text-xs"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {count}
                </span>
              </button>
            ))}
          </div>

          {/* Card grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 xl:gap-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="glass-card rounded-xl flex flex-col p-5 animate-pulse"
                >
                  <div className="flex items-start gap-3">
                    <div className="size-10 shrink-0 rounded-full bg-stone-200 dark:bg-stone-700" />
                    <div className="min-w-0 flex-1">
                      <div className="h-4 w-2/3 rounded bg-stone-200 dark:bg-stone-700" />
                      <div className="mt-2 h-3 w-full rounded bg-stone-200 dark:bg-stone-700" />
                      <div className="mt-1.5 h-3 w-4/5 rounded bg-stone-200 dark:bg-stone-700" />
                    </div>
                  </div>
                  <div className="mt-4 flex gap-1.5">
                    <div className="h-5 w-12 rounded-full bg-stone-200 dark:bg-stone-700" />
                    <div className="h-5 w-16 rounded-full bg-stone-200 dark:bg-stone-700" />
                  </div>
                  <div className="mt-4 flex gap-2">
                    <div className="h-8 w-16 rounded-lg bg-stone-200 dark:bg-stone-700" />
                    <div className="h-8 w-16 rounded-lg bg-stone-200 dark:bg-stone-700" />
                  </div>
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-stone-100 dark:bg-stone-800">
                <UserRound size={28} className="text-stone-400" />
              </div>
              <h3
                className="text-base font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {query || activeTag
                  ? t("personaPresets.noMatch", "没有匹配的角色")
                  : t("personaPresets.empty", "暂无角色预设")}
              </h3>
              <p
                className="mt-1 text-sm"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {query || activeTag
                  ? t("personaPresets.tryOtherFilters", "试试其他搜索条件")
                  : t("personaPresets.emptyHint", "管理员可以创建官方角色预设")}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 xl:gap-5">
              {filtered.map((preset) => {
                const selected = selectedPresetId === preset.id;
                const gradient = getAvatarGradient(preset.id);
                return (
                  <div
                    key={preset.id}
                    className="glass-card rounded-xl group flex flex-col p-5 transition-all animate-glass-enter"
                    style={{
                      borderColor: selected
                        ? "var(--theme-primary)"
                        : undefined,
                      outline: selected
                        ? "2px solid var(--theme-primary)"
                        : undefined,
                      outlineOffset: selected ? "-2px" : undefined,
                    }}
                  >
                    {/* Card header */}
                    <div className="flex items-start gap-3">
                      <div
                        className={`flex size-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${gradient} text-white shadow-sm`}
                      >
                        <span className="text-sm font-bold">
                          {preset.name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h3
                            className="truncate text-sm font-semibold"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {preset.name}
                          </h3>
                          {preset.usage_count > 0 && (
                            <span
                              className="shrink-0 text-[11px]"
                              style={{ color: "var(--theme-text-secondary)" }}
                            >
                              {preset.usage_count}次使用
                            </span>
                          )}
                        </div>
                        <p
                          className="mt-1 line-clamp-2 text-xs leading-5"
                          style={{ color: "var(--theme-text-secondary)" }}
                        >
                          {preset.description || preset.system_prompt}
                        </p>
                      </div>
                    </div>

                    {/* Scope badge + tags */}
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      <span
                        className={
                          preset.scope === "global"
                            ? "glass-tag glass-tag--accent text-[11px] px-2.5 py-0.5"
                            : "glass-tag text-[11px] px-2.5 py-0.5"
                        }
                      >
                        {preset.scope === "global"
                          ? t("personaPresets.official", "官方")
                          : t("personaPresets.mine", "我的")}
                      </span>
                      {preset.tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag}
                          className="glass-tag text-[11px] px-2 py-0.5"
                        >
                          {tag}
                        </span>
                      ))}
                      {preset.tags.length > 3 && (
                        <span className="glass-tag glass-tag--overflow text-[11px] px-2 py-0.5">
                          +{preset.tags.length - 3}
                        </span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="mt-4 flex items-center gap-2 glass-divider pt-3">
                      {selected ? (
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={handleClear}
                          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all disabled:opacity-50"
                          style={{
                            background: "var(--theme-primary-light, #dbeafe)",
                            color: "var(--theme-primary)",
                          }}
                        >
                          <Check size={14} />
                          {t("personaPresets.using", "使用中")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={() => handleUse(preset)}
                          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium shadow-sm transition-all hover:shadow-md active:scale-[0.98] disabled:opacity-50"
                          style={{
                            background: "var(--theme-primary)",
                            color: "var(--theme-bg)",
                          }}
                        >
                          <Sparkles size={14} />
                          {t("personaPresets.use", "使用")}
                        </button>
                      )}
                      {preset.scope === "global" && canWrite && (
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={() => handleCopy(preset)}
                          className="glass-tag flex items-center gap-1 px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                        >
                          <Copy size={13} />
                          {t("personaPresets.copy", "复制")}
                        </button>
                      )}
                      {preset.scope === "user" && canWrite && (
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={() => startEdit(preset)}
                          className="glass-tag flex items-center gap-1 px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                        >
                          <Pencil size={13} />
                          {t("personaPresets.edit", "编辑")}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Toast notification */}
      {toast && (
        <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-fade-in">
          <div
            className="rounded-xl px-4 py-2.5 text-sm font-medium shadow-lg"
            style={{
              background: "var(--theme-text)",
              color: "var(--theme-bg)",
            }}
          >
            {toast}
          </div>
        </div>
      )}

      {/* Create/Edit overlay */}
      {showEditor && canWrite && (
        <div
          className="absolute inset-0 z-20 flex flex-col animate-fade-in"
          style={{ background: "var(--theme-bg)" }}
        >
          <div
            className="flex items-center justify-between border-b px-5 py-4"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <h2
              className="text-base font-semibold"
              style={{ color: "var(--theme-text)" }}
            >
              {editingPreset
                ? t("personaPresets.editMine", "编辑我的角色")
                : t("personaPresets.createMine", "新建我的角色")}
            </h2>
            <button
              type="button"
              onClick={() => {
                setShowEditor(false);
                setEditingPreset(null);
              }}
              className="rounded-lg p-2 transition-colors hover:bg-stone-100 dark:hover:bg-stone-800"
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl space-y-5 p-5 sm:p-6 xl:p-8">
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("personaPresets.name", "名称")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  value={draft.name}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, name: e.target.value }))
                  }
                  className="glass-input h-10 w-full px-3 text-sm"
                  style={{ color: "var(--theme-text)" }}
                  placeholder={t(
                    "personaPresets.namePlaceholder",
                    "给角色起个名字",
                  )}
                />
              </div>
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("personaPresets.description", "简介")}
                </label>
                <input
                  value={draft.description}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      description: e.target.value,
                    }))
                  }
                  className="glass-input h-10 w-full px-3 text-sm"
                  style={{ color: "var(--theme-text)" }}
                  placeholder={t(
                    "personaPresets.descriptionPlaceholder",
                    "简短描述角色的能力和特点",
                  )}
                />
              </div>
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("personaPresets.systemPrompt", "系统提示词")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={draft.system_prompt}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      system_prompt: e.target.value,
                    }))
                  }
                  rows={10}
                  className="glass-input w-full resize-none px-4 py-3 text-sm leading-6"
                  style={{ color: "var(--theme-text)" }}
                  placeholder={t(
                    "personaPresets.systemPromptPlaceholder",
                    "定义角色的行为、语气和能力边界...",
                  )}
                />
              </div>
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("personaPresets.tagsInput", "标签")}
                </label>
                <input
                  value={draft.tags}
                  onChange={(e) =>
                    setDraft((prev) => ({ ...prev, tags: e.target.value }))
                  }
                  className="glass-input h-10 w-full px-3 text-sm"
                  style={{ color: "var(--theme-text)" }}
                  placeholder={t(
                    "personaPresets.tagsInputPlaceholder",
                    "用逗号分隔，如：写作, 翻译, 代码",
                  )}
                />
              </div>
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium"
                  style={{ color: "var(--theme-text)" }}
                >
                  {t("personaPresets.skillsInput", "Skills")}
                </label>
                <input
                  value={draft.skill_names}
                  onChange={(e) =>
                    setDraft((prev) => ({
                      ...prev,
                      skill_names: e.target.value,
                    }))
                  }
                  className="glass-input h-10 w-full px-3 text-sm"
                  style={{ color: "var(--theme-text)" }}
                  placeholder={t(
                    "personaPresets.skillsInputPlaceholder",
                    "用逗号分隔，如：web_search, code_interpreter",
                  )}
                />
              </div>
            </div>
          </div>

          <div
            className="flex justify-end gap-2 border-t px-5 py-4"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <button
              type="button"
              onClick={() => {
                setShowEditor(false);
                setEditingPreset(null);
              }}
              className="rounded-xl border px-4 py-2 text-sm font-medium transition-colors"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text-secondary)",
              }}
            >
              {t("common.cancel", "取消")}
            </button>
            <button
              type="button"
              disabled={
                isMutating || !draft.name.trim() || !draft.system_prompt.trim()
              }
              onClick={handleSave}
              className="rounded-xl px-4 py-2 text-sm font-medium shadow-sm transition-all hover:shadow-md active:scale-[0.98] disabled:opacity-50"
              style={{
                background: "var(--theme-primary)",
                color: "var(--theme-bg)",
              }}
            >
              {t("common.save", "保存")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default PersonaPlazaPanel;
