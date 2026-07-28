import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ArrowUp, Minimize2, Square, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface ChatInputExpandedComposerProps {
  open: boolean;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  canSubmit?: boolean;
  isLoading?: boolean;
  hasUploadingAttachment?: boolean;
  onChange: (value: string) => void;
  onCollapse: () => void;
  onSend?: (event: React.FormEvent | React.MouseEvent) => void;
  onStop?: () => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onPaste?: (event: React.ClipboardEvent<HTMLTextAreaElement>) => void;
}

export function ChatInputExpandedComposer({
  open,
  value,
  placeholder,
  disabled,
  canSubmit = false,
  isLoading = false,
  hasUploadingAttachment = false,
  onChange,
  onCollapse,
  onSend,
  onStop,
  onKeyDown,
  onPaste,
}: ChatInputExpandedComposerProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dragHandleRef = useRef<HTMLDivElement>(null);
  const swipeRef = useSwipeToClose({
    onClose: onCollapse,
    enabled: open,
    dragHandleRef,
  });
  useBodyScrollLock(open);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
      textarea.scrollTop = textarea.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCollapse();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCollapse]);

  if (!open) return null;

  return createPortal(
    <>
      <div
        className="fixed inset-0 z-[279] bg-black/45"
        onClick={onCollapse}
        aria-hidden="true"
      />
      <div className="safe-area-viewport-padding fixed inset-0 z-[280] flex items-end sm:items-center sm:justify-center p-0 sm:p-8 md:p-10 sm:pointer-events-none">
        <div
          ref={(node) => {
            swipeRef.current = node;
          }}
          className="relative z-10 flex h-[min(92dvh,920px)] w-full max-w-4xl flex-col overflow-hidden rounded-t-2xl border shadow-2xl sm:h-[min(85vh,720px)] sm:rounded-2xl sm:pointer-events-auto animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
          }}
          role="dialog"
          aria-modal="true"
          aria-label={t("chat.expandedComposerTitle", "展开编辑")}
          onClick={(event) => event.stopPropagation()}
        >
          <div
            ref={dragHandleRef}
            className="flex shrink-0 justify-center pt-3 pb-1 sm:hidden"
            aria-hidden="true"
          >
            <div
              className="h-1 w-9 rounded-full"
              style={{ backgroundColor: "var(--theme-border)" }}
            />
          </div>

          <div
            className="flex items-center justify-between gap-3 border-b px-4 sm:px-6 py-3 sm:py-4"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <div className="min-w-0 pr-3">
              <div className="text-sm font-medium text-[var(--theme-text)]">
                {t("chat.expandedComposerTitle", "展开编辑")}
              </div>
              <div className="mt-1 hidden text-xs leading-5 text-[var(--theme-text-secondary)] sm:block">
                {t(
                  "chat.expandedComposerHint",
                  "适合编辑长提示词。Esc 收起，发送快捷键保持不变。",
                )}
              </div>
              <div className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)] sm:hidden">
                {t(
                  "chat.expandedComposerHintMobile",
                  "适合编辑长提示词。下拉或点收起可返回。",
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={onCollapse}
              className="inline-flex shrink-0 items-center justify-center rounded-lg p-2 transition-colors hover:bg-[color-mix(in_srgb,var(--theme-text)_8%,transparent)]"
              style={{ color: "var(--theme-text-secondary)" }}
              title={t("chat.collapseComposer", "收起")}
              aria-label={t("chat.collapseComposer", "收起")}
            >
              <X size={18} className="sm:hidden" />
              <Minimize2 size={16} className="hidden sm:block" />
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col p-3 sm:p-5 pb-2 sm:pb-3">
            <textarea
              ref={textareaRef}
              value={value}
              disabled={disabled}
              placeholder={placeholder}
              onChange={(event) => {
                onChange(event.target.value);
                // Keep the latest typed content visible while appending.
                requestAnimationFrame(() => {
                  const textarea = textareaRef.current;
                  if (!textarea) return;
                  if (textarea.selectionEnd >= textarea.value.length) {
                    textarea.scrollTop = textarea.scrollHeight;
                  }
                });
              }}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              className="min-h-0 flex-1 resize-none rounded-xl border bg-transparent px-3 sm:px-4 py-3 sm:py-3.5 text-[15px] sm:text-sm leading-6 outline-none"
              style={{
                color: "var(--theme-text)",
                borderColor:
                  "color-mix(in srgb, var(--theme-border) 80%, transparent)",
                backgroundColor:
                  "color-mix(in srgb, var(--theme-bg) 55%, transparent)",
              }}
            />
          </div>

          <div
            className="flex shrink-0 items-center justify-between gap-3 border-t px-4 sm:px-5 py-3"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <button
              type="button"
              onClick={onCollapse}
              className="inline-flex h-10 items-center gap-1.5 rounded-xl px-3.5 text-sm font-medium transition-colors hover:bg-[color-mix(in_srgb,var(--theme-text)_8%,transparent)]"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              <Minimize2 size={15} />
              {t("chat.collapseComposer", "收起")}
            </button>

            {isLoading ? (
              <button
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  onStop?.();
                }}
                className="inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium transition-all duration-200 hover:scale-[1.02] active:scale-95"
                style={{
                  border:
                    "1px solid color-mix(in srgb, var(--theme-primary) 40%, transparent)",
                  background:
                    "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
                  color: "var(--theme-primary)",
                }}
                title={t("chat.stop")}
              >
                <Square size={14} fill="currentColor" />
                {t("chat.stop")}
              </button>
            ) : (
              <button
                type="button"
                disabled={!canSubmit || disabled}
                onClick={(event) => {
                  event.preventDefault();
                  if (!canSubmit || disabled) return;
                  onSend?.(event);
                }}
                className="inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium transition-all duration-200"
                style={
                  canSubmit && !disabled
                    ? {
                        backgroundColor: "var(--theme-primary)",
                        border: "1px solid var(--theme-primary)",
                        color: "var(--theme-bg-card)",
                      }
                    : {
                        backgroundColor: "transparent",
                        border: "1px solid var(--theme-border)",
                        color: "var(--theme-text-secondary)",
                      }
                }
                title={
                  hasUploadingAttachment
                    ? t("chat.waitingForUpload", "请等待文件上传完成")
                    : t("chat.send")
                }
              >
                <ArrowUp size={16} />
                {t("chat.send")}
              </button>
            )}
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
