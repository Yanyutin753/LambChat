import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Bot, X } from "lucide-react";

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

  // 锁定滚动
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (agents.length <= 1 || !onSelectAgent) return null;

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          setOpen(true);
        }}
        className="chat-tool-btn"
        title={current ? t(current.name) : ""}
      >
        <Bot size={18} />
      </button>

      {open &&
        createPortal(
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-50 bg-black/50 animate-fade-in"
              onClick={() => setOpen(false)}
            />

            {/* Modal Content */}
            <div className="fixed z-50 sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in">
              <div
                className="sm:rounded-2xl rounded-t-2xl shadow-2xl w-full sm:w-auto sm:min-w-[600px] min-h-[40vh] sm:max-h-[80vh] max-h-[85vh] max-h-[85dvh] flex flex-col overflow-hidden"
                style={{ background: "var(--theme-bg-card)" }}
                onClick={(e) => e.stopPropagation()}
              >
                {/* Header */}
                <div
                  className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b relative"
                  style={{ borderColor: "var(--theme-border)" }}
                >
                  {/* Mobile drag handle */}
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
                    onClick={() => setOpen(false)}
                    className="p-2 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 active:bg-stone-200 dark:active:bg-stone-600 transition-colors"
                  >
                    <X
                      size={18}
                      className="text-stone-400 dark:text-stone-500"
                    />
                  </button>
                </div>

                {/* Agent list */}
                <div className="flex-1 overflow-y-auto p-2.5 sm:p-3 space-y-1">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      type="button"
                      disabled={false}
                      className={`flex w-full items-center gap-1.5 sm:gap-2 px-2 sm:px-2.5 py-2 sm:py-2.5 rounded-lg transition-all duration-200 ${
                        agent.id === currentAgent
                          ? "hover:bg-stone-50 dark:hover:bg-stone-700/30 active:bg-stone-100/80 dark:active:bg-stone-600/40"
                          : "bg-[var(--theme-primary)]/[0.06] dark:bg-[var(--theme-primary)]/[0.08] hover:bg-[var(--theme-primary)]/[0.12] dark:hover:bg-[var(--theme-primary)]/[0.14] active:bg-[var(--theme-primary)]/[0.18] dark:active:bg-[var(--theme-primary)]/[0.20]"
                      }`}
                      onClick={() => {
                        onSelectAgent(agent.id);
                        setOpen(false);
                      }}
                    >
                      <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg bg-white dark:bg-stone-700 flex items-center justify-center shadow-sm border border-stone-100 dark:border-stone-600">
                        <Bot
                          size={13}
                          className={`sm:w-[14px] sm:h-[14px] ${
                            agent.id === currentAgent
                              ? "text-[var(--theme-primary)]"
                              : "text-stone-500 dark:text-stone-400"
                          }`}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <span
                          className={`text-[12px] sm:text-[13px] font-medium truncate ${
                            agent.id === currentAgent
                              ? "text-stone-700 dark:text-stone-200"
                              : "text-[var(--theme-primary)] dark:text-[var(--theme-primary)]"
                          }`}
                        >
                          {t(agent.name)}
                        </span>
                        {agent.description && (
                          <p className="text-xs text-stone-400 dark:text-stone-500 truncate mt-0.5 leading-relaxed text-left">
                            {t(agent.description)}
                          </p>
                        )}
                      </div>
                      {agent.id === currentAgent && (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="3"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-white border-2 border-[var(--theme-primary)] bg-[var(--theme-primary)] rounded-[5px] shadow-[0_0_8px_color-mix(in_srgb,var(--theme-primary)_30%,transparent)] animate-[check-pop_200ms_ease-out]"
                        >
                          <path d="M20 6 9 17l-5-5"></path>
                        </svg>
                      )}
                    </button>
                  ))}
                </div>

                {/* Footer */}
                <div className="px-4 sm:px-5 py-3 sm:py-3.5 border-t border-stone-200 dark:border-stone-700 bg-stone-50/80 dark:bg-stone-800/50 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
                  <button
                    onClick={() => setOpen(false)}
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
