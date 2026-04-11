import { useState, useEffect, useRef } from "react";
import { ThumbsUp, ThumbsDown, X, Send } from "lucide-react";
import { clsx } from "clsx";
import toast from "react-hot-toast";
import { feedbackApi } from "../../../services/api/feedback";
import type { RatingValue } from "../../../types/feedback";
import { useTranslation } from "react-i18next";

interface FeedbackButtonsProps {
  sessionId: string;
  runId?: string;
  currentFeedback?: RatingValue | null;
  onFeedbackChange?: (feedback: RatingValue | null) => void;
  className?: string;
  isLastMessage?: boolean;
}

export function FeedbackButtons({
  sessionId,
  runId,
  currentFeedback: externalFeedback,
  onFeedbackChange,
  className,
  isLastMessage,
}: FeedbackButtonsProps) {
  const { t } = useTranslation();
  const [selectedRating, setSelectedRating] = useState<RatingValue | null>(
    null,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCommentInput, setShowCommentInput] = useState(false);
  const [comment, setComment] = useState("");
  const [submittedFeedback, setSubmittedFeedback] =
    useState<RatingValue | null>(externalFeedback || null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync with external feedback (e.g., from history)
  useEffect(() => {
    if (externalFeedback) {
      setSubmittedFeedback(externalFeedback);
    }
  }, [externalFeedback]);

  // Focus textarea when popup opens
  useEffect(() => {
    if (showCommentInput && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [showCommentInput]);

  // User clicks thumbs up/down - show comment input first
  function handleRatingClick(rating: RatingValue) {
    if (isSubmitting || submittedFeedback) return;
    setSelectedRating(rating);
    setShowCommentInput(true);
    setComment("");
  }

  // Submit feedback with optional comment
  async function handleSubmitFeedback() {
    if (isSubmitting || !selectedRating) return;

    setIsSubmitting(true);
    try {
      await feedbackApi.submit({
        rating: selectedRating,
        comment: comment.trim() || undefined,
        session_id: sessionId,
        run_id: runId || "",
      });
      setSubmittedFeedback(selectedRating);
      onFeedbackChange?.(selectedRating);
      setShowCommentInput(false);
      toast.success(t("feedback.submitSuccess") || "Feedback submitted");
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      toast.error(
        error instanceof Error ? error.message : t("feedback.submitFailed"),
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  // Skip comment and submit immediately
  function handleSkipComment() {
    handleSubmitFeedback();
  }

  // Cancel rating selection
  function handleCancel() {
    setSelectedRating(null);
    setShowCommentInput(false);
    setComment("");
  }

  // Handle keyboard shortcuts
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      handleCancel();
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmitFeedback();
    }
  }

  // If already submitted, show readonly indicator on hover only
  if (submittedFeedback) {
    return (
      <div className={clsx("flex items-center gap-1", className)}>
        <span
          className={clsx(
            "flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium transition-all",
            !isLastMessage && "opacity-0 group-hover:opacity-100",
            submittedFeedback === "up"
              ? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
              : "bg-stone-800 text-stone-300 dark:bg-stone-200 dark:text-stone-700",
          )}
          title={t("feedback.alreadySubmitted") || "Feedback submitted"}
        >
          {submittedFeedback === "up" ? (
            <ThumbsUp size={12} className="fill-current" />
          ) : (
            <ThumbsDown size={12} className="fill-current" />
          )}
        </span>
      </div>
    );
  }

  return (
    <div className={clsx("relative flex items-center gap-1", className)}>
      <button
        onClick={() => handleRatingClick("up")}
        disabled={isSubmitting}
        className={clsx(
          "flex items-center justify-center rounded-md p-1.5 transition-all",
          !isLastMessage && "opacity-0 group-hover:opacity-100",
          "text-stone-400 dark:text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-600 dark:hover:text-stone-300",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        title={t("feedback.positive")}
      >
        <ThumbsUp
          size={16}
          className={clsx(
            selectedRating === "up"
              ? "text-stone-600 dark:text-stone-300"
              : "text-stone-400 dark:text-stone-500",
          )}
        />
      </button>
      <button
        onClick={() => handleRatingClick("down")}
        disabled={isSubmitting}
        className={clsx(
          "flex items-center justify-center rounded-md p-1.5 transition-all",
          !isLastMessage && "opacity-0 group-hover:opacity-100",
          "text-stone-400 dark:text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-600 dark:hover:text-stone-300",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        title={t("feedback.negative")}
      >
        <ThumbsDown
          size={16}
          className={clsx(
            selectedRating === "down"
              ? "text-stone-600 dark:text-stone-300"
              : "text-stone-400 dark:text-stone-500",
          )}
        />
      </button>

      {/* Comment input popup - ChatGPT style */}
      {showCommentInput && (
        <div
          className="absolute bottom-full left-0 z-50 mb-2 inline-block w-72 min-w-0 max-w-md rounded-xl border border-stone-200 bg-white p-4 shadow-xl dark:border-stone-700 dark:bg-stone-900"
          onKeyDown={handleKeyDown}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "flex h-6 w-6 items-center justify-center rounded-full bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300 text-xs",
                )}
              >
                {selectedRating === "up" ? (
                  <ThumbsUp size={12} />
                ) : (
                  <ThumbsDown size={12} />
                )}
              </span>
              <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
                {selectedRating === "up"
                  ? t("feedback.positive")
                  : t("feedback.negative")}
              </span>
            </div>
            <button
              onClick={handleCancel}
              className="flex h-6 w-6 items-center justify-center rounded-md text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
            >
              <X size={14} />
            </button>
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={
              t("feedback.commentPlaceholder") || "What could be improved?"
            }
            className={clsx(
              "w-full resize-none rounded-lg border border-stone-200 p-3 text-sm",
              "bg-stone-50 dark:border-stone-700 dark:bg-stone-800",
              "text-stone-900 dark:text-stone-100",
              "placeholder:text-stone-400 dark:placeholder:text-stone-500",
              "focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400",
              "transition-colors",
            )}
            rows={3}
          />

          {/* Actions */}
          <div className="mt-3 flex flex-nowrap items-center justify-between gap-2">
            <span className="truncate text-xs text-stone-400">
              {t("feedback.pressEnter") || "⌘+Enter to send"}
            </span>
            <div className="flex shrink-0 gap-2">
              <button
                onClick={handleSkipComment}
                disabled={isSubmitting}
                className={clsx(
                  "whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  "text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {t("common.skip") || "Skip"}
              </button>
              <button
                onClick={handleSubmitFeedback}
                disabled={isSubmitting}
                className={clsx(
                  "flex whitespace-nowrap items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  "bg-stone-900 text-white hover:bg-stone-800 dark:bg-stone-200 dark:text-stone-900 dark:hover:bg-stone-300",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {isSubmitting ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent dark:border-stone-900" />
                ) : (
                  <Send size={14} />
                )}
                {t("feedback.submit") || "Submit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
