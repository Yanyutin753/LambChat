import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CornerDownRight,
  ListEnd,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SteerItem } from "../../utils/mergeSteers";

interface ChatInputSteerQueueProps {
  items: SteerItem[];
  onCancel?: (content: string, messageId?: string) => void;
  onEdit?: (
    content: string,
    messageId: string,
    attachments?: SteerItem["attachments"],
  ) => void;
  onGuide?: (content: string, attachments?: SteerItem["attachments"]) => void;
}

const actionClass =
  "flex min-h-9 min-w-9 shrink-0 items-center justify-center gap-1.5 rounded-lg px-2 text-12 hover:bg-[var(--theme-bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] disabled:opacity-50";

function QueueRow({
  item,
  onCancel,
  onEdit,
  onGuide,
}: Omit<ChatInputSteerQueueProps, "items"> & { item: SteerItem }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const failed = item.status === "failed";
  const deferred = item.status === "deferred" || item.deferred;
  const preview =
    item.content || item.attachments?.map((file) => file.name).join(", ");

  useEffect(() => {
    if (!open) return;
    editRef.current?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  return (
    <div className="flex min-w-0 items-center gap-1 px-2 py-1 sm:gap-2 sm:px-3">
      {failed ? (
        <AlertCircle size={16} className="shrink-0 text-[var(--theme-error)]" />
      ) : (
        <ListEnd size={16} className="shrink-0 opacity-60" />
      )}
      <span
        className="min-w-0 flex-1 truncate text-14 text-[var(--theme-text)]"
        title={preview}
      >
        {preview}
      </span>
      {failed ? (
        <span
          role="status"
          className="max-w-[30%] text-12 text-[var(--theme-error)]"
        >
          {t("chat.steerFailedRetry")}
        </span>
      ) : deferred ? null : (
        <span role="status" className="max-w-[30%] text-12">
          {t("chat.steerQueued")}
        </span>
      )}
      {onGuide && onCancel && deferred && !failed && (
        <button
          type="button"
          onClick={() => {
            onCancel(item.content, item.id);
            onGuide(item.content, item.attachments);
          }}
          className={actionClass}
          title={t("chat.queueGuideHint")}
        >
          <CornerDownRight size={14} />
          {t("chat.queueGuide")}
        </button>
      )}
      {onCancel && (
        <button
          type="button"
          onClick={() => onCancel(item.content, item.id)}
          className={actionClass}
          aria-label={t("chat.queueDelete")}
          title={t("chat.queueDelete")}
        >
          <Trash2 size={14} />
        </button>
      )}
      {onEdit && (
        <div
          ref={menuRef}
          className="relative shrink-0"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget))
              setOpen(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              triggerRef.current?.focus();
            }
            if (
              open &&
              ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)
            ) {
              event.preventDefault();
              editRef.current?.focus();
            }
          }}
        >
          <button
            ref={triggerRef}
            type="button"
            className={actionClass}
            aria-label={t("chat.queueMore")}
            title={t("chat.queueMore")}
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <MoreHorizontal size={16} />
          </button>
          {open && (
            <div
              role="menu"
              aria-label={t("chat.queueMore")}
              className="absolute bottom-full right-0 z-50 mb-1 min-w-40 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] p-1 shadow-lg"
            >
              <button
                ref={editRef}
                type="button"
                role="menuitem"
                data-testid="queue-edit-trigger"
                className={`${actionClass} w-full justify-start whitespace-nowrap`}
                onClick={() => {
                  setOpen(false);
                  onEdit(item.content, item.id, item.attachments);
                }}
              >
                <Pencil size={14} />
                {t("chat.message.queueEdit")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatInputSteerQueue({
  items,
  ...actions
}: ChatInputSteerQueueProps) {
  const { t } = useTranslation();
  if (items.length === 0) return null;

  return (
    <div
      className="mx-auto w-full max-w-4xl px-3 sm:px-5 lg:max-w-5xl xl:max-w-6xl"
      aria-label={t("chat.steerQueue")}
    >
      <div className="-mb-5 rounded-t-3xl border border-b-0 border-[var(--theme-border)] bg-[var(--theme-bg-card)] pb-5 text-[var(--theme-text-secondary)]">
        {items.map((item) => (
          <QueueRow key={item.id} item={item} {...actions} />
        ))}
      </div>
    </div>
  );
}
