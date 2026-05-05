import { type ReactNode } from "react";
import { Checkbox } from "./Checkbox";

export interface SkillBaseCardProps {
  title: string;
  description?: string;
  descriptionMaxLines?: 2 | 3;
  gradient?: string[];
  bannerOverlay?: ReactNode;
  icon?: ReactNode;
  statusPills?: ReactNode;
  tags?: ReactNode;
  meta?: ReactNode;
  extraContent?: ReactNode;
  footer?: ReactNode;
  muted?: boolean;
  selected?: boolean;
  selectionMode?: boolean;
  onSelect?: () => void;
  animated?: boolean;
  animationDelay?: number;
  className?: string;
  onClick?: (e: React.MouseEvent<HTMLDivElement>) => void;
}

export function SkillBaseCard({
  title,
  description,
  descriptionMaxLines = 2,
  gradient,
  bannerOverlay,
  icon,
  statusPills,
  tags,
  meta,
  extraContent,
  footer,
  muted = false,
  selected = false,
  selectionMode = false,
  onSelect,
  animated = false,
  animationDelay = 0,
  className = "",
  onClick,
}: SkillBaseCardProps) {
  const lineClamp = descriptionMaxLines === 3 ? "line-clamp-3" : "line-clamp-2";

  return (
    <div
      className={`scb group flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none dark:border dark:border-[var(--theme-border)] ${
        muted ? "scb--muted" : ""
      } ${
        selected
          ? "ring-2 ring-[var(--theme-primary)] animate-[select-glow_2s_ease-in-out]"
          : ""
      } ${animated ? "scb--animated" : ""} ${
        selectionMode && onSelect ? "cursor-pointer" : ""
      } ${className}`}
      style={animated ? { animationDelay: `${animationDelay}ms` } : undefined}
      onClick={
        selectionMode && onSelect
          ? (e) => {
              if (
                !(e.target as HTMLElement).closest("button") &&
                !(e.target as HTMLElement).closest('[role="checkbox"]')
              ) {
                onSelect();
              }
            }
          : onClick
      }
    >
      {selectionMode && onSelect && (
        <div
          className={`absolute top-3 right-3 z-10 transition-all duration-200 ${
            selected ? "scale-110" : "sm:scale-90 sm:group-hover:scale-100"
          }`}
        >
          <Checkbox
            size="lg"
            checked={selected}
            onChange={() => onSelect()}
            className="shadow-sm sm:opacity-0 sm:group-hover:opacity-100"
          />
        </div>
      )}

      {gradient && (
        <div
          className="scb__banner relative h-12 shrink-0"
          style={{
            background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
          }}
        >
          {bannerOverlay && (
            <div className="absolute top-2 right-2 flex gap-1.5">
              {bannerOverlay}
            </div>
          )}
        </div>
      )}

      <div
        className={`flex flex-1 flex-col p-4 ${
          gradient ? "-mt-3 pt-5" : "sm:p-5"
        }`}
      >
        <div className="flex items-start gap-3">
          {icon && <div className="scb__icon-ring shrink-0">{icon}</div>}
          <div className="min-w-0 flex-1">
            <h3
              className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight"
              title={title}
            >
              {title}
            </h3>
            {statusPills}
          </div>
        </div>

        {description && (
          <p
            className={`mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] ${lineClamp} min-h-[3.25em]`}
          >
            {description}
          </p>
        )}

        {tags && <div className="mt-3">{tags}</div>}

        {extraContent && <div className="mt-3">{extraContent}</div>}

        <div className="flex-1" />

        {meta && <div className="mt-4">{meta}</div>}

        {footer && <div className="scb__footer">{footer}</div>}
      </div>
    </div>
  );
}
