import { clsx } from "clsx";
import { ListTree, MessageSquare, Hash } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MessageOutlineItem } from "./messageOutline";

interface MessageOutlinePanelProps {
  items: MessageOutlineItem[];
  activeId: string | null;
  onNavigate: (anchorId: string, messageIndex: number) => void;
}

function OutlineItem({
  item,
  isActive,
  onClick,
}: {
  item: MessageOutlineItem;
  isActive: boolean;
  onClick: () => void;
}) {
  const indentPx = (item.level - 1) * 16;

  return (
    <button
      onClick={onClick}
      className={clsx(
        "group relative flex items-center gap-2 w-full text-left py-[6px] rounded-md transition-all duration-200 outline-none",
        "focus-visible:ring-1 focus-visible:ring-stone-400/50 dark:focus-visible:ring-stone-500/50",
        item.level === 1 ? "text-[11.5px]" : "text-[11px]",
        isActive
          ? "text-stone-800 dark:text-stone-100 font-medium bg-stone-100/80 dark:bg-stone-800/60"
          : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-800/40",
      )}
      style={{ paddingLeft: `${12 + indentPx}px`, paddingRight: "10px" }}
      title={item.label}
    >
      {isActive && (
        <span className="absolute left-0 top-[5px] bottom-[5px] w-[2.5px] rounded-full bg-stone-700 dark:bg-stone-300" />
      )}
      {item.kind === "user-message" ? (
        <MessageSquare
          size={12}
          className={clsx(
            "shrink-0 transition-colors duration-200",
            isActive
              ? "text-stone-600 dark:text-stone-300"
              : "text-stone-400 dark:text-stone-500 group-hover:text-stone-500 dark:group-hover:text-stone-400",
          )}
        />
      ) : (
        <Hash
          size={item.level === 1 ? 13 : 11}
          className={clsx(
            "shrink-0 transition-colors duration-200",
            isActive
              ? "text-stone-500 dark:text-stone-400"
              : "text-stone-300 dark:text-stone-600 group-hover:text-stone-400 dark:group-hover:text-stone-500",
          )}
        />
      )}
      <span className="truncate leading-tight">{item.label}</span>
    </button>
  );
}

export function MessageOutlinePanel({
  items,
  activeId,
  onNavigate,
}: MessageOutlinePanelProps) {
  const { t } = useTranslation();

  if (items.length === 0) return null;

  return (
    <div className="py-3 px-2 overflow-y-auto h-full">
      <div className="flex items-center gap-2 px-2 py-1.5 mb-2">
        <ListTree
          size={13}
          strokeWidth={2}
          className="text-stone-400 dark:text-stone-500"
        />
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-stone-400 dark:text-stone-500">
          {t("chat.outline")}
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-stone-300 dark:text-stone-600">
          {items.length}
        </span>
      </div>
      <div className="space-y-0.5">
        {items.map((item) => (
          <OutlineItem
            key={item.id}
            item={item}
            isActive={activeId === item.anchorId}
            onClick={() => onNavigate(item.anchorId, item.messageIndex)}
          />
        ))}
      </div>
    </div>
  );
}
