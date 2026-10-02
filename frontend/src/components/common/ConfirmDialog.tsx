import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Dialog } from "./Dialog";
import { Button } from "./ui/Button";

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: "danger" | "warning" | "info";
  loading?: boolean;
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmText,
  cancelText,
  onConfirm,
  onCancel,
  variant = "danger",
  loading = false,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const actionClass =
    "min-w-0 max-w-full flex-auto sm:flex-none !min-h-11 sm:!min-h-9 [@media(pointer:coarse)]:!min-h-11 [&>span]:!whitespace-normal";
  const iconColor =
    variant === "danger"
      ? "text-red-600 dark:text-red-400"
      : variant === "warning"
        ? "text-theme-warning"
        : "text-theme-primary";
  return (
    <Dialog
      open={isOpen}
      onClose={onCancel}
      title={title}
      icon={
        <AlertTriangle
          size={18}
          className={`shrink-0 ${iconColor}`}
          aria-hidden="true"
        />
      }
      dismissible={!loading}
      footer={
        <>
          <Button className={actionClass} disabled={loading} onClick={onCancel}>
            {cancelText || t("common.cancel")}
          </Button>
          <Button
            className={actionClass}
            variant={variant === "danger" ? "danger" : "primary"}
            loading={loading}
            aria-busy={loading}
            onClick={(event) => {
              event.currentTarget
                .closest<HTMLElement>("[data-modal-surface]")
                ?.focus();
              onConfirm();
            }}
          >
            {confirmText || t("common.confirm")}
          </Button>
        </>
      }
    >
      <p className="whitespace-pre-line text-14 leading-relaxed text-theme-text-secondary [overflow-wrap:anywhere]">
        {message}
      </p>
      {loading && (
        <span role="status" className="sr-only">
          {t("common.loading")}
        </span>
      )}
    </Dialog>
  );
}
