import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Trash2, FolderInput, X } from "lucide-react";
import { LoadingSpinner } from "./LoadingSpinner";

interface DeleteProjectDialogProps {
  isOpen: boolean;
  projectName: string;
  onConfirm: (deleteSessions: boolean) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function DeleteProjectDialog({
  isOpen,
  projectName,
  onConfirm,
  onCancel,
  loading = false,
}: DeleteProjectDialogProps) {
  const { t } = useTranslation();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isOpen) {
      cancelRef.current?.focus();
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
      if (!isOpen || loading) return;
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel, loading]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={loading ? undefined : onCancel}
      />

      <div
        className="relative z-10 w-full max-w-md mx-4 rounded-xl shadow-xl border overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="flex items-center gap-2">
            <Trash2
              size={15}
              strokeWidth={1.8}
              className="text-red-500 dark:text-red-400"
            />
            <span
              className="text-sm font-medium"
              style={{ color: "var(--theme-text)" }}
            >
              {t("sidebar.deleteProjectTitle")}
            </span>
          </div>
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex items-center justify-center w-6 h-6 rounded-md transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
          >
            <X size={14} strokeWidth={2} />
          </button>
        </div>

        {/* Description */}
        <div className="px-5 py-4">
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {t("sidebar.deleteProjectDesc", { name: projectName })}
          </p>
        </div>

        {/* Options */}
        <div className="px-4 pb-4 space-y-1.5">
          <button
            onClick={() => onConfirm(true)}
            disabled={loading}
            className="flex w-full items-center gap-3 px-4 py-3 rounded-lg text-left text-sm transition-colors text-red-500/80 hover:text-red-500 dark:text-red-400/80 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed"
          >
            <Trash2 size={16} strokeWidth={1.8} className="shrink-0" />
            <div className="min-w-0">
              <span className="block">
                {t("sidebar.deleteProjectAndSessions")}
              </span>
              <span
                className="block text-xs mt-0.5 opacity-60"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t(
                  "sidebar.deleteProjectAndSessionsHint",
                  "包含项目下所有会话",
                )}
              </span>
            </div>
            {loading && (
              <LoadingSpinner size="sm" color="text-current ml-auto" />
            )}
          </button>
          <button
            onClick={() => onConfirm(false)}
            disabled={loading}
            className="flex w-full items-center gap-3 px-4 py-3 rounded-lg text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed"
          >
            <FolderInput size={16} strokeWidth={1.8} className="shrink-0" />
            <div className="min-w-0">
              <span className="block">
                {t("sidebar.deleteProjectKeepSessions")}
              </span>
              <span className="block text-xs mt-0.5 opacity-60">
                {t("sidebar.deleteProjectKeepSessionsHint", "会话移至未分类")}
              </span>
            </div>
            {loading && (
              <LoadingSpinner size="sm" color="text-current ml-auto" />
            )}
          </button>
        </div>

        {/* Footer */}
        <div
          className="flex justify-end px-5 py-3 border-t"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <button
            ref={cancelRef}
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
