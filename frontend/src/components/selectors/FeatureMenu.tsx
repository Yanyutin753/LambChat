import {
  useState,
  useRef,
  useEffect,
  memo,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Wrench, Sparkles, Bot, Brain, Wand2, ChevronDown } from "lucide-react";

export type FeaturePanel = "tools" | "skills" | "agent" | "thinking" | null;

interface FeatureMenuProps {
  activePanel: FeaturePanel;
  onOpen: (panel: FeaturePanel) => void;
  enabledToolsCount: number;
  totalToolsCount: number;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  hasAgentSelector: boolean;
  hasThinkingOption: boolean;
  thinkingLabel?: string;
}

function MenuItem({
  icon,
  label,
  badge,
  active,
  onClick,
  divider,
}: {
  icon: ReactNode;
  label: string;
  badge?: string;
  active?: boolean;
  onClick: () => void;
  divider?: boolean;
}) {
  return (
    <>
      {divider && <div className="feature-menu-divider" />}
      <button
        type="button"
        onClick={onClick}
        className="feature-menu-item"
        data-active={active ? "" : undefined}
      >
        <span className="feature-menu-icon">{icon}</span>
        <span className="flex-1 text-left">{label}</span>
        {badge && <span className="feature-menu-badge">{badge}</span>}
      </button>
    </>
  );
}

export const FeatureMenu = memo(function FeatureMenu({
  activePanel,
  onOpen,
  enabledToolsCount,
  totalToolsCount,
  enabledSkillsCount,
  totalSkillsCount,
  hasAgentSelector,
  hasThinkingOption,
  thinkingLabel,
}: FeatureMenuProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (triggerRef.current?.contains(e.target as Node)) return;
      if (dropdownRef.current?.contains(e.target as Node)) return;
      setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (activePanel) setIsOpen(false);
  }, [activePanel]);

  const getDropdownStyle = (): CSSProperties => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return { display: "none" };
    const vw = window.innerWidth;
    const dropdownW = Math.min(248, vw - 16);
    const left = Math.max(8, Math.min(rect.left, vw - dropdownW - 8));
    return {
      position: "fixed",
      bottom: window.innerHeight - rect.top + 8,
      left,
      width: dropdownW,
      zIndex: 9999,
    };
  };

  const hasItems =
    totalToolsCount > 0 ||
    totalSkillsCount > 0 ||
    hasAgentSelector ||
    hasThinkingOption;
  if (!hasItems) return null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        style={isOpen ? { position: "relative", zIndex: 10000 } : undefined}
        className="chat-tool-btn group"
        aria-label={t("chat.features", "功能")}
      >
        <div className="flex flex-row items-center gap-1.5">
          <Wand2 size={18} className="transition-transform duration-200" />
          <span className="text-sm font-medium">
            {t("chat.features", "功能")}
          </span>
          <ChevronDown
            size={14}
            className="feature-menu-chevron opacity-50"
            data-open={isOpen ? "true" : undefined}
          />
        </div>
      </button>

      {isOpen &&
        createPortal(
          <div
            ref={dropdownRef}
            className="feature-menu-dropdown"
            style={{
              ...getDropdownStyle(),
              background: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
            }}
          >
            {totalToolsCount > 0 && (
              <MenuItem
                icon={<Wrench size={15} />}
                label={t("tools.title")}
                badge={`${enabledToolsCount}/${totalToolsCount}`}
                active={activePanel === "tools"}
                onClick={() => onOpen("tools")}
              />
            )}
            {totalSkillsCount > 0 && (
              <MenuItem
                icon={<Sparkles size={15} />}
                label={t("skillSelector.title", "技能")}
                badge={`${enabledSkillsCount}/${totalSkillsCount}`}
                active={activePanel === "skills"}
                onClick={() => onOpen("skills")}
                divider={totalToolsCount > 0}
              />
            )}
            {hasAgentSelector && (
              <MenuItem
                icon={<Bot size={15} />}
                label={t("agent.selectMode", "智能体")}
                active={activePanel === "agent"}
                onClick={() => onOpen("agent")}
                divider={totalToolsCount > 0 || totalSkillsCount > 0}
              />
            )}
            {hasThinkingOption && (
              <MenuItem
                icon={<Brain size={15} />}
                label={t("chat.thinkingIntensity", "思考强度")}
                badge={thinkingLabel}
                active={activePanel === "thinking"}
                onClick={() => onOpen("thinking")}
                divider={
                  totalToolsCount > 0 ||
                  totalSkillsCount > 0 ||
                  hasAgentSelector
                }
              />
            )}
          </div>,
          document.body,
        )}
    </>
  );
});
