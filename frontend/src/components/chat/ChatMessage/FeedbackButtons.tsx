import { useEffect, useRef, useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { clsx } from "clsx";
import toast from "react-hot-toast";
import { feedbackApi } from "../../../services/api/feedback";
import type { RatingValue } from "../../../types/feedback";
import type { MessageAttachment } from "../../../types/upload";
import { useTranslation } from "react-i18next";
import { Tooltip } from "../../common/Tooltip";
import { FeedbackDialog } from "./FeedbackDialog";

interface FeedbackButtonsProps {
  sessionId: string;
  runId?: string;
  currentFeedback?: RatingValue | null;
  onFeedbackChange?: (feedback: RatingValue | null) => void;
  className?: string;
}

export function FeedbackButtons({
  sessionId,
  runId,
  currentFeedback: externalFeedback,
  onFeedbackChange,
  className,
}: FeedbackButtonsProps) {
  const { t } = useTranslation();
  const [selectedRating, setSelectedRating] = useState<RatingValue | null>(
    null,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [comment, setComment] = useState("");
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const [submitError, setSubmitError] = useState("");
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
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
    setAttachments([]);
    setSubmitError("");
    setShowDialog(true);
  }

  async function handleSubmitFeedback() {
    if (isSubmitting || !selectedRating) return;

    setIsSubmitting(true);
    setSubmitError("");
    try {
      await feedbackApi.submit({
        rating: selectedRating,
        comment: comment.trim() || undefined,
        session_id: sessionId,
        run_id: runId || "",
        attachments:
          attachments.length > 0
            ? attachments.map((a) => ({
                id: a.id,
                key: a.key,
                name: a.name,
                type: a.type,
                mimeType: a.mimeType,
                size: a.size,
                url: a.url,
              }))
            : undefined,
      });
      if (!mounted.current) return;
      setSubmittedFeedback(selectedRating);
      onFeedbackChange?.(selectedRating);
      setShowDialog(false);
      toast.success(t("feedback.submitSuccess") || "Feedback submitted");
    } catch (error) {
      if (!mounted.current) return;
      setSubmitError(
        error instanceof Error ? error.message : t("feedback.submitFailed"),
      );
    } finally {
      if (mounted.current) setIsSubmitting(false);
    }
  }

  function handleClose() {
    if (isSubmitting) return;
    setShowDialog(false);
    setSelectedRating(null);
    setComment("");
    setAttachments([]);
    setSubmitError("");
  }

  function handleSkip() {
    handleSubmitFeedback();
  }

  if (submittedFeedback) {
    return (
      <div className={clsx("flex items-center", className)}>
        <Tooltip
          content={t("feedback.alreadySubmitted") || "Feedback submitted"}
        >
          <span
            className={clsx(
              "flex items-center justify-center rounded-md p-1.5 transition-all",
              submittedFeedback === "up"
                ? "text-stone-600 dark:text-stone-300"
                : "text-stone-600 dark:text-stone-300",
            )}
            aria-label={t("feedback.alreadySubmitted") || "Feedback submitted"}
          >
            {submittedFeedback === "up" ? (
              <ThumbsUp size={16} className="fill-current" />
            ) : (
              <ThumbsDown size={16} className="fill-current" />
            )}
          </span>
        </Tooltip>
      </div>
    );
  }

  return (
    <>
      <div className={clsx("relative flex items-center gap-1", className)}>
        <Tooltip content={t("feedback.positive")}>
          <button
            onClick={() => handleRatingClick("up")}
            disabled={isSubmitting}
            aria-label={t("feedback.positive")}
            className={clsx(
              "flex items-center justify-center rounded-md p-1.5 transition-all",
              "text-stone-400 dark:text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-600 dark:hover:text-stone-300",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
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
        </Tooltip>
        <Tooltip content={t("feedback.negative")}>
          <button
            onClick={() => handleRatingClick("down")}
            disabled={isSubmitting}
            aria-label={t("feedback.negative")}
            className={clsx(
              "flex items-center justify-center rounded-md p-1.5 transition-all",
              "text-stone-400 dark:text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 hover:text-stone-600 dark:hover:text-stone-300",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
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
        </Tooltip>
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
          error={submitError}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
        />
      )}
    </>
  );
}
