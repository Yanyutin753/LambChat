import type { ReactNode } from "react";
import { X } from "lucide-react";

interface ToolbarChipProps {
  icon?: ReactNode;
  label: string;
  title?: string;
  onClick: () => void;
  onClear?: () => void;
}

export function ToolbarChip({
  icon,
  label,
  title,
  onClick,
  onClear,
}: ToolbarChipProps) {
  return (
    <button
      type="button"
      className="chat-tool-btn group shrink min-w-0"
      onClick={onClick}
      title={title ?? label}
    >
      <div className="flex flex-row items-center gap-2 min-w-0">
        {icon && (
          <span className="relative h-[18px] w-[18px] shrink-0 inline-flex items-center justify-center overflow-hidden">
            {icon}
            {onClear && (
              <X
                size={18}
                className="absolute inset-0 m-auto opacity-0 transition-opacity group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  onClear();
                }}
              />
            )}
          </span>
        )}
        <span className="max-w-40 sm:max-w-52 truncate text-sm font-semibold text-blue-600 dark:text-blue-400 font-serif">
          {label}
        </span>
      </div>
    </button>
  );
}
