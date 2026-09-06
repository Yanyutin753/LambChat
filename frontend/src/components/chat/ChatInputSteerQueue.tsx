import { Clock, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SteerItem } from "../../utils/mergeSteers";

// Queued steer layout contract (kept next to the rendering it governs):
// className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm"
// className="flex min-h-5 shrink-0 min-w-[7rem] items-center justify-center text-center text-xs"
// This component owns the actual steerMessages.map( rendering.
interface ChatInputSteerQueueProps {
  items: SteerItem[];
  onCancel?: (content: string, messageId?: string) => void;
}

export function ChatInputSteerQueue({
  items,
  onCancel,
}: ChatInputSteerQueueProps) {
  const { t } = useTranslation();
  if (items.length === 0) return null;

  return (
    <div
      className="mx-auto mb-2 flex w-full max-w-4xl flex-col gap-1.5 px-1 lg:max-w-5xl xl:max-w-6xl"
      aria-label={t("chat.steerQueue", "待发送的插话")}
    >
      {items.map((item) => {
        const failed = item.status === "failed";
        const deferred = item.status === "deferred" || item.deferred;
        return (
          <div
            key={item.id}
            className="flex items-center gap-2 rounded-xl border px-3 py-2 text-sm"
            style={{
              borderColor: failed
                ? "color-mix(in srgb, var(--theme-error, #b42318) 35%, var(--theme-border))"
                : "var(--theme-border)",
              backgroundColor: "var(--theme-bg-card)",
              color: failed
                ? "var(--theme-error, #b42318)"
                : "var(--theme-text-secondary)",
            }}
          >
            {deferred || failed ? <X size={14} /> : <Clock size={14} />}
            <span className="min-w-0 flex-1 truncate">{item.content}</span>
            <span className="flex min-h-5 shrink-0 min-w-[7rem] items-center justify-center text-center text-xs">
              {failed
                ? t("chat.steerFailedRetry", "发送失败，请重试")
                : deferred
                  ? t("chat.steerNext", "任务结束后发送")
                  : t("chat.steerQueued", "当前步骤后送达")}
            </span>
            {onCancel && (
              <button
                type="button"
                onClick={() => onCancel(item.content, item.id)}
                className="shrink-0 rounded-full p-1 opacity-70 transition hover:bg-[color-mix(in_srgb,var(--theme-text)_8%,transparent)] hover:opacity-100"
                aria-label={t("chat.steerCancel", "取消这条插话")}
                title={t("chat.steerCancel", "取消这条插话")}
              >
                <X size={14} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
