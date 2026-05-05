import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Search, Settings2, UserRound, X, Sparkles, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import type { PersonaPreset, PersonaPresetSnapshot } from "../../types";
import { isPersonaImageAvatar } from "./personaAvatar";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import { PersonaPreviewSidebar } from "./PersonaPreviewSidebar";
import { Pagination } from "../common/Pagination";

const PAGE_SIZE = 12;

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
  const [previewPreset, setPreviewPreset] = useState<PersonaPreset | null>(
    null,
  );
  const [page, setPage] = useState(1);

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

  useEffect(() => {
    setPage(1);
  }, [query, activeTag]);

  const paged = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  if (!isOpen) return null;

  const selector = createPortal(
    <div
      data-yields-sidebar
      className="fixed inset-0 z-[250] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="flex max-h-[86vh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl md:max-w-4xl lg:max-w-5xl sm:rounded-2xl"
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
          <div className="inline-grid grid-cols-2 gap-2">
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
            <div className="grid auto-grid-cols gap-4">
              {paged.map((preset, index) => {
                const selected = selectedPresetId === preset.id;
                const gradient = nameToGradient(preset.name);
                const primaryTag = preset.tags[0];
                return (
                  <div
                    key={preset.id}
                    className="pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none cursor-pointer"
                    style={{ animationDelay: `${index * 50}ms` }}
                    onClick={() => setPreviewPreset(preset)}
                  >
                    {/* Gradient Banner */}
                    <div
                      className="pps-card__banner relative h-10 shrink-0"
                      style={{
                        background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                      }}
                    >
                      {selected && (
                        <span className="pps-card__status-badge">
                          {t("personaPresets.using", "使用中")}
                        </span>
                      )}
                    </div>

                    {/* Card Body */}
                    <div className="flex flex-1 flex-col p-3.5 pt-4">
                      {/* Title row */}
                      <div className="flex items-start gap-2.5">
                        <div className="pps-card__avatar shrink-0">
                          {isPersonaImageAvatar(preset.avatar) ? (
                            <PersonaAvatarImage
                              avatar={preset.avatar}
                              alt=""
                              className="pps-card__avatar-img"
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display =
                                  "none";
                              }}
                            />
                          ) : (
                            <PersonaAvatarIcon
                              avatar={preset.avatar}
                              primaryTag={primaryTag}
                              size={16}
                              className="pps-card__avatar-icon"
                            />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3
                            className="truncate text-sm font-semibold leading-tight"
                            style={{ color: "var(--theme-text)" }}
                          >
                            {preset.name}
                          </h3>
                          <div
                            className="mt-1 flex items-center gap-1.5 text-[11px]"
                            style={{ color: "var(--theme-text-secondary)" }}
                          >
                            <span>
                              {preset.scope === "global"
                                ? t("personaPresets.official", "官方")
                                : t("personaPresets.mine", "我的")}
                            </span>
                            {preset.usage_count > 0 && (
                              <>
                                <span
                                  className="inline-block h-0.5 w-0.5 rounded-full"
                                  style={{ background: "var(--theme-border)" }}
                                />
                                <span>
                                  {preset.usage_count}
                                  {t("personaPresets.usageCount", "次使用")}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Description */}
                      <p
                        className="mt-2.5 text-[13px] leading-relaxed line-clamp-2 min-h-[3.25em]"
                        style={{ color: "var(--theme-text-secondary)" }}
                      >
                        {preset.description || preset.system_prompt}
                      </p>

                      {/* Tags */}
                      {preset.tags.length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {preset.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="scb__mini-tag"
                              style={{ cursor: "default" }}
                            >
                              {tag}
                            </span>
                          ))}
                          {preset.tags.length > 3 && (
                            <span
                              className="scb__mini-tag"
                              style={{ cursor: "default", opacity: 0.7 }}
                            >
                              +{preset.tags.length - 3}
                            </span>
                          )}
                        </div>
                      )}

                      <div className="flex-1" />

                      {/* Actions */}
                      <div
                        className="mt-3 flex items-center gap-1.5 border-t pt-3"
                        style={{ borderColor: "var(--theme-border)" }}
                      >
                        <button
                          type="button"
                          disabled={isMutating}
                          onClick={async (e) => {
                            e.stopPropagation();
                            const snapshot = await onUsePreset(preset);
                            if (snapshot) onOpenChange(false);
                          }}
                          className={`pps-card__action ${
                            selected
                              ? "pps-card__action--active"
                              : "pps-card__action--primary"
                          }`}
                        >
                          <Sparkles size={13} />
                          {selected
                            ? t("personaPresets.using", "使用中")
                            : t("personaPresets.use", "使用")}
                        </button>
                        {preset.scope === "global" && (
                          <button
                            type="button"
                            disabled={isMutating}
                            onClick={(e) => {
                              e.stopPropagation();
                              onCopyPreset(preset);
                            }}
                            className="pps-card__action pps-card__action--ghost"
                          >
                            <Copy size={13} />
                            {t("personaPresets.copy", "复制")}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {filtered.length > PAGE_SIZE && (
          <div
            className="border-t px-5 py-3"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={filtered.length}
              onChange={setPage}
            />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );

  const preview = previewPreset
    ? createPortal(
        <PersonaPreviewSidebar
          preset={previewPreset}
          isSelected={selectedPresetId === previewPreset.id}
          isMutating={isMutating}
          onClose={() => setPreviewPreset(null)}
          onUsePreset={async (preset) => {
            const snapshot = await onUsePreset(preset);
            if (snapshot) {
              setPreviewPreset(null);
              onOpenChange(false);
            }
          }}
          onCopyPreset={(preset) => {
            onCopyPreset(preset);
          }}
        />,
        document.body,
      )
    : null;

  return (
    <>
      {selector}
      {preview}
    </>
  );
}
