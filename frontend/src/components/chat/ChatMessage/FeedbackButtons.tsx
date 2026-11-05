import { InteractiveIcon } from "../../common/InteractiveIcon";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { clsx } from "clsx";
import type { RatingValue } from "../../../types/feedback";
import { useTranslation } from "react-i18next";
import { Tooltip } from "../../common/Tooltip";

import { useFeedbackDialog } from "./FeedbackProvider";

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
  const feedback = useFeedbackDialog();
  const submittedFeedback =
    externalFeedback || feedback?.submitted[JSON.stringify([sessionId, runId])];
  function handleRatingClick(rating: RatingValue) {
    if (submittedFeedback) return;
    feedback?.open({ sessionId, runId, rating, onFeedbackChange });
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
                ? "text-theme-text-secondary dark:text-stone-300"
                : "text-theme-text-secondary dark:text-stone-300",
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
    <div className={clsx("relative flex items-center gap-1", className)}>
      <Tooltip content={t("feedback.positive")}>
        <button
          type="button"
          onClick={() => handleRatingClick("up")}
          disabled={!feedback}
          aria-label={t("feedback.positive")}
          className={clsx(
            "flex items-center justify-center rounded-md p-1.5 transition-all",
            "text-theme-text-tertiary dark:text-stone-500 hover:bg-theme-bg-hover dark:hover:bg-theme-bg-hover hover:text-theme-text-secondary dark:hover:text-stone-300",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          <InteractiveIcon>
            <ThumbsUp size={16} />
          </InteractiveIcon>
        </button>
      </Tooltip>
      <Tooltip content={t("feedback.negative")}>
        <button
          type="button"
          onClick={() => handleRatingClick("down")}
          disabled={!feedback}
          aria-label={t("feedback.negative")}
          className={clsx(
            "flex items-center justify-center rounded-md p-1.5 transition-all",
            "text-theme-text-tertiary dark:text-stone-500 hover:bg-theme-bg-hover dark:hover:bg-theme-bg-hover hover:text-theme-text-secondary dark:hover:text-stone-300",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          <InteractiveIcon>
            <ThumbsDown size={16} />
          </InteractiveIcon>
        </button>
      </Tooltip>
    </div>
  );
}
