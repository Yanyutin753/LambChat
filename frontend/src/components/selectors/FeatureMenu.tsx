import { useState, useRef, useEffect, memo, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import {
  Wrench,
  Sparkles,
  Plus,
  UserRound,
  UsersRound,
  ChevronDown,
  Upload,
  Layers,
  Plug,
  Settings2,
} from "lucide-react";

import type { FileCategory } from "../../types";
import type { CoreChatInputOptionContribution } from "../../extensions/coreContributions";

export type FeaturePanel =
  | "persona"
  | "tools"
  | "skills"
  | "agent"
  | "thinking"
  | (string & {})
  | null;

const PLUGIN_OPTION_ICONS: Record<string, React.ElementType> = {
  UsersRound,
  Plug,
};

interface FeatureMenuProps {
  activePanel: FeaturePanel;
  onOpen: (panel: FeaturePanel) => void;
  enabledToolsCount: number;
  totalToolsCount: number;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  hasPersonaSelector?: boolean;
  personaName?: string | null;
  pluginOptions?: readonly CoreChatInputOptionContribution[];
  hasAgentSelector: boolean;
  agentName?: string | null;
  thinkingLabel?: string;
  thinkingLevel?: string;
  // File upload
  uploadCategories: FileCategory[];
  onUploadFiles: () => void;
}

function MenuGroup({
  label,
  icon,
  defaultExpanded = false,
  children,
}: {
  label: string;
  icon: ReactNode;
  defaultExpanded?: boolean;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <div className="feature-menu-group" role="group">
      <button
        type="button"
        className="feature-menu-group-header"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="feature-menu-group-icon">{icon}</span>
        <span className="flex-1 text-left truncate">{label}</span>
        <ChevronDown
          size={16}
          className="feature-menu-chevron"
          data-open={expanded ? "true" : undefined}
        />
      </button>
      <div
        className="feature-menu-group-body"
        data-expanded={expanded ? "" : undefined}
      >
        <div className="feature-menu-group-inner">{children}</div>
      </div>
    </div>
  );
}

function MenuItem({
  icon,
  label,
  badge,
  badgeColor,
  active,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  badge?: string;
  badgeColor?: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="feature-menu-item"
      data-active={active ? "" : undefined}
    >
      <span className="feature-menu-item-icon">{icon}</span>
      <span className="flex-1 text-left truncate">{label}</span>
      {badge && (
        <span className="feature-menu-item-badge" data-badge-color={badgeColor}>
          {badge}
        </span>
      )}
    </button>
  );
}

export const FeatureMenu = memo(function FeatureMenu({
  activePanel,
  onOpen,
  enabledToolsCount,
  totalToolsCount,
  enabledSkillsCount,
  totalSkillsCount,
  hasPersonaSelector = false,
  personaName,
  pluginOptions = [],
  uploadCategories,
  onUploadFiles,
}: FeatureMenuProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const dropdownStyle = useStickyDropdownPosition(
    triggerRef,
    isOpen,
    (rect) => {
      const vw = window.innerWidth;
      const dropdownW = Math.min(
        vw < 640 ? Math.min(240, vw - 40) : 320,
        vw - 16,
      );
      const left = Math.max(8, Math.min(rect.left, vw - dropdownW - 8));
      return {
        position: "fixed",
        bottom: window.innerHeight - rect.top + 8,
        left,
        width: dropdownW,
        zIndex: 9999,
      };
    },
  );

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

  const openDropdown = () => {
    setIsOpen((prev) => !prev);
  };

  const uploadPluginOptions = pluginOptions.filter(
    (option) => option.slot === "upload",
  );
  const settingsPluginOptions = pluginOptions.filter(
    (option) => option.slot === "settings",
  );
  const enhancePluginOptions = pluginOptions.filter(
    (option) => option.slot !== "upload" && option.slot !== "settings",
  );
  const renderPluginOption = (option: CoreChatInputOptionContribution) => {
    const Icon = PLUGIN_OPTION_ICONS[option.icon] ?? Plug;
    return (
      <MenuItem
        key={option.id}
        icon={<Icon size={18} />}
        label={t(option.label)}
        active={activePanel === option.panel}
        onClick={() => onOpen(option.panel ?? option.id)}
      />
    );
  };
  const hasFeatureItems =
    totalToolsCount > 0 ||
    totalSkillsCount > 0 ||
    hasPersonaSelector ||
    uploadPluginOptions.length > 0 ||
    settingsPluginOptions.length > 0 ||
    enhancePluginOptions.length > 0;
  if (!hasFeatureItems && uploadCategories.length === 0) return null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          openDropdown();
        }}
        style={isOpen ? { position: "relative", zIndex: 10000 } : undefined}
        className="chat-tool-btn"
        aria-label={t("chat.features", "Features")}
      >
        <Plus size={18} />
      </button>

      {isOpen &&
        createPortal(
          <div
            ref={dropdownRef}
            className="feature-menu-dropdown"
            style={{
              ...dropdownStyle,
              background: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
            }}
          >
            {(uploadCategories.length > 0 || uploadPluginOptions.length > 0) && (
              <MenuGroup
                label={t("featureMenu.upload", "Upload")}
                icon={<Upload size={18} />}
                defaultExpanded
              >
                {uploadCategories.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      onUploadFiles();
                      setIsOpen(false);
                    }}
                    className="feature-menu-item"
                  >
                    <span className="feature-menu-item-icon">
                      <Upload size={18} />
                    </span>
                    <span className="flex-1 text-left truncate">
                      {t("featureMenu.upload", "Upload")}
                    </span>
                  </button>
                )}
                {uploadPluginOptions.map(renderPluginOption)}
              </MenuGroup>
            )}
            {(hasPersonaSelector ||
              enhancePluginOptions.length > 0 ||
              totalToolsCount > 0 ||
              totalSkillsCount > 0) && (
              <MenuGroup
                label={t("featureMenu.enhance", "Enhance")}
                icon={<Layers size={18} />}
              >
                {hasPersonaSelector && (
                  <MenuItem
                    icon={<UserRound size={18} />}
                    label={t("featureMenu.persona", "Persona")}
                    badge={personaName || undefined}
                    active={activePanel === "persona"}
                    onClick={() => onOpen("persona")}
                  />
                )}
                {enhancePluginOptions.map(renderPluginOption)}
                {totalToolsCount > 0 && (
                  <MenuItem
                    icon={<Wrench size={18} />}
                    label={t("tools.title")}
                    badge={`${enabledToolsCount}/${totalToolsCount}`}
                    active={activePanel === "tools"}
                    onClick={() => onOpen("tools")}
                  />
                )}
                {totalSkillsCount > 0 && (
                  <MenuItem
                    icon={<Sparkles size={18} />}
                    label={t("skillSelector.title", "Skills")}
                    badge={`${enabledSkillsCount}/${totalSkillsCount}`}
                    active={activePanel === "skills"}
                    onClick={() => onOpen("skills")}
                  />
                )}
              </MenuGroup>
            )}
            {settingsPluginOptions.length > 0 && (
              <MenuGroup
                label={t("featureMenu.settings", "Settings")}
                icon={<Settings2 size={18} />}
              >
                {settingsPluginOptions.map(renderPluginOption)}
              </MenuGroup>
            )}
          </div>,
          document.body,
        )}
    </>
  );
});
