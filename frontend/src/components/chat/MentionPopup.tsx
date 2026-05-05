import { useEffect, useRef, useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2 } from "lucide-react";
import type { PersonaPreset } from "../../types";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import { isPersonaImageAvatar } from "../persona/personaAvatar";

interface MentionPopupProps {
  presets: PersonaPreset[];
  highlightedIndex: number;
  selectedPresetId?: string | null;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  onSelect: (preset: PersonaPreset) => void;
  onHover: (index: number) => void;
  onClose: () => void;
  onLoadMore?: () => void;
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

function AvatarWithSkeleton({ preset }: { preset: PersonaPreset }) {
  const isImage = isPersonaImageAvatar(preset.avatar);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className={`mention-popup-avatar ${
        isImage && !imgLoaded && !imgError
          ? "mention-popup-avatar--loading"
          : isImage && imgLoaded
            ? "mention-popup-avatar--loaded"
            : ""
      }`}
    >
      {isImage ? (
        !imgError ? (
          <PersonaAvatarImage
            avatar={preset.avatar}
            alt=""
            className="mention-popup-avatar-img"
            onLoad={() => setImgLoaded(true)}
            onError={() => {
              setImgError(true);
            }}
          />
        ) : (
          <PersonaAvatarIcon
            avatar={null}
            primaryTag={preset.tags?.[0]}
            size={14}
            className="mention-popup-avatar-icon"
          />
        )
      ) : (
        <PersonaAvatarIcon
          avatar={preset.avatar}
          primaryTag={preset.tags?.[0]}
          size={14}
          className="mention-popup-avatar-icon"
        />
      )}
    </div>
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
  onHover,
  onClose,
  onLoadMore,
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

  return (
    <div className="mention-popup-anchor" onMouseDown={onClose}>
      <div className="mention-popup" onMouseDown={(e) => e.stopPropagation()}>
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
                    <AvatarWithSkeleton preset={preset} />
                    <div className="mention-popup-text">
                      <span className="mention-popup-name">
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
