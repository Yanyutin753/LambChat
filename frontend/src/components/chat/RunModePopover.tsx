import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Brain,
  ChevronDown,
  ToggleLeft,
  Zap,
  Target,
  Settings2,
  ChevronRight,
} from "lucide-react";
import { THINKING_LEVEL_COLOR } from "./chatInputConstants";
import { getRunModePopoverPosition } from "./runModePopoverPosition";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import type { AgentOption } from "../../types";

interface RunModePopoverProps {
  open: boolean;
  onClose: () => void;
  // Run mode
  autoModeEnabled: boolean;
  goalModeEnabled: boolean;
  onToggleAutoMode: (enabled: boolean) => void;
  onToggleGoalMode: (enabled: boolean) => void;
  // Settings (moved from FeatureMenu)
  hasAgentSelector?: boolean;
  agentName?: string | null;
  onOpenAgentPanel?: () => void;
  hasThinkingOption?: boolean;
  thinkingLabel?: string;
  thinkingLevel?: string;
  onOpenThinkingPanel?: () => void;
  booleanAgentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
}

/** Toggle switch – track + thumb, fully themed. */
function ToggleSwitch({ on }: { on: boolean }) {
  return (
    <div className="run-mode-toggle" data-on={on ? "" : undefined}>
      <div className="run-mode-toggle-thumb" />
    </div>
  );
}

export function RunModePopover({
  open,
  onClose,
  autoModeEnabled,
  goalModeEnabled,
  onToggleAutoMode,
  onToggleGoalMode,
  hasAgentSelector,
  agentName,
  onOpenAgentPanel,
  hasThinkingOption,
  thinkingLabel,
  thinkingLevel,
  onOpenThinkingPanel,
  booleanAgentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
}: RunModePopoverProps) {
  const { t } = useTranslation();
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const hasSettings =
    hasAgentSelector ||
    hasThinkingOption ||
    Object.keys(booleanAgentOptions ?? {}).length > 0;

  const getStyle = (rect: DOMRect): CSSProperties => {
    return getRunModePopoverPosition({
      triggerRect: rect,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    });
  };

  const position = useStickyDropdownPosition(triggerRef, open, getStyle);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      const popover = document.getElementById("run-mode-popover");
      if (popover?.contains(target)) return;
      onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onClose]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Store trigger ref from the button via a custom attribute
  useEffect(() => {
    const trigger = document.querySelector("[data-run-mode-trigger]");
    if (trigger) triggerRef.current = trigger as HTMLButtonElement;
  }, [open]);

  const booleanOptionEntries = Object.entries(booleanAgentOptions ?? {});
  const [settingsExpanded, setSettingsExpanded] = useState(false);

  if (!open) return null;

  return createPortal(
    <div
      id="run-mode-popover"
      className="feature-menu-dropdown"
      style={position}
    >
      {/* ── Run Mode group ── */}
      <div className="feature-menu-group" role="group">
        <div
          className="feature-menu-group-header"
          style={{ cursor: "default", pointerEvents: "none" }}
        >
          <span className="feature-menu-group-icon">
            <Settings2 size={18} />
          </span>
          <span className="flex-1 text-left truncate">
            {t("mode.title", "Run Mode")}
          </span>
        </div>
        <div className="feature-menu-group-body" data-expanded>
          <div className="feature-menu-group-inner">
            {/* Auto Mode */}
            <button
              type="button"
              className="feature-menu-item"
              data-toggle
              data-active={autoModeEnabled ? "" : undefined}
              onClick={() => onToggleAutoMode(!autoModeEnabled)}
            >
              <span className="feature-menu-item-icon">
                <Zap size={18} />
              </span>
              <span className="flex-1 text-left truncate">
                {t("mode.auto", "Auto Mode")}
              </span>
              <ToggleSwitch on={autoModeEnabled} />
            </button>

            {/* Goal Mode */}
            <button
              type="button"
              className="feature-menu-item"
              data-toggle
              data-active={goalModeEnabled ? "" : undefined}
              onClick={() => onToggleGoalMode(!goalModeEnabled)}
            >
              <span className="feature-menu-item-icon">
                <Target size={18} />
              </span>
              <span className="flex-1 text-left truncate">
                {t("mode.goal", "Goal Mode")}
              </span>
              <ToggleSwitch on={goalModeEnabled} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Settings group ── */}
      {hasSettings && (
        <div className="feature-menu-group" role="group">
          <button
            type="button"
            className="feature-menu-group-header"
            onClick={() => setSettingsExpanded((v) => !v)}
          >
            <span className="feature-menu-group-icon">
              <Settings2 size={18} />
            </span>
            <span className="flex-1 text-left truncate">
              {t("featureMenu.settings", "Settings")}
            </span>
            <ChevronDown
              size={16}
              className="feature-menu-chevron"
              data-open={settingsExpanded ? "true" : undefined}
            />
          </button>
          <div
            className="feature-menu-group-body"
            data-expanded={settingsExpanded ? "" : undefined}
          >
            <div className="feature-menu-group-inner">
              {/* Agent Mode */}
              {hasAgentSelector && (
                <button
                  type="button"
                  className="feature-menu-item"
                  onClick={() => {
                    onOpenAgentPanel?.();
                    onClose();
                  }}
                >
                  <span className="feature-menu-item-icon">
                    <Bot size={18} />
                  </span>
                  <span className="flex-1 text-left truncate">
                    {t("agent.selectMode", "Agent Mode")}
                  </span>
                  <span className="feature-menu-item-badge">
                    {agentName ? t(agentName) : ""}
                  </span>
                  <ChevronRight size={14} className="feature-menu-chevron" />
                </button>
              )}

              {/* Thinking Intensity */}
              {hasThinkingOption && (
                <button
                  type="button"
                  className="feature-menu-item"
                  onClick={() => {
                    onOpenThinkingPanel?.();
                    onClose();
                  }}
                >
                  <span className="feature-menu-item-icon">
                    <Brain size={18} />
                  </span>
                  <span className="flex-1 text-left truncate">
                    {t("chat.thinkingIntensity", "Thinking Intensity")}
                  </span>
                  {thinkingLabel && (
                    <span
                      className="feature-menu-item-badge"
                      style={
                        THINKING_LEVEL_COLOR[thinkingLevel ?? ""]
                          ? {
                              color:
                                THINKING_LEVEL_COLOR[thinkingLevel ?? ""].text,
                              background:
                                THINKING_LEVEL_COLOR[thinkingLevel ?? ""].bg,
                            }
                          : undefined
                      }
                    >
                      {thinkingLabel}
                    </span>
                  )}
                  <ChevronRight size={14} className="feature-menu-chevron" />
                </button>
              )}

              {/* Boolean Agent Options */}
              {booleanOptionEntries.map(([key, option]) => {
                const value = agentOptionValues[key] ?? option.default;
                const enabled = value === true;
                const label = option.label_key
                  ? t(option.label_key)
                  : option.label;
                return (
                  <button
                    key={key}
                    type="button"
                    className="feature-menu-item"
                    data-toggle
                    data-active={enabled ? "" : undefined}
                    onClick={() => onToggleAgentOption?.(key, !enabled)}
                  >
                    <span className="feature-menu-item-icon">
                      <ToggleLeft size={18} />
                    </span>
                    <span className="flex-1 text-left truncate">{label}</span>
                    <ToggleSwitch on={enabled} />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}
