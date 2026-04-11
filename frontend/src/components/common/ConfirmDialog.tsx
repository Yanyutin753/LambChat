import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

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
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // Use default values from translations if not provided
  const confirmLabel = confirmText || t("common.confirm");
  const cancelLabel = cancelText || t("common.cancel");

  useEffect(() => {
    if (isOpen) {
      // Focus the confirm button when dialog opens
      confirmButtonRef.current?.focus();
      // Prevent body scroll
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape" && !loading) {
        onCancel();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel, loading]);

  if (!isOpen) return null;

  const variantStyles = {
    danger: {
      icon: "text-red-500 dark:text-red-400",
      confirmButton:
        "bg-red-500 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700 text-white",
    },
    warning: {
      icon: "text-amber-500 dark:text-amber-400",
      confirmButton:
        "bg-amber-500 hover:bg-amber-600 dark:bg-amber-600 dark:hover:bg-amber-700 text-white",
    },
    info: {
      icon: "text-[var(--theme-primary)]",
      confirmButton: "btn-primary shadow-sm",
    },
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={loading ? undefined : onCancel}
      />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-sm mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Content */}
        <div className="p-5">
          <div className="flex items-start gap-3">
            <div
              className={`flex-shrink-0 mt-0.5 ${variantStyles[variant].icon}`}
            >
              <AlertTriangle size={22} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
                {title}
              </h3>
              <p className="mt-1.5 text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                {message}
              </p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors inline-flex items-center justify-center gap-2 disabled:opacity-70 ${variantStyles[variant].confirmButton}`}
          >
            {loading && (
              <svg
                className="animate-spin h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            )}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
