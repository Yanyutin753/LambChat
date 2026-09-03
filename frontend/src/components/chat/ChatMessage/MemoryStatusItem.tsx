import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../common";
import { formatDuration } from "../../../utils/datetime";

/**
 * 首轮记忆装配进度 item——与沙箱初始化（SandboxItem）完全同款：
 * loading pill「正在检索相关记忆」→ success pill「记忆检索完成」+ 用时。
 */
export function MemoryStatusItem({
  status,
  startedAt,
  completedAt,
}: {
  status: "starting" | "ready" | "cancelled";
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();

  const durationText = (() => {
    if (startedAt) {
      const startMs = new Date(startedAt).getTime();
      const endMs = completedAt ? new Date(completedAt).getTime() : Date.now();
      if (endMs > startMs) return formatDuration(endMs - startMs);
    }
    return undefined;
  })();

  return (
    <CollapsiblePill
      status={status === "starting" ? "loading" : "success"}
      icon={<BookOpen size={12} className="shrink-0 opacity-50" />}
      label={
        status === "starting"
          ? t("chat.memory.initializing")
          : t("chat.memory.ready")
      }
      suffix={
        status === "ready" && durationText ? (
          <span className="text-xs font-mono font-medium min-w-0 truncate overflow-hidden leading-none">
            {durationText}
          </span>
        ) : undefined
      }
      animatedDots={status === "starting"}
    />
  );
}
