import { AlertCircle, LoaderCircle, Paperclip, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FileReferenceDescriptor } from "./composerTypes";

const STATUS_LABELS = {
  uploading: "uploading",
  ready: "ready",
  failed: "failed",
} as const;

interface FileReferenceChipProps extends FileReferenceDescriptor {
  onRetry?: () => void;
  onClick?: () => void;
  readOnly?: boolean;
}

export function FileReferenceChip({
  fileName,
  referenceNumber = 1,
  status,
  onRetry,
  onClick,
  readOnly = false,
}: FileReferenceChipProps) {
  const { t } = useTranslation();
  const displayLabel = t("fileUpload.composerReferenceNumber", {
    index: referenceNumber,
    defaultValue: `Reference ${referenceNumber}`,
  });
  const StatusIcon =
    status === "uploading"
      ? LoaderCircle
      : status === "failed"
        ? AlertCircle
        : null;

  return (
    <span
      className={`skill-chip-node composer-reference-chip composer-file-reference composer-file-reference--${status}`}
      role={!readOnly || onClick ? "button" : undefined}
      tabIndex={!readOnly || onClick ? 0 : undefined}
      aria-label={`File ${fileName}, ${STATUS_LABELS[status]}`}
      title={fileName}
      contentEditable={false}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <Paperclip className="composer-reference-chip__icon" size="1em" />
      <span className="skill-chip-node-name composer-reference-chip__label font-serif">
        {displayLabel}
      </span>
      {!readOnly && StatusIcon ? (
        <StatusIcon
          className={`composer-reference-chip__status${
            status === "uploading"
              ? " composer-reference-chip__status--spinning"
              : ""
          }`}
          size={13}
          aria-hidden="true"
        />
      ) : null}
      {status === "failed" && onRetry ? (
        <button
          type="button"
          className="composer-reference-chip__retry"
          aria-label={t("fileUpload.composerRetry", "Retry upload")}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onRetry();
          }}
        >
          <RotateCcw size={12} aria-hidden="true" />
          <span>{t("fileUpload.composerRetry", "Retry")}</span>
        </button>
      ) : null}
    </span>
  );
}
