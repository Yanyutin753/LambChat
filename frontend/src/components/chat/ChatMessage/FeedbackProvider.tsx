import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { feedbackApi } from "../../../services/api/feedback";
import type { RatingValue } from "../../../types/feedback";
import type { MessageAttachment } from "../../../types/upload";
import { FeedbackDialog } from "./FeedbackDialog";

interface FeedbackRequest {
  sessionId: string;
  runId?: string;
  rating: RatingValue;
  onFeedbackChange?: (rating: RatingValue | null) => void;
}
const FeedbackContext = createContext<{
  open: (request: FeedbackRequest) => void;
  submitted: Record<string, RatingValue>;
} | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useFeedbackDialog() {
  return useContext(FeedbackContext);
}

/** Keep the draft and upload alive when the virtual message list recycles its opener. */
export function FeedbackProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [request, setRequest] = useState<FeedbackRequest | null>(null);
  const [comment, setComment] = useState("");
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState<Record<string, RatingValue>>({});
  const mounted = useRef(false);
  const submitting = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function open(next: FeedbackRequest) {
    if (request || submitting.current) return;
    setComment("");
    setAttachments([]);
    setError("");
    setRequest(next);
  }
  async function submit() {
    if (!request || submitting.current) return;
    submitting.current = true;
    setIsSubmitting(true);
    setError("");
    try {
      await feedbackApi.submit({
        rating: request.rating,
        comment: comment.trim() || undefined,
        session_id: request.sessionId,
        run_id: request.runId || "",
        attachments: attachments.length
          ? attachments.map(({ id, key, name, type, mimeType, size, url }) => ({
              id,
              key,
              name,
              type,
              mimeType,
              size,
              url,
            }))
          : undefined,
      });
      if (!mounted.current) return;
      setSubmitted((previous) => ({
        ...previous,
        [JSON.stringify([request.sessionId, request.runId])]: request.rating,
      }));
      request.onFeedbackChange?.(request.rating);
      setRequest(null);
      toast.success(t("feedback.submitSuccess"));
    } catch (cause) {
      if (mounted.current)
        setError(
          cause instanceof Error ? cause.message : t("feedback.submitFailed"),
        );
    } finally {
      submitting.current = false;
      if (mounted.current) setIsSubmitting(false);
    }
  }
  return (
    <FeedbackContext.Provider value={{ open, submitted }}>
      {children}
      {request && (
        <FeedbackDialog
          isOpen
          onClose={() => {
            if (!submitting.current) setRequest(null);
          }}
          rating={request.rating}
          comment={comment}
          onCommentChange={setComment}
          onSubmit={submit}
          onSkip={submit}
          isSubmitting={isSubmitting}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          error={error}
        />
      )}
    </FeedbackContext.Provider>
  );
}
