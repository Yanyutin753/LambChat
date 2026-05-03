import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Search, Settings2, UserRound, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PersonaPreset, PersonaPresetSnapshot } from "../../types";

interface PersonaPresetSelectorProps {
  presets: PersonaPreset[];
  selectedPresetId?: string | null;
  isOpen: boolean;
  isLoading?: boolean;
  isMutating?: boolean;
  canManagePresets?: boolean;
  onOpenChange: (open: boolean) => void;
  onUsePreset: (preset: PersonaPreset) => Promise<PersonaPresetSnapshot | null>;
  onCopyPreset: (preset: PersonaPreset) => Promise<void>;
  onManagePresets?: () => void;
  onClearPreset: () => void;
}

export function PersonaPresetSelector({
  presets,
  selectedPresetId,
  isOpen,
  isLoading = false,
  isMutating = false,
  canManagePresets = false,
  onOpenChange,
  onUsePreset,
  onCopyPreset,
  onManagePresets,
  onClearPreset,
}: PersonaPresetSelectorProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const tags = useMemo(
    () => Array.from(new Set(presets.flatMap((preset) => preset.tags))).sort(),
    [presets],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return presets.filter((preset) => {
      const matchesQuery =
        !q ||
        preset.name.toLowerCase().includes(q) ||
        preset.description.toLowerCase().includes(q);
      const matchesTag = !activeTag || preset.tags.includes(activeTag);
      return matchesQuery && matchesTag;
    });
  }, [activeTag, presets, query]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[9998] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="flex max-h-[86vh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl sm:rounded-2xl"
        style={{ background: "var(--theme-bg-card)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100 dark:bg-stone-800">
              <UserRound size={18} style={{ color: "var(--theme-primary)" }} />
            </div>
            <div>
              <h2
                className="text-base font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("personaPresets.title", "角色广场")}
              </h2>
              <p
                className="text-xs"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("personaPresets.subtitle", "选择一个角色开始对话")}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="rounded-lg p-2 hover:bg-stone-100 dark:hover:bg-stone-800"
            onClick={() => onOpenChange(false)}
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 border-b px-5 py-3 border-stone-200/70 dark:border-stone-700/70">
          <div className="flex items-center gap-2">
            {canManagePresets && onManagePresets && (
              <button
                type="button"
                onClick={() => {
                  onOpenChange(false);
                  onManagePresets();
                }}
                className="rounded-lg px-3 py-2 text-xs font-medium"
                style={{
                  background: "var(--theme-primary)",
                  color: "var(--theme-bg)",
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Settings2 size={14} />
                  {t("personaPresets.manage", "管理角色")}
                </span>
              </button>
            )}
            {selectedPresetId && (
              <button
                type="button"
                onClick={onClearPreset}
                className="rounded-lg border px-3 py-2 text-xs"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                {t("personaPresets.clear", "清除当前角色")}
              </button>
            )}
          </div>
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("personaPresets.search", "搜索角色")}
              className="w-full rounded-lg border bg-transparent py-2 pl-9 pr-3 text-sm outline-none"
              style={{
                borderColor: "var(--theme-border)",
                color: "var(--theme-text)",
              }}
            />
          </div>
          {tags.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              <button
                type="button"
                onClick={() => setActiveTag(null)}
                className="shrink-0 rounded-full border px-3 py-1 text-xs"
                style={{
                  borderColor: activeTag
                    ? "var(--theme-border)"
                    : "var(--theme-primary)",
                  color: activeTag
                    ? "var(--theme-text-secondary)"
                    : "var(--theme-primary)",
                }}
              >
                {t("personaPresets.allTags", "全部")}
              </button>
              {tags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setActiveTag(tag)}
                  className="shrink-0 rounded-full border px-3 py-1 text-xs"
                  style={{
                    borderColor:
                      activeTag === tag
                        ? "var(--theme-primary)"
                        : "var(--theme-border)",
                    color:
                      activeTag === tag
                        ? "var(--theme-primary)"
                        : "var(--theme-text-secondary)",
                  }}
                >
                  {tag}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="py-10 text-center text-sm text-stone-500">
              {t("common.loading", "加载中...")}
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-10 text-center text-sm text-stone-500">
              {t("personaPresets.empty", "暂无角色预设")}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {filtered.map((preset) => {
                const selected = selectedPresetId === preset.id;
                return (
                  <div
                    key={preset.id}
                    className="rounded-lg border p-4"
                    style={{
                      borderColor: selected
                        ? "var(--theme-primary)"
                        : "var(--theme-border)",
                    }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3
                          className="truncate text-sm font-semibold"
                          style={{ color: "var(--theme-text)" }}
                        >
                          {preset.name}
                        </h3>
                        <p
                          className="mt-1 line-clamp-2 text-xs leading-5"
                          style={{ color: "var(--theme-text-secondary)" }}
                        >
                          {preset.description || preset.system_prompt}
                        </p>
                      </div>
                      <span className="shrink-0 rounded-full bg-stone-100 px-2 py-1 text-[11px] text-stone-500 dark:bg-stone-800">
                        {preset.scope === "global"
                          ? t("personaPresets.official", "官方")
                          : t("personaPresets.mine", "我的")}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {preset.tags.slice(0, 4).map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500 dark:bg-stone-800"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="mt-4 flex items-center gap-2">
                      <button
                        type="button"
                        disabled={isMutating}
                        onClick={async () => {
                          const snapshot = await onUsePreset(preset);
                          if (snapshot) onOpenChange(false);
                        }}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                        style={{
                          background: selected
                            ? "var(--theme-primary-light)"
                            : "var(--theme-primary)",
                          color: selected
                            ? "var(--theme-primary)"
                            : "var(--theme-bg)",
                        }}
                      >
                        {selected
                          ? t("personaPresets.using", "使用中")
                          : t("personaPresets.use", "使用")}
                      </button>
                      {preset.scope === "global" && (
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={() => onCopyPreset(preset)}
                          className="rounded-lg border px-3 py-1.5 text-xs disabled:opacity-50"
                          style={{
                            borderColor: "var(--theme-border)",
                            color: "var(--theme-text-secondary)",
                          }}
                        >
                          {t("personaPresets.copy", "复制")}
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
    </div>,
    document.body,
  );
}
