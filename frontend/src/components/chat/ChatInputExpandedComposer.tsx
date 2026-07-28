import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Minimize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";

interface ChatInputExpandedComposerProps {
  open: boolean;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onCollapse: () => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onPaste?: (event: React.ClipboardEvent<HTMLTextAreaElement>) => void;
}

export function ChatInputExpandedComposer({
  open,
  value,
  placeholder,
  disabled,
  onChange,
  onCollapse,
  onKeyDown,
  onPaste,
}: ChatInputExpandedComposerProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
    <div
      className="safe-area-viewport-padding fixed inset-0 z-[280] flex items-center justify-center p-5 sm:p-8 md:p-10"
      style={{ backgroundColor: "color-mix(in srgb, black 45%, transparent)" }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCollapse();
      }}
    >
      <div
        className="flex h-[min(85vh,720px)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
        }}
        role="dialog"
        aria-modal="true"
        aria-label={t("chat.expandedComposerTitle", "展开编辑")}
      >
        <div
          className="flex items-center justify-between gap-3 border-b px-5 sm:px-6 py-4"
          style={{ borderColor: "var(--theme-border)" }}
        >
          <div className="min-w-0 pr-3">
            <div className="text-sm font-medium text-[var(--theme-text)]">
              {t("chat.expandedComposerTitle", "展开编辑")}
            </div>
            <div className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)]">
              {t(
                "chat.expandedComposerHint",
                "适合编辑长提示词。Esc 收起，发送快捷键保持不变。",
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onCollapse}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors hover:bg-[color-mix(in_srgb,var(--theme-text)_8%,transparent)]"
            style={{ color: "var(--theme-text-secondary)" }}
            title={t("chat.collapseComposer", "收起")}
          >
            <Minimize2 size={14} />
            {t("chat.collapseComposer", "收起")}
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
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
            className="min-h-0 flex-1 resize-none rounded-xl border bg-transparent px-4 py-3.5 text-sm leading-6 outline-none"
            style={{
              color: "var(--theme-text)",
              borderColor:
                "color-mix(in srgb, var(--theme-border) 80%, transparent)",
              backgroundColor:
                "color-mix(in srgb, var(--theme-bg) 55%, transparent)",
            }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
