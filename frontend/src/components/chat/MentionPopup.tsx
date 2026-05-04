import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import type { PersonaPreset } from "../../types";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import { isPersonaImageAvatar } from "../persona/personaAvatar";

interface MentionPopupProps {
  filteredPresets: PersonaPreset[];
  highlightedIndex: number;
  selectedPresetId?: string | null;
  position: { top: number; left: number } | null;
  onSelect: (preset: PersonaPreset) => void;
  onHover: (index: number) => void;
  onClose: () => void;
}

export function MentionPopup({
  filteredPresets,
  highlightedIndex,
  selectedPresetId,
  position,
  onSelect,
  onHover,
  onClose,
}: MentionPopupProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    const el = itemRefs.current[highlightedIndex];
    if (el) {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  if (!position) return null;

  const vw = window.innerWidth;
  const isMobile = vw < 640;
  const popupWidth = isMobile ? vw - 32 : Math.min(320, vw - 32);
  let left = position.left;
  if (left + popupWidth > vw - 16) {
    left = vw - popupWidth - 16;
  }
  if (left < 8) left = 8;

  return createPortal(
    <div className="fixed inset-0 z-[9999]" onMouseDown={onClose}>
      <div
        ref={containerRef}
        className="mention-popup"
        role="listbox"
        style={{
          position: "fixed",
          top: position.top,
          left,
          width: popupWidth,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {filteredPresets.length === 0 ? (
          <div className="mention-popup-empty">
            {t("chat.mentionNoResults", "没有匹配的角色")}
          </div>
        ) : (
          filteredPresets.map((preset, index) => {
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
                <div className="mention-popup-avatar">
                  {isPersonaImageAvatar(preset.avatar) ? (
                    <PersonaAvatarImage
                      avatar={preset.avatar}
                      alt=""
                      className="mention-popup-avatar-img"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <PersonaAvatarIcon
                      avatar={preset.avatar}
                      primaryTag={preset.tags[0]}
                      size={16}
                      className="mention-popup-avatar-icon"
                    />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mention-popup-name">
                    {preset.name}
                    {isSelected && (
                      <Check
                        size={13}
                        className="inline-block ml-1.5 opacity-60"
                      />
                    )}
                  </div>
                  <div className="mention-popup-desc">
                    {preset.description || preset.system_prompt}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>,
    document.body,
  );
}
