import { ModalSurface } from "../common/ModalSurface";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  Search,
  Settings2,
  UserRound,
  X,
  Sparkles,
  Copy,
  Pin,
  Star,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import type { PersonaPreset, PersonaPresetSnapshot } from "../../types";
import {
  isPersonaImageAvatar,
  isEmojiAvatar,
  getEmojiAvatarUrl,
} from "./personaAvatar";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import { PersonaPreviewSidebar } from "./PersonaPreviewSidebar";
import { Pagination } from "../common/Pagination";
import { PanelSearchInput } from "../common/PanelSearchInput";
import { ResourceCardTags } from "../common/ResourceCardTags";

const LOCAL_PAGE_SIZE = 20;

interface PersonaPresetSelectorProps {
  presets: PersonaPreset[];
  total?: number;
  page?: number;
  /** Items per page; must match the parent's remote fetch limit when remote filtering is used. */
  pageSize?: number;
  selectedPresetId?: string | null;
  isOpen: boolean;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  isMutating?: boolean;
  canManagePresets?: boolean;
  onOpenChange: (open: boolean) => void;
  onPageChange?: (page: number) => void;
  onSearchChange?: (query: string) => void;
  onTagChange?: (tag: string | null) => void;
  onUsePreset: (preset: PersonaPreset) => Promise<PersonaPresetSnapshot | null>;
  onTogglePreference?: (
    preset: PersonaPreset,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => Promise<void>;
  onCopyPreset: (preset: PersonaPreset) => Promise<void>;
  onManagePresets?: () => void;
  onClearPreset: () => void;
}

export function PersonaPresetSelector({
  presets,
  total,
  page: controlledPage,
  pageSize: pageSizeProp,
  selectedPresetId,
  isOpen,
  isLoading = false,
  error,
  onRetry,
  isMutating = false,
  canManagePresets = false,
  onOpenChange,
  onPageChange,
  onSearchChange,
  onTagChange,
  onUsePreset,
  onTogglePreference,
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
  const [pendingUsePresetId, setPendingUsePresetId] = useState<string | null>(
    null,
  );
  const [page, setPage] = useState(1);
  const pageSize = pageSizeProp ?? LOCAL_PAGE_SIZE;
  const currentPage = controlledPage ?? page;
  const usesRemoteFiltering = !!onSearchChange || !!onTagChange;

  const tags = useMemo(
    () => Array.from(new Set(presets.flatMap((preset) => preset.tags))).sort(),
    [presets],
  );

  const filtered = useMemo(() => {
    if (usesRemoteFiltering) return presets;
    const q = query.trim().toLowerCase();
    return presets.filter((preset) => {
      const matchesQuery =
        !q ||
        preset.name.toLowerCase().includes(q) ||
        preset.description.toLowerCase().includes(q);
      const matchesTag = !activeTag || preset.tags.includes(activeTag);
      return matchesQuery && matchesTag;
    });
  }, [activeTag, presets, query, usesRemoteFiltering]);

  useEffect(() => {
    setPage(1);
    onPageChange?.(1);
  }, [query, activeTag, onPageChange]);

  useEffect(() => {
    onSearchChange?.(query);
  }, [onSearchChange, query]);

  useEffect(() => {
    onTagChange?.(activeTag);
  }, [activeTag, onTagChange]);

  const paged = useMemo(() => {
    if (usesRemoteFiltering) return filtered;
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [currentPage, filtered, pageSize, usesRemoteFiltering]);

  const totalItems = total ?? filtered.length;
  const handleUsePreset = async (preset: PersonaPreset) => {
    setPendingUsePresetId(preset.id);
    try {
      return await onUsePreset(preset);
    } finally {
      setPendingUsePresetId(null);
    }
  };

  const handlePageChange = (nextPage: number) => {
    if (onPageChange) {
      onPageChange(nextPage);
    } else {
      setPage(nextPage);
    }
  };

  if (!isOpen) return null;

  const selector = (
    <ModalSurface
      className="modal-wide"
      open={isOpen}
      onClose={() => onOpenChange(false)}
    >
      <div
        className="resource-picker flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-2xl shadow-2xl sm:max-w-3xl md:max-w-4xl lg:max-w-5xl xl:max-w-6xl sm:rounded-2xl safe-area-bottom"
        style={{ background: "var(--theme-bg-card)" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="resource-picker-header flex items-center justify-between border-b px-5 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-theme-bg-subtle dark:bg-stone-800">
              <UserRound size={18} style={{ color: "var(--theme-primary)" }} />
            </div>
            <div>
              <h2
                className="text-16 font-semibold"
                style={{ color: "var(--theme-text)" }}
              >
                {t("personaPresets.title", "角色广场")}
              </h2>
              <p
                className="text-12"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("personaPresets.subtitle", "选择一个角色开始对话")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {canManagePresets && onManagePresets && (
              <button
                type="button"
                title={t("personaPresets.manage", "管理角色")}
                aria-label={t("personaPresets.manage", "管理角色")}
                onClick={() => {
                  onOpenChange(false);
                  onManagePresets();
                }}
                className="inline-flex items-center gap-1.5 rounded-lg p-2 text-12 font-medium transition-colors hover:bg-theme-bg-subtle dark:hover:bg-stone-800 sm:px-2.5"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                <Settings2 size={18} className="shrink-0" />
                <span className="hidden sm:inline">
                  {t("personaPresets.manage", "管理角色")}
                </span>
              </button>
            )}
            <button
              type="button"
              className="rounded-lg p-2 hover:bg-theme-bg-subtle dark:hover:bg-stone-800"
              aria-label={t("common.close")}
              onClick={() => onOpenChange(false)}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="resource-picker-toolbar space-y-3 border-b px-5 py-3 border-theme-border/70 dark:border-stone-700/70">
          <div className="flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-theme-text-tertiary"
              />
              <PanelSearchInput
                value={query}
                onValueChange={setQuery}
                placeholder={t("personaPresets.search", "搜索角色")}
                maxLength={100}
                className="h-10 w-full rounded-lg border bg-transparent pl-9 pr-3 text-14 outline-none"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text)",
                }}
              />
            </div>
            {selectedPresetId && (
              <button
                type="button"
                onClick={onClearPreset}
                className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-12 font-medium transition-colors hover:border-[var(--theme-text-secondary)]"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                <span
                  className="size-1.5 shrink-0 rounded-full"
                  style={{ background: "var(--theme-primary)" }}
                />
                {t("personaPresets.clear", "清除使用")}
              </button>
            )}
          </div>
          {tags.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              <button
                type="button"
                aria-pressed={activeTag === null}
                onClick={() => setActiveTag(null)}
                className="shrink-0 rounded-full border px-3 py-1 text-12"
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
                  aria-pressed={activeTag === tag}
                  onClick={() => setActiveTag(tag)}
                  className="shrink-0 rounded-full border px-3 py-1 text-12"
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
          {error && (
            <div
              role="alert"
              className="mb-4 text-center text-14 text-theme-text-secondary"
            >
              <p>{error}</p>
              {onRetry && (
                <button
                  type="button"
                  disabled={isLoading}
                  className="btn-secondary mt-3"
                  onClick={onRetry}
                >
                  {t("common.retry")}
                </button>
              )}
            </div>
          )}
          {isLoading ? (
            <div className="py-10 text-center text-14 text-theme-text-secondary">
              {t("common.loading", "加载中...")}
            </div>
          ) : !error && filtered.length === 0 ? (
            <div className="py-10 text-center text-14 text-theme-text-secondary">
              {query.trim() || activeTag
                ? t("personaPresets.noMatch")
                : t("personaPresets.empty", "暂无角色预设")}
            </div>
          ) : (
            <div className="grid auto-grid-cols gap-3">
              {paged.map((preset, index) => {
                const selected = selectedPresetId === preset.id;
                const isUsingPreset = pendingUsePresetId === preset.id;
                const gradient = nameToGradient(preset.name);
                const primaryTag = preset.tags[0];
                return (
                  <div
                    key={preset.id}
                    className="pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none"
                    style={{ animationDelay: `${Math.min(index * 30, 180)}ms` }}
                    onClick={() => setPreviewPreset(preset)}
                  >
                    {/* Gradient Banner */}
                    <div
                      className="pps-card__banner relative h-12 shrink-0"
                      style={{
                        background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
                      }}
                    >
                      {selected && (
                        <span className="scb__status-pill scb__status-pill--installed absolute top-1.5 right-2">
                          {t("personaPresets.using", "使用中")}
                        </span>
                      )}
                      {onTogglePreference && (
                        <div className="absolute left-2 top-2 flex gap-1.5">
                          <button
                            type="button"
                            className={`pps-card__icon-action ${
                              preset.is_pinned
                                ? "pps-card__icon-action--active-pin"
                                : ""
                            }`}
                            title={t("personaPresets.pin", "置顶")}
                            aria-pressed={!!preset.is_pinned}
                            onClick={(event) => {
                              event.stopPropagation();
                              void onTogglePreference(preset, {
                                is_pinned: !preset.is_pinned,
                              });
                            }}
                          >
                            <Pin size={12} />
                          </button>
                          <button
                            type="button"
                            className={`pps-card__icon-action ${
                              preset.is_favorite
                                ? "pps-card__icon-action--active-fav"
                                : ""
                            }`}
                            title={t("personaPresets.favorite", "收藏")}
                            aria-pressed={!!preset.is_favorite}
                            onClick={(event) => {
                              event.stopPropagation();
                              void onTogglePreference(preset, {
                                is_favorite: !preset.is_favorite,
                              });
                            }}
                          >
                            <Star size={12} />
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Card Body */}
                    <div className="flex flex-1 flex-col p-4 pt-5">
                      {/* Title row */}
                      <div className="flex items-start gap-3">
                        <div className="pps-card__avatar shrink-0">
                          {isPersonaImageAvatar(preset.avatar) ||
                          isEmojiAvatar(preset.avatar) ? (
                            <PersonaAvatarImage
                              avatar={
                                isEmojiAvatar(preset.avatar)
                                  ? getEmojiAvatarUrl(preset.avatar)
                                  : preset.avatar
                              }
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
                              size={20}
                              className="pps-card__avatar-icon"
                            />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3 className="text-16 font-semibold font-serif text-theme-text leading-tight">
                            <button
                              type="button"
                              className="pps-card__title w-full text-left"
                              title={preset.name}
                              onClick={(event) => {
                                event.stopPropagation();
                                setPreviewPreset(preset);
                              }}
                            >
                              <span className="line-clamp-2">
                                {preset.name}
                              </span>
                            </button>
                          </h3>
                          <div className="mt-1.5 flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
                            <span>
                              {preset.scope === "global"
                                ? t("personaPresets.official", "官方")
                                : t("personaPresets.mine", "我的")}
                            </span>
                            {preset.usage_count > 0 && (
                              <>
                                <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
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
                      <p className="mt-3 text-13 leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2 min-h-[3.25em]">
                        {preset.description || preset.system_prompt}
                      </p>

                      {preset.tags.length > 0 && (
                        <div className="mt-3">
                          <ResourceCardTags tags={preset.tags} />
                        </div>
                      )}

                      <div className="flex-1" />

                      {/* Actions */}
                      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
                        <button
                          type="button"
                          disabled={isMutating || isUsingPreset}
                          aria-busy={isUsingPreset}
                          onClick={async (e) => {
                            e.stopPropagation();
                            const snapshot = await handleUsePreset(preset);
                            if (snapshot) onOpenChange(false);
                          }}
                          className={`pps-card__action ${
                            selected
                              ? "pps-card__action--active"
                              : "pps-card__action--primary"
                          } ${
                            isUsingPreset ? "pps-card__action--loading" : ""
                          }`}
                        >
                          {isUsingPreset ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Sparkles size={13} />
                          )}
                          {isUsingPreset
                            ? t("personaPresets.applying", "使用中...")
                            : selected
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

        <div
          className="border-t px-5 py-3 empty:hidden"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <Pagination
            page={currentPage}
            pageSize={pageSize}
            total={totalItems}
            onChange={handlePageChange}
          />
        </div>
      </div>
    </ModalSurface>
  );

  const preview = previewPreset
    ? createPortal(
        <PersonaPreviewSidebar
          preset={previewPreset}
          isSelected={selectedPresetId === previewPreset.id}
          isMutating={isMutating}
          isUsingPreset={pendingUsePresetId === previewPreset.id}
          onClose={() => setPreviewPreset(null)}
          onUsePreset={async (preset) => {
            const snapshot = await handleUsePreset(preset);
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
