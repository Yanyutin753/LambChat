import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Bot, X } from "lucide-react";
import { Checkbox } from "../common/Checkbox";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface AgentModeSelectorProps {
  agents: { id: string; name: string; description: string }[];
  currentAgent: string;
  onSelectAgent?: (id: string) => void;
}

export function AgentModeSelector({
  agents,
  currentAgent,
  onSelectAgent,
}: AgentModeSelectorProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const current = agents.find((a) => a.id === currentAgent);
  const sheetRef = useSwipeToClose({ onClose: () => setOpen(false) });

  const handleClose = useCallback(() => setOpen(false), []);

  // Prevent background scroll when modal is open, restore previous value on close
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  if (agents.length <= 1 || !onSelectAgent) return null;

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="chat-tool-btn"
        title={current ? t(current.name) : ""}
      >
        <Bot size={18} />
      </button>

      {open &&
        createPortal(
          <>
            <div
              className="fixed inset-0 z-[300] bg-black/50 animate-fade-in"
              onClick={handleClose}
            />

            <div
              className="fixed z-[301] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"
              onClick={handleClose}
            >
              <div
                ref={sheetRef as React.Ref<HTMLDivElement>}
                className="sm:rounded-2xl rounded-t-2xl shadow-2xl w-full sm:w-[40%] sm:min-w-[600px] min-h-[40vh] sm:max-h-[80vh] max-h-[85vh] max-h-[85dvh] flex flex-col overflow-hidden"
                style={{ background: "var(--theme-bg-card)" }}
                onClick={(e) => e.stopPropagation()}
              >
                <div
                  className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b relative"
                  style={{ borderColor: "var(--theme-border)" }}
                >
                  <div className="absolute left-1/2 -translate-x-1/2 top-2 w-10 h-1 rounded-full bg-stone-300 dark:bg-stone-600 sm:hidden" />

                  <div className="flex items-center gap-3 mt-2 sm:mt-0">
                    <div className="size-9 sm:size-10 rounded-xl bg-gradient-to-br from-stone-100 to-stone-200 dark:from-amber-500/20 dark:to-orange-500/20 flex items-center justify-center">
                      <Bot
                        size={16}
                        className="text-stone-500 dark:text-amber-400 sm:w-[18px] sm:h-[18px]"
                      />
                    </div>
                    <div>
                      <h2 className="text-sm sm:text-base font-semibold text-stone-900 dark:text-stone-100 font-serif">
                        {t("agent.selectMode", "选择模式")}
                      </h2>
                      <p className="text-xs text-stone-500 dark:text-stone-400">
                        {t("agent.selectModeDesc", "切换智能体模式")}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={handleClose}
                    className="p-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 transition-colors"
                  >
                    <X
                      size={18}
                      className="text-stone-400 dark:text-stone-500"
                    />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-2">
                  {agents.map((agent) => {
                    const isActive = agent.id === currentAgent;
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        className="flex w-full items-center gap-3 px-3.5 py-3.5 rounded-xl text-left transition-all duration-200"
                        style={{
                          backgroundColor: isActive
                            ? "color-mix(in srgb, var(--theme-primary) 8%, transparent)"
                            : "",
                          boxShadow: isActive
                            ? "inset 0 0 0 1px color-mix(in srgb, var(--theme-primary) 15%, transparent)"
                            : "none",
                          color: isActive
                            ? "var(--theme-primary)"
                            : "var(--theme-text)",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = isActive
                            ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)"
                            : "color-mix(in srgb, var(--theme-primary) 4%, transparent)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = isActive
                            ? "color-mix(in srgb, var(--theme-primary) 8%, transparent)"
                            : "";
                        }}
                        onMouseDown={(e) => {
                          e.currentTarget.style.backgroundColor = isActive
                            ? "color-mix(in srgb, var(--theme-primary) 16%, transparent)"
                            : "color-mix(in srgb, var(--theme-primary) 8%, transparent)";
                        }}
                        onMouseUp={(e) => {
                          e.currentTarget.style.backgroundColor = isActive
                            ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)"
                            : "color-mix(in srgb, var(--theme-primary) 4%, transparent)";
                        }}
                        onClick={() => {
                          onSelectAgent(agent.id);
                          setOpen(false);
                        }}
                      >
                        <div
                          className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl flex items-center justify-center shrink-0"
                          style={{
                            backgroundColor: isActive
                              ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)"
                              : "color-mix(in srgb, var(--theme-primary) 5%, transparent)",
                          }}
                        >
                          <Bot
                            size={17}
                            className="sm:w-[18px] sm:h-[18px]"
                            style={{
                              color: isActive
                                ? "var(--theme-primary)"
                                : "var(--theme-text-secondary)",
                            }}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span
                            className="text-sm font-medium truncate block"
                            style={{
                              color: isActive
                                ? "var(--theme-primary)"
                                : "var(--theme-text)",
                            }}
                          >
                            {t(agent.name)}
                          </span>
                          {agent.description && (
                            <p
                              className="text-xs truncate mt-1 text-left leading-relaxed"
                              style={{ color: "var(--theme-text-secondary)" }}
                            >
                              {t(agent.description)}
                            </p>
                          )}
                        </div>
                        {isActive && <Checkbox checked size="sm" />}
                      </button>
                    );
                  })}
                </div>

                <div className="px-4 sm:px-5 py-3 sm:py-3.5 border-t border-stone-200 dark:border-stone-700 bg-stone-50/80 dark:bg-stone-800/50 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
                  <button
                    onClick={handleClose}
                    className="w-full py-2.5 px-4 bg-stone-900 dark:bg-stone-600 text-white dark:text-stone-100 rounded-xl font-medium text-sm hover:bg-stone-800 dark:hover:bg-stone-500 active:bg-stone-700 dark:active:bg-stone-600 transition-colors"
                  >
                    {t("common.done", "完成")}
                  </button>
                </div>
              </div>
            </div>
          </>,
          document.body,
        )}
    </div>
  );
}
