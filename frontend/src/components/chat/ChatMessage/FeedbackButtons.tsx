import { useEffect, useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { clsx } from "clsx";
import toast from "react-hot-toast";
import { feedbackApi } from "../../../services/api/feedback";
import type { RatingValue } from "../../../types/feedback";
import { useTranslation } from "react-i18next";
import { FeedbackDialog } from "./FeedbackDialog";

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
  const [showDialog, setShowDialog] = useState(false);
  const [comment, setComment] = useState("");
  const [submittedFeedback, setSubmittedFeedback] =
    useState<RatingValue | null>(externalFeedback || null);

  useEffect(() => {
    if (externalFeedback) {
      setSubmittedFeedback(externalFeedback);
    }
  }, [externalFeedback]);

  function handleRatingClick(rating: RatingValue) {
    if (isSubmitting || submittedFeedback) return;
    setSelectedRating(rating);
    setComment("");
    setShowDialog(true);
  }

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
      setShowDialog(false);
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

  function handleClose() {
    setShowDialog(false);
    setSelectedRating(null);
    setComment("");
  }

  function handleSkip() {
    handleSubmitFeedback();
  }

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
    <>
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
      </div>

      {selectedRating && (
        <FeedbackDialog
          isOpen={showDialog}
          onClose={handleClose}
          rating={selectedRating}
          comment={comment}
          onCommentChange={setComment}
          onSubmit={handleSubmitFeedback}
          onSkip={handleSkip}
          isSubmitting={isSubmitting}
        />
      )}
    </>
  );
}
