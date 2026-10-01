import { Copy, Check, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useClipboardCopy } from "../../hooks/useClipboardCopy";
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
  const { copied, failed, copying, copy } = useClipboardCopy(text);

  const actionLabel = copied
    ? t("chat.message.copied")
    : label || t("chat.message.copy");
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={(event) => {
        event.stopPropagation();
        void copy();
      }}
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
