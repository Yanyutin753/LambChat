import { useState, useCallback, useEffect, useRef, useId } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { copyToClipboard } from "../utils/clipboard";

export function useClipboardCopy(
  text: string | (() => string),
  successMessage?: string,
) {
  const { t } = useTranslation();
  const feedbackId = useId();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copying, setCopying] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const request = useRef(0);

  useEffect(() => {
    const version = request.current;
    setCopied(false);
    setFailed(false);
    setCopying(false);
    return () => {
      request.current = version + 1;
      clearTimeout(resetTimer.current);
    };
  }, [text]);

  const copy = useCallback(async () => {
    if (!text || copying) return;
    const version = request.current;
    clearTimeout(resetTimer.current);
    setCopied(false);
    setFailed(false);
    setCopying(true);
    try {
      const content = typeof text === "function" ? text() : text;
      if (!content) return;
      await copyToClipboard(content);
      if (version !== request.current) return;
      setCopied(true);
      toast.success(successMessage || t("chat.message.copied"), {
        id: feedbackId,
      });
      resetTimer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      if (version !== request.current) return;
      setFailed(true);
      toast.error(t("chat.message.copyFailed"), { id: feedbackId });
    } finally {
      if (version === request.current) setCopying(false);
    }
  }, [text, copying, t, feedbackId, successMessage]);

  return { copied, failed, copying, copy };
}
