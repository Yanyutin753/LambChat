import type { ReactNode } from "react";
import { X } from "lucide-react";

interface ToolbarChipProps {
  icon?: ReactNode;
  label: string;
  /** 悬停提示；缺省回落 label。 */
  title?: string;
  /** 标签尾部附加节点（如沙箱 daemon 状态点）。 */
  trailing?: ReactNode;
  /** 追加到标签上的类名（如手机端隐藏文字：hidden sm:inline）。 */
  labelClassName?: string;
  onClick: () => void;
  onClear?: () => void;
}

export function ToolbarChip({
  icon,
  label,
  title,
  trailing,
  labelClassName,
  onClick,
  onClear,
}: ToolbarChipProps) {
  return (
    <button
      type="button"
      className="chat-tool-btn group shrink min-w-0 overflow-hidden"
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
        {/* Tailwind 截断正解：标签保持自然宽度（basis auto + shrink 1），
            空间够时完整显示；行内一挤它先收缩出 …（全链 min-w-0 传递）。
            按钮 overflow-hidden 兜底：链路再断也只裁自己，结构上杜绝重叠 */}
        <span
          className={`min-w-0 truncate text-sm font-semibold text-blue-600 dark:text-blue-400 font-serif${
            labelClassName ? ` ${labelClassName}` : ""
          }`}
        >
          {label}
        </span>
        {trailing}
      </div>
    </button>
  );
}
