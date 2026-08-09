import { AlertCircle, Check, FileText, LoaderCircle, X } from "lucide-react";
import type { FileReferenceDescriptor } from "./composerTypes";

const STATUS_LABELS = {
  uploading: "uploading",
  ready: "ready",
  failed: "failed",
} as const;

interface FileReferenceChipProps extends FileReferenceDescriptor {
  onRemove: () => void;
}

export function FileReferenceChip({
  fileName,
  status,
  onRemove,
}: FileReferenceChipProps) {
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
