import { useState, useCallback, useEffect, useRef, useId } from "react";
import { Copy, Check, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { copyToClipboard } from "../../utils/clipboard";
import { Button } from "./ui/Button";

export function CopyButton({
  text,
  size = 14,
  className,
  label,
  showLabel = false,
}: {
  text: string | (() => string);
  size?: number;
  className?: string;
  label?: string;
  showLabel?: boolean;
}) {
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

  const handleCopy = useCallback(
    async (event: React.MouseEvent) => {
      event.stopPropagation();
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
        toast.success(t("chat.message.copied"), { id: feedbackId });
        resetTimer.current = setTimeout(() => setCopied(false), 2000);
      } catch {
        if (version !== request.current) return;
        setFailed(true);
        toast.error(t("chat.message.copyFailed"), { id: feedbackId });
      } finally {
        if (version === request.current) setCopying(false);
      }
    },
    [text, copying, t, feedbackId],
  );

  const actionLabel = copied
    ? t("chat.message.copied")
    : label || t("chat.message.copy");
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleCopy}
      disabled={copying || (typeof text === "string" && !text)}
      aria-label={actionLabel}
      aria-description={failed ? t("chat.message.copyFailed") : undefined}
      aria-busy={copying || undefined}
      title={failed ? t("chat.message.copyFailed") : actionLabel}
      className={clsx(
        "copy-button touch-manipulation shrink-0",
        !showLabel && "ui-icon-button",
        className,
      )}
      style={{
        color: copied
          ? "var(--theme-success)"
          : failed
            ? "var(--theme-error)"
            : undefined,
      }}
      leftIcon={
        copied ? (
          <Check size={size} aria-hidden="true" />
        ) : failed ? (
          <AlertCircle size={size} aria-hidden="true" />
        ) : (
          <Copy size={size} aria-hidden="true" />
        )
      }
    >
      {showLabel
        ? t(copied ? "chat.message.copied" : "chat.message.copy")
        : undefined}
    </Button>
  );
}
