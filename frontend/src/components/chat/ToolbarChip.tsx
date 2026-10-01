import type { ReactNode } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  return (
    <div className="composer-toolbar-chip group relative flex min-w-0 shrink">
      <button
        type="button"
        className="chat-tool-btn shrink min-w-0 overflow-hidden"
        onClick={onClick}
        aria-label={title ?? label}
        title={title ?? label}
      >
        <div className="flex flex-row items-center gap-2 min-w-0">
          {icon && (
            <span
              aria-hidden="true"
              className={`relative h-4 w-4 shrink-0 inline-flex items-center justify-center overflow-hidden${onClear ? " sm:group-hover:opacity-0 sm:group-focus-within:opacity-0" : ""}`}
            >
              {icon}
            </span>
          )}
          {/* 名称在空间不足时截断；手机端外层仍保留完整点击区域。 */}
          <span
            className={`min-w-0 truncate text-14 leading-5 font-semibold text-blue-600 dark:text-blue-400 font-serif${
              labelClassName ? ` ${labelClassName}` : ""
            }`}
          >
            {label}
          </span>
          {trailing}
        </div>
      </button>
      {onClear && (
        <button
          type="button"
          aria-label={`${t("common.clear")} ${label}`}
          title={`${t("common.clear")} ${label}`}
          onClick={onClear}
          className="chat-tool-btn absolute left-0 top-0 !hidden h-9 w-8 sm:!flex opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto"
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
