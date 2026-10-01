import { ModalSurface } from "./ModalSurface";
import { useEffect, useRef } from "react";

import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LoadingSpinner } from "./LoadingSpinner";

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
      confirmButtonRef.current?.focus();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const variantStyles = {
    danger: {
      icon: "text-red-500 dark:text-red-400",
      confirmButton:
        "bg-red-500 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700 text-white",
    },
    warning: {
      icon: "text-theme-warning",
      confirmButton: "btn-primary",
    },
    info: {
      icon: "text-[var(--theme-primary)]",
      confirmButton: "btn-primary shadow-sm",
    },
  };

  return (
    <ModalSurface open={isOpen} onClose={onCancel} dismissible={!loading}>
      <div className="relative z-10 w-full max-w-sm mx-4 bg-theme-bg-card dark:bg-stone-800 rounded-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Content */}
        <div className="p-5">
          <div className="flex items-start gap-3">
            <div
              className={`flex-shrink-0 mt-0.5 ${variantStyles[variant].icon}`}
            >
              <AlertTriangle size={22} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-16 font-semibold font-sans text-stone-900 dark:text-stone-100">
                {title}
              </h3>
              <p className="mt-1.5 text-14 text-stone-600 dark:text-stone-400 leading-relaxed">
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
            className="px-4 py-2 text-14 font-medium text-stone-700 dark:text-stone-300 bg-theme-bg-card dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-14 font-medium rounded-lg transition-colors inline-flex items-center justify-center gap-2 disabled:opacity-70 ${variantStyles[variant].confirmButton}`}
          >
            {loading ? (
              <span className="inline-flex h-4 w-4 items-center justify-center">
                <LoadingSpinner size="sm" color="text-current" />
              </span>
            ) : (
              <AlertTriangle size={16} className="shrink-0" />
            )}
            {confirmLabel}
          </button>
        </div>
      </div>
    </ModalSurface>
  );
}
