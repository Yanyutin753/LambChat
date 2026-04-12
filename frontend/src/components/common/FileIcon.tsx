import { type ReactNode } from "react";
import { type LucideIcon } from "lucide-react";

/* ── FileIcon ── */

interface FileIconProps {
  icon: LucideIcon;
  bg?: string;
  color?: string;
}

export function FileIcon({
  icon: Icon,
  bg = "bg-blue-100 dark:bg-blue-900/40",
  color = "text-blue-600 dark:text-blue-400",
}: FileIconProps) {
  return (
    <div
      className={`flex items-center justify-center w-10 h-10 sm:w-11 sm:h-11 rounded-xl shrink-0 ${bg}`}
    >
      <Icon size={20} className={`sm:w-[22px] sm:h-[22px] ${color}`} />
    </div>
  );
}

/* ── PreviewHeader ── */

type PreviewHeaderVariant = "sidebar" | "card";

interface PreviewHeaderProps {
  icon: LucideIcon;
  iconBg?: string;
  iconColor?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  variant?: PreviewHeaderVariant;
}
export function PreviewHeader({
  icon,
  iconBg,
  iconColor,
  title,
  subtitle,
  actions,
  variant = "sidebar",
}: PreviewHeaderProps) {
  const isSidebar = variant === "sidebar";

  return (
    <div
      className={`flex items-center ${
        isSidebar
          ? "gap-2 sm:gap-3 px-3 sm:px-5 py-3 sm:py-4"
          : "gap-2 sm:gap-3 px-2 sm:px-4 py-2 sm:py-3"
      } border-b border-stone-200 ${
        isSidebar ? "dark:border-[#333]" : "dark:border-stone-700"
      } shrink-0 bg-gradient-to-r from-stone-50 to-white ${
        isSidebar
          ? "dark:from-[#252526] dark:to-[#1e1e1e]"
          : "dark:bg-stone-800/50"
      } whitespace-nowrap`}
    >
      <FileIcon icon={icon} bg={iconBg} color={iconColor} />
      <div
        className={`flex-1 min-w-0 ${
          isSidebar ? "min-w-[120px] sm:min-w-[180px]" : ""
        }`}
      >
        <h3
          className={`${
            isSidebar ? "font-bold text-sm sm:text-base" : "font-medium text-sm"
          } text-stone-900 dark:text-stone-100 truncate`}
          title={title}
        >
          {title}
        </h3>
        {subtitle && (
          <p
            className={`text-xs ${
              isSidebar ? "" : "hidden sm:block"
            } text-stone-500 dark:text-stone-400 mt-0.5`}
          >
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-0.5 sm:gap-1 relative z-10 shrink-0">
          {actions}
        </div>
      )}
    </div>
  );
}
