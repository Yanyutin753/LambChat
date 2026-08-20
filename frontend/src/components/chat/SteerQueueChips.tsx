import { Clock, X } from "lucide-react";

import i18n from "../../i18n";

export interface PendingSteer {
  id: string;
  content: string;
}

interface SteerQueueChipsProps {
  steers: PendingSteer[];
  onCancel: (content: string) => void;
}

/**
 * 运行中插话排队 chips：显示在输入框上方。
 *
 * 消息送达（后端注入模型调用并发 user:message 事件）后由父级移除，
 * 对应的正式用户气泡由标准 user:message 渲染路径上屏。
 */
export function SteerQueueChips({ steers, onCancel }: SteerQueueChipsProps) {
  if (steers.length === 0) return null;

  const queuedLabel = i18n.t("chat.steerQueued", "已排队，当前步骤后送达");
  const cancelLabel = i18n.t("chat.steerCancel", "取消这条插话");

  return (
    <div className="flex flex-col gap-1.5 px-1 pb-1" data-testid="steer-queue">
      {steers.map((steer) => (
        <div
          key={steer.id}
          className="flex items-center gap-2 self-end rounded-full border px-3 py-1 text-xs max-w-[85%]"
          style={{
            borderColor: "color-mix(in srgb, var(--theme-primary) 35%, transparent)",
            backgroundColor:
              "color-mix(in srgb, var(--theme-primary) 8%, transparent)",
            color: "var(--theme-text-secondary)",
          }}
          title={queuedLabel}
        >
          <Clock
            size={12}
            style={{ color: "var(--theme-primary)" }}
            className="shrink-0"
          />
          <span className="truncate">{steer.content}</span>
          <button
            type="button"
            onClick={() => onCancel(steer.content)}
            className="shrink-0 rounded-full p-0.5 opacity-60 transition hover:opacity-100"
            title={cancelLabel}
            aria-label={cancelLabel}
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
