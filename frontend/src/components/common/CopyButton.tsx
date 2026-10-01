import { useState, useCallback, useEffect, useRef } from "react";
import { Copy, Check, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { copyToClipboard } from "../../utils/clipboard";
import { IconButton } from "./ui/IconButton";

export function CopyButton({
  text,
  size = 14,
  className,
  label,
}: {
  text: string;
  size?: number;
  className?: string;
  label?: string;
}) {
  const { t } = useTranslation();
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
        await copyToClipboard(text);
        if (version !== request.current) return;
        setCopied(true);
        toast.success(t("chat.message.copied"));
        resetTimer.current = setTimeout(() => setCopied(false), 2000);
      } catch {
        if (version !== request.current) return;
        setFailed(true);
        toast.error(t("chat.message.copyFailed"));
      } finally {
        if (version === request.current) setCopying(false);
      }
    },
    [text, copying, t],
  );

  const actionLabel = copied
    ? t("chat.message.copied")
    : label || t("chat.message.copy");
  return (
    <IconButton
      size="sm"
      onClick={handleCopy}
      disabled={copying || !text}
      aria-label={actionLabel}
      aria-description={failed ? t("chat.message.copyFailed") : undefined}
      aria-busy={copying || undefined}
      title={failed ? t("chat.message.copyFailed") : actionLabel}
      className={clsx("copy-button touch-manipulation shrink-0", className)}
      style={{
        color: copied
          ? "var(--theme-success)"
          : failed
            ? "var(--theme-error)"
            : undefined,
      }}
      icon={
        copied ? (
          <Check size={size} aria-hidden="true" />
        ) : failed ? (
          <AlertCircle size={size} aria-hidden="true" />
        ) : (
          <Copy size={size} aria-hidden="true" />
        )
      }
    />
  );
}
