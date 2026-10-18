import { InteractiveIcon } from "../common/InteractiveIcon";
import {
  AlertCircle,
  CornerDownRight,
  ListEnd,
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
  "flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg text-12 hover:bg-[var(--theme-bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] disabled:opacity-50";

function QueueRow({
  item,
  onCancel,
  onEdit,
  onGuide,
}: Omit<ChatInputSteerQueueProps, "items"> & { item: SteerItem }) {
  const { t } = useTranslation();
  const failed = item.status === "failed";
  const deferred = item.status === "deferred" || item.deferred;
  const preview =
    item.content || item.attachments?.map((file) => file.name).join(", ");

  return (
    <div className="flex min-w-0 items-center gap-2 px-3 py-1.5 sm:px-4">
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
      <div className="flex shrink-0 items-center gap-1">
        {onGuide && onCancel && deferred && !failed && (
          <button
            type="button"
            onClick={() => {
              onCancel(item.content, item.id);
              onGuide(item.content, item.attachments);
            }}
            className={`${actionClass} px-3`}
            title={t("chat.queueGuideHint")}
          >
            <InteractiveIcon>
              <CornerDownRight size={14} />
            </InteractiveIcon>
            {t("chat.queueGuide")}
          </button>
        )}
        {onCancel && (
          <button
            type="button"
            onClick={() => onCancel(item.content, item.id)}
            className={`${actionClass} w-9`}
            aria-label={t("chat.queueDelete")}
            title={t("chat.queueDelete")}
          >
            <InteractiveIcon>
              <Trash2 size={14} />
            </InteractiveIcon>
          </button>
        )}
        {onEdit && (
          <button
            type="button"
            data-testid="queue-edit-trigger"
            className={`${actionClass} w-9`}
            aria-label={t("chat.message.queueEdit")}
            title={t("chat.message.queueEdit")}
            onClick={() => onEdit(item.content, item.id, item.attachments)}
          >
            <InteractiveIcon>
              <Pencil size={14} />
            </InteractiveIcon>
          </button>
        )}
      </div>
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
    <div className="chat-content-column" aria-label={t("chat.steerQueue")}>
      <div className="-mb-5 rounded-t-3xl border border-b-0 border-[var(--theme-border)] bg-[var(--theme-bg-card)] pb-5 text-[var(--theme-text-secondary)]">
        {items.map((item) => (
          <QueueRow key={item.id} item={item} {...actions} />
        ))}
      </div>
    </div>
  );
}
