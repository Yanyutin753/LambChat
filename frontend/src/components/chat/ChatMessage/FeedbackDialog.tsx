import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ThumbsUp, ThumbsDown, X, Send } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";
import type { RatingValue } from "../../../types/feedback";

interface FeedbackDialogProps {
  isOpen: boolean;
  onClose: () => void;
  rating: RatingValue;
  comment: string;
  onCommentChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  isSubmitting: boolean;
}

export function FeedbackDialog({
  isOpen,
  onClose,
  rating,
  comment,
  onCommentChange,
  onSubmit,
  onSkip,
  isSubmitting,
}: FeedbackDialogProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const swipeRef = useSwipeToClose({ onClose, enabled: isOpen });

  useEffect(() => {
    if (isOpen && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onSubmit();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, onSubmit]);

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
          className="relative z-10 w-full sm:max-w-md sm:mx-4 sm:pointer-events-auto bg-white dark:bg-stone-800 sm:rounded-xl rounded-t-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden duration-300 animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200 dark:border-stone-700">
            <div className="sm:hidden absolute top-2 left-1/2 -translate-x-1/2 w-9 h-1 bg-stone-300 dark:bg-stone-600 rounded-full" />
            <div className="flex items-center gap-2 pt-2 sm:pt-0">
              <span
                className={clsx(
                  "flex h-7 w-7 items-center justify-center rounded-full bg-stone-100 text-stone-600 dark:bg-stone-700 dark:text-stone-300",
                )}
              >
                {rating === "up" ? (
                  <ThumbsUp size={14} />
                ) : (
                  <ThumbsDown size={14} />
                )}
              </span>
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                {rating === "up"
                  ? t("feedback.positive")
                  : t("feedback.negative")}
              </h3>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
            >
              <X size={20} className="text-stone-500 dark:text-stone-400" />
            </button>
          </div>

          {/* Content */}
          <div className="p-5">
            <textarea
              ref={textareaRef}
              value={comment}
              onChange={(e) => onCommentChange(e.target.value)}
              placeholder={
                t("feedback.commentPlaceholder") || "What could be improved?"
              }
              className={clsx(
                "w-full resize-none rounded-lg border border-stone-200 p-3 text-sm",
                "bg-stone-50 dark:border-stone-700 dark:bg-stone-900",
                "text-stone-900 dark:text-stone-100",
                "placeholder:text-stone-400 dark:placeholder:text-stone-500",
                "focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400",
                "transition-colors",
              )}
              rows={4}
            />
            <div className="mt-2 text-xs text-stone-400 text-right">
              {t("feedback.pressEnter") || "⌘+Enter to send"}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 px-5 py-4 bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700 safe-area-bottom">
            <button
              onClick={onSkip}
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("common.skip") || "Skip"}
            </button>
            <button
              onClick={onSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-stone-900 hover:bg-stone-800 dark:bg-stone-600 dark:hover:bg-stone-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent dark:border-stone-900" />
              ) : (
                <Send size={14} />
              )}
              <span>{t("feedback.submit") || "Submit"}</span>
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
