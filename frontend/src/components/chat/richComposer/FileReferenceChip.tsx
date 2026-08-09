import {
  AlertCircle,
  Check,
  FileText,
  LoaderCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FileReferenceDescriptor } from "./composerTypes";

const STATUS_LABELS = {
  uploading: "uploading",
  ready: "ready",
  failed: "failed",
} as const;

interface FileReferenceChipProps extends FileReferenceDescriptor {
  onRemove: () => void;
  onRetry?: () => void;
}

export function FileReferenceChip({
  fileName,
  status,
  onRemove,
  onRetry,
}: FileReferenceChipProps) {
  const { t } = useTranslation();
  const StatusIcon =
    status === "uploading"
      ? LoaderCircle
      : status === "failed"
        ? AlertCircle
        : Check;

  return (
    <span
      className={`composer-reference-chip composer-file-reference composer-file-reference--${status}`}
      role="button"
      tabIndex={0}
      aria-label={`File ${fileName}, ${STATUS_LABELS[status]}`}
      contentEditable={false}
    >
      <FileText className="composer-reference-chip__icon" size={15} />
      <span className="composer-reference-chip__label">{fileName}</span>
      <StatusIcon
        className={`composer-reference-chip__status${
          status === "uploading"
            ? " composer-reference-chip__status--spinning"
            : ""
        }`}
        size={13}
        aria-hidden="true"
      />
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
      <button
        type="button"
        className="composer-reference-chip__remove"
        aria-label={`Remove ${fileName}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onRemove();
        }}
      >
        <X size={12} aria-hidden="true" />
      </button>
    </span>
  );
}
