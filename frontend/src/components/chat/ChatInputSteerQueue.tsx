import { InteractiveIcon } from "../common/InteractiveIcon";
import {
  AlertCircle,
  CornerDownRight,
  ListEnd,
  Pencil,
  Pause,
  Play,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SteerItem } from "../../utils/mergeSteers";

interface ChatInputSteerQueueProps {
  items: SteerItem[];
  paused?: boolean;
  pauseReason?: "interrupted" | "delivery";
  resuming?: boolean;
  onResume?: () => void;
  onCancel?: (content: string, messageId?: string) => void;
  onEdit?: (
    content: string,
    messageId: string,
    attachments?: SteerItem["attachments"],
  ) => void;
  onGuide?: (
    content: string,
    attachments?: SteerItem["attachments"],
    messageId?: string,
  ) => void;
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
    <div className="composer-queue-row flex min-w-0 items-center gap-2">
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
              onGuide(item.content, item.attachments, item.id);
            }}
            className={`${actionClass} composer-queue-guide px-3`}
            aria-label={t("chat.queueGuide")}
            title={t("chat.queueGuideHint")}
          >
            <InteractiveIcon>
              <CornerDownRight size={14} />
            </InteractiveIcon>
            <span className="composer-queue-guide-label">
              {t("chat.queueGuide")}
            </span>
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
  paused,
  pauseReason,
  resuming,
  onResume,
  ...actions
}: ChatInputSteerQueueProps) {
  const { t } = useTranslation();
  if (items.length === 0) return null;

  return (
    <div
      className="composer-queue text-theme-text-secondary"
      aria-label={t("chat.steerQueue")}
    >
      {paused && (
        <div className="composer-queue-pause flex min-w-0 items-center gap-2">
          <Pause size={14} aria-hidden="true" className="shrink-0 opacity-60" />
          <span role="status" className="min-w-0 flex-1 text-12">
            {t(
              pauseReason === "delivery"
                ? "chat.queuePausedAfterFailure"
                : "chat.queuePausedByStop",
            )}
          </span>
          <button
            type="button"
            className={`${actionClass} px-2`}
            onClick={onResume}
            disabled={resuming || !onResume}
            aria-label={t("chat.queueResume")}
          >
            <Play size={14} aria-hidden="true" />
            {t("chat.queueResume")}
          </button>
        </div>
      )}
      {items.map((item) => (
        <QueueRow key={item.id} item={item} {...actions} />
      ))}
    </div>
  );
}
