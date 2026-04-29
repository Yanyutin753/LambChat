import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X, Loader2, User, Bot } from "lucide-react";
import { sessionApi } from "../../services/api/session";
import type { SSEEventRecord } from "../../types/session";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface SessionPreviewDialogProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  sessionName: string;
}

interface PreviewMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

function extractMessages(events: SSEEventRecord[]): PreviewMessage[] {
  const messages: PreviewMessage[] = [];

  for (const event of events) {
    if (event.event_type === "user:message") {
      const content = event.data?.content as string | undefined;
      if (content) {
        messages.push({
          role: "user",
          content,
          timestamp: event.timestamp,
        });
      }
    } else if (event.event_type === "assistant:text") {
      const content = event.data?.content as string | undefined;
      if (content) {
        const last = messages[messages.length - 1];
        if (
          last &&
          last.role === "assistant" &&
          last.timestamp === event.timestamp
        ) {
          last.content += content;
        } else {
          messages.push({
            role: "assistant",
            content,
            timestamp: event.timestamp,
          });
        }
      }
    }
  }

  return messages;
}

export function SessionPreviewDialog({
  isOpen,
  onClose,
  sessionId,
  sessionName,
}: SessionPreviewDialogProps) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<PreviewMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const swipeRef = useSwipeToClose({ onClose, enabled: isOpen });

  const loadMessages = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await sessionApi.getEvents(sessionId);
      const previewMessages = extractMessages(response.events);
      setMessages(previewMessages);
    } catch (error) {
      console.error("Failed to load session events:", error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (isOpen) {
      loadMessages();
    }
  }, [isOpen, loadMessages]);

  useEffect(() => {
    if (isOpen) {
      const handler = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      document.addEventListener("keydown", handler);
      return () => document.removeEventListener("keydown", handler);
    }
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-[299] bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-[300] flex items-end sm:items-center sm:justify-center sm:pointer-events-none">
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="relative z-10 w-full sm:max-w-2xl sm:mx-4 sm:pointer-events-auto bg-white dark:bg-stone-800 sm:rounded-xl rounded-t-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden duration-300 max-h-[85vh] max-h-[85dvh] flex flex-col animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200 dark:border-stone-700 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="w-5 h-5 text-stone-600 dark:text-stone-300 shrink-0"
              >
                <path
                  fillRule="evenodd"
                  clipRule="evenodd"
                  d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.57354 19.4265 6.1146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.4477 5 12Z"
                  fill="currentColor"
                />
              </svg>
              <h2 className="text-sm font-semibold text-stone-800 dark:text-stone-100 truncate">
                {sessionName}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 dark:hover:text-stone-300 dark:hover:bg-stone-700 transition-colors shrink-0"
            >
              <X size={18} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={20} className="animate-spin text-stone-400" />
              </div>
            ) : messages.length === 0 ? (
              <div className="text-center py-12 text-sm text-stone-400 dark:text-stone-500">
                {t("sidebar.noMessages") || "No messages yet"}
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className="flex gap-3">
                  <div
                    className={`shrink-0 mt-0.5 flex h-7 w-7 items-center justify-center rounded-full ${
                      msg.role === "user"
                        ? "bg-stone-200 dark:bg-stone-700"
                        : "bg-stone-100 dark:bg-stone-800"
                    }`}
                  >
                    {msg.role === "user" ? (
                      <User
                        size={14}
                        className="text-stone-500 dark:text-stone-400"
                      />
                    ) : (
                      <Bot
                        size={14}
                        className="text-stone-500 dark:text-stone-400"
                      />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium text-stone-400 dark:text-stone-500 mb-1">
                      {msg.role === "user"
                        ? t("chat.user") || "You"
                        : t("chat.assistant") || "Assistant"}
                    </div>
                    <div className="text-[13px] text-stone-700 dark:text-stone-300 whitespace-pre-wrap break-words leading-relaxed">
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
