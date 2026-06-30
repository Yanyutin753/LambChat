import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import i18n from "../../i18n";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { AgentIcon } from "../agent/AgentIcon";
import {
  resolveAgentDescription,
  resolveAgentDisplayName,
} from "../agent/agentCatalog";
import type { AgentCatalogLabels } from "../../types";
import {
  SelectorModalHeader,
  SelectorModalPortal,
  SelectorModalShell,
} from "./shared";

interface AgentModeSelectorProps {
  agents: {
    id: string;
    name: string;
    description: string;
    icon?: string;
    labels?: AgentCatalogLabels;
  }[];
  currentAgent: string;
  onSelectAgent?: (id: string) => void;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function AgentModeSelector({
  agents,
  currentAgent,
  onSelectAgent,
  isOpen: externalIsOpen,
  onOpenChange: externalOnOpenChange,
}: AgentModeSelectorProps) {
  const { t } = useTranslation();
  const [internalOpen, setInternalOpen] = useState(false);
  const open = externalIsOpen ?? internalOpen;
  const setOpen = externalOnOpenChange ?? setInternalOpen;

  const current = agents.find((a) => a.id === currentAgent);
  const currentName = current
    ? resolveAgentDisplayName(current, i18n.language, t)
    : "";
  const sheetRef = useSwipeToClose({ onClose: () => setOpen(false) });
  useBodyScrollLock(open);

  const handleClose = useCallback(() => setOpen(false), [setOpen]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, setOpen]);

  if (agents.length <= 1 || !onSelectAgent) return null;

  const renderModalContent = () => (
    <SelectorModalShell ref={sheetRef as React.Ref<HTMLDivElement>}>
      <SelectorModalHeader
        className="relative"
        icon={
          <Bot
            size={16}
            className="text-stone-500 dark:text-amber-400 sm:w-[18px] sm:h-[18px]"
          />
        }
        title={t("agent.selectMode", "选择模式")}
        subtitle={t("agent.selectModeDesc", "切换智能体模式")}
        subtitleClassName="text-xs text-stone-500 dark:text-stone-400"
        onClose={handleClose}
      />

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4 space-y-1.5">
        {agents.map((agent) => {
          const isActive = agent.id === currentAgent;
          const displayName = resolveAgentDisplayName(agent, i18n.language, t);
          const displayDescription = resolveAgentDescription(
            agent,
            i18n.language,
            t,
          );
          return (
            <button
              key={agent.id}
              type="button"
              className={`flex w-full items-center gap-3 px-3 sm:px-3.5 py-3 sm:py-3.5 rounded-xl text-left transition-all duration-200 ${
                isActive
                  ? "bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/15"
                  : "hover:bg-stone-50 dark:hover:bg-stone-700/30 active:bg-stone-100/80 dark:active:bg-stone-600/40"
              }`}
              onClick={() => {
                onSelectAgent(agent.id);
                setOpen(false);
              }}
            >
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center shrink-0 bg-white dark:bg-stone-700 shadow-sm border border-stone-100 dark:border-stone-600 overflow-hidden">
                <AgentIcon
                  icon={agent.icon || "Bot"}
                  size={24}
                  className={`sm:w-[26px] sm:h-[26px] ${
                    isActive
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-stone-500 dark:text-stone-400"
                  }`}
                />
              </div>
              <div className="flex-1 min-w-0">
                <span
                  className={`text-[13px] sm:text-sm font-medium truncate block ${
                    isActive
                      ? "text-amber-700 dark:text-amber-400"
                      : "text-stone-700 dark:text-stone-200"
                  }`}
                >
                  {displayName}
                </span>
                {agent.description && (
                  <p className="text-xs text-stone-400 dark:text-stone-500 truncate mt-0.5 leading-relaxed text-left">
                    {displayDescription}
                  </p>
                )}
              </div>
              {isActive && (
                <div className="w-5 h-5 rounded-full bg-amber-500 dark:bg-amber-500 flex items-center justify-center shrink-0">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="white"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </SelectorModalShell>
  );

  // When controlled externally, only render the modal — no trigger button
  if (externalOnOpenChange) {
    return (
      <SelectorModalPortal open={open} onClose={handleClose}>
        {renderModalContent()}
      </SelectorModalPortal>
    );
  }

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="chat-tool-btn"
        title={currentName}
      >
        <AgentIcon icon={current?.icon || "Bot"} size={18} />
      </button>

      {open && (
        <SelectorModalPortal open={open} onClose={handleClose}>
          {renderModalContent()}
        </SelectorModalPortal>
      )}
    </div>
  );
}
