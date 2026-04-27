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
      className={`flex items-center justify-center size-10 rounded-lg shrink-0 ${bg}`}
    >
      <Icon size={18} className={color} />
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
          ? "gap-2.5 px-3 sm:px-4 py-2.5 sm:py-3"
          : "gap-2 sm:gap-3 px-2 sm:px-4 py-2 sm:py-3"
      } border-b border-stone-200 dark:border-stone-700/80 shrink-0 ${
        isSidebar
          ? "bg-stone-50 dark:bg-[#1e1e1e]"
          : "bg-stone-50/80 dark:bg-stone-800/60"
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
            isSidebar
              ? "text-[13px] sm:text-sm font-medium"
              : "font-medium text-sm"
          } text-stone-800 dark:text-stone-100 truncate`}
          title={title}
        >
          {title}
        </h3>
        {subtitle && (
          <p
            className={`text-xs ${
              isSidebar ? "" : "hidden sm:block"
            } text-stone-400 dark:text-stone-500 mt-0.5`}
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
