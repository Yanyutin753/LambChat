import { useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2, Pin, Star } from "lucide-react";
import type { PersonaPreset } from "../../types";
import { PersonaAvatarWithLoading } from "../persona/PersonaAvatarWithLoading";

interface MentionPopupProps {
  presets: PersonaPreset[];
  highlightedIndex: number;
  selectedPresetId?: string | null;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  onSelect: (preset: PersonaPreset) => void;
  onTogglePreference?: (
    preset: PersonaPreset,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => Promise<void>;
  onHover: (index: number) => void;
  onClose: () => void;
  onLoadMore?: () => void;
  placement?: {
    left: number;
    width: number;
    bottom: number;
    maxHeight: number;
  } | null;
}

function SkeletonItems() {
  return (
    <>
      {[1, 2, 3, 4, 5].map((n) => (
        <div key={n} className="mention-skeleton-item">
          <div className="mention-skeleton-avatar" />
          <div className="mention-skeleton-text">
            <div className="mention-skeleton-name" />
            <div className="mention-skeleton-desc" />
          </div>
        </div>
      ))}
    </>
  );
}

export function MentionPopup({
  presets,
  highlightedIndex,
  selectedPresetId,
  isLoading,
  isLoadingMore,
  hasMore,
  onSelect,
  onTogglePreference,
  onHover,
  onClose,
  onLoadMore,
  placement,
}: MentionPopupProps) {
  const { t } = useTranslation();
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = itemRefs.current[highlightedIndex];
    if (el) {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (!el || !hasMore || isLoadingMore) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    if (scrollHeight - scrollTop - clientHeight < 60) {
      onLoadMore?.();
    }
  }, [hasMore, isLoadingMore, onLoadMore]);

  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  return (
    <div
      ref={anchorRef}
      className="mention-popup-anchor"
      style={
        placement
          ? ({
              "--mention-popup-left": `${placement.left}px`,
              "--mention-popup-width": `${placement.width}px`,
              "--mention-popup-bottom": `${placement.bottom}px`,
              "--mention-popup-max-height": `${placement.maxHeight}px`,
            } as React.CSSProperties)
          : undefined
      }
    >
      <div className="mention-popup">
        <div className="mention-popup-content">
          {isLoading && presets.length === 0 ? (
            <div className="mention-popup-list">
              <SkeletonItems />
            </div>
          ) : presets.length === 0 ? (
            <div className="mention-popup-empty">
              {t("chat.mentionNoResults", "没有匹配的角色")}
            </div>
          ) : (
            <div
              ref={listRef}
              className="mention-popup-list"
              onScroll={handleScroll}
            >
              {presets.map((preset, index) => {
                const isActive = index === highlightedIndex;
                const isSelected = selectedPresetId === preset.id;
                return (
                  <button
                    key={preset.id}
                    ref={(el) => {
                      itemRefs.current[index] = el;
                    }}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    className={`mention-popup-item ${
                      isActive ? "mention-popup-item--active" : ""
                    }`}
                    onClick={() => onSelect(preset)}
                    onMouseEnter={() => onHover(index)}
                  >
                    <PersonaAvatarWithLoading
                      preset={preset}
                      className="mention-popup-avatar"
                      imgClassName="mention-popup-avatar-img"
                      iconSize={14}
                    />
                    <div className="mention-popup-text">
                      <span className="mention-popup-name font-serif">
                        {preset.name}
                        {isSelected && (
                          <Check
                            size={13}
                            className="inline-block ml-1.5 opacity-60"
                          />
                        )}
                      </span>
                      <span className="mention-popup-desc">
                        {preset.description || preset.system_prompt}
                      </span>
                    </div>
                    {onTogglePreference && (
                      <span className="mention-popup-actions">
                        <button
                          type="button"
                          className={`mention-popup-action ${
                            preset.is_pinned
                              ? "mention-popup-action--active-pin"
                              : ""
                          }`}
                          title={t("personaPresets.pin", "置顶")}
                          aria-label={t("personaPresets.pin", "置顶")}
                          onClick={(event) => {
                            event.preventDefault();
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
                          className={`mention-popup-action ${
                            preset.is_favorite
                              ? "mention-popup-action--active-fav"
                              : ""
                          }`}
                          title={t("personaPresets.favorite", "收藏")}
                          aria-label={t("personaPresets.favorite", "收藏")}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void onTogglePreference(preset, {
                              is_favorite: !preset.is_favorite,
                            });
                          }}
                        >
                          <Star size={12} />
                        </button>
                      </span>
                    )}
                  </button>
                );
              })}
              {isLoadingMore && (
                <div className="mention-popup-loading">
                  <Loader2 size={14} className="animate-spin" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
