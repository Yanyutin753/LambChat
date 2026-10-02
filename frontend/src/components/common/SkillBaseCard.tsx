import {
  useCallback,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ResourceCardMenu, type ResourceCardAction } from "./ResourceCardMenu";
import { Checkbox } from "./Checkbox";

export interface SkillBaseCardProps {
  title: string;
  actions?: ResourceCardAction[];
  style?: CSSProperties;
  iconClassName?: string;
  description?: string;
  descriptionMaxLines?: 2 | 3;
  gradient?: string[];
  bannerLeadingOverlay?: ReactNode;
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
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
}

export function SkillBaseCard({
  title,
  actions = [],
  style,
  iconClassName = "scb__icon-ring",
  description,
  descriptionMaxLines = 2,
  gradient,
  bannerLeadingOverlay,
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
  const { t } = useTranslation();
  const menuId = useId();
  const focusReturn = useRef<HTMLElement | null>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const closeMenu = useCallback((restoreFocus = false) => {
    setMenuPosition(null);
    if (restoreFocus) focusReturn.current?.focus();
  }, []);
  const singleAction = actions.length === 1 ? actions[0] : undefined;
  const SingleAction = singleAction?.href ? "a" : "button";
  const lineClamp = descriptionMaxLines === 3 ? "line-clamp-3" : "line-clamp-2";

  return (
    <div
      role="group"
      aria-label={title}
      tabIndex={
        onClick || (selectionMode && onSelect) || actions.length ? 0 : undefined
      }
      onContextMenu={
        actions.length
          ? (e) => {
              e.preventDefault();
              e.stopPropagation();
              focusReturn.current = e.currentTarget;
              setMenuPosition({ x: e.clientX, y: e.clientY });
            }
          : undefined
      }
      onKeyDown={(e) => {
        if (
          e.target === e.currentTarget &&
          actions.length &&
          (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))
        ) {
          e.preventDefault();
          focusReturn.current = e.currentTarget;
          const rect = e.currentTarget.getBoundingClientRect();
          setMenuPosition({ x: rect.left, y: rect.top + 48 });
          return;
        }
        if (
          e.target === e.currentTarget &&
          (e.key === "Enter" || e.key === " ") &&
          (onClick || (selectionMode && onSelect))
        ) {
          e.preventDefault();
          e.currentTarget.click();
        }
      }}
      className={`scb relative group flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none dark:border dark:border-[var(--theme-border)] ${
        muted ? "scb--muted" : ""
      } ${
        selected
          ? "ring-2 ring-[var(--theme-primary)] animate-[select-glow_2s_ease-in-out]"
          : ""
      } ${animated ? "scb--animated" : ""} ${
        selectionMode && onSelect ? "cursor-pointer" : ""
      } ${actions.length ? "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]" : ""} ${className}`}
      style={{
        ...style,
        ...(animated
          ? { animationDelay: `${Math.min(animationDelay, 180)}ms` }
          : {}),
      }}
      onClick={(e) => {
        if (
          (e.target as HTMLElement).closest(
            'button, a, input, select, textarea, [role="checkbox"], [role="switch"], [role="menu"]',
          )
        )
          return;
        if (selectionMode && onSelect) onSelect();
        else onClick?.(e);
      }}
    >
      {(gradient || bannerLeadingOverlay || bannerOverlay) && (
        <div
          className="scb__banner relative h-12 shrink-0"
          style={{
            background: gradient
              ? `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`
              : undefined,
          }}
        >
          <div className="absolute inset-0 flex items-start justify-between px-2 py-2 z-[3]">
            <div className="flex items-center gap-1.5">
              {bannerLeadingOverlay}
              {!bannerLeadingOverlay && selectionMode && onSelect && (
                <div
                  className={`transition-all duration-200 ${
                    selected
                      ? "scale-110"
                      : "sm:scale-90 sm:group-hover:scale-100"
                  }`}
                >
                  <Checkbox
                    ariaLabel={title}
                    size="lg"
                    checked={selected}
                    onChange={() => onSelect()}
                    className="shadow-sm sm:opacity-0 sm:group-hover:opacity-100"
                  />
                </div>
              )}
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              {bannerLeadingOverlay && selectionMode && onSelect && (
                <div
                  className={`transition-all duration-200 ${
                    selected
                      ? "scale-110"
                      : "sm:scale-90 sm:group-hover:scale-100"
                  }`}
                >
                  <Checkbox
                    ariaLabel={title}
                    size="lg"
                    checked={selected}
                    onChange={() => onSelect()}
                    className="shadow-sm sm:opacity-0 sm:group-hover:opacity-100"
                  />
                </div>
              )}
              {bannerOverlay}
            </div>
          </div>
        </div>
      )}

      {!gradient && selectionMode && onSelect && (
        <div
          className={`absolute top-3 right-3 z-10 transition-all duration-200 ${
            selected ? "scale-110" : "sm:scale-90 sm:group-hover:scale-100"
          }`}
        >
          <Checkbox
            ariaLabel={title}
            size="lg"
            checked={selected}
            onChange={() => onSelect()}
            className="shadow-sm sm:opacity-0 sm:group-hover:opacity-100"
          />
        </div>
      )}

      <div
        className={`flex flex-1 flex-col p-3.5 ${gradient ? "-mt-3 pt-4" : ""}`}
      >
        <div className="flex items-start gap-2.5">
          {icon && <div className={`${iconClassName} shrink-0`}>{icon}</div>}
          <div className="min-w-0 flex-1">
            <h3
              title={title}
              className="line-clamp-2 break-words text-16 font-medium font-serif text-[var(--theme-text-secondary)] leading-tight"
            >
              {onClick && !selectionMode ? (
                <button
                  type="button"
                  className="w-full text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
                  onClick={(e) => {
                    e.stopPropagation();
                    onClick(e);
                  }}
                >
                  {title}
                </button>
              ) : (
                title
              )}
            </h3>
            {statusPills}
          </div>
        </div>

        {description && (
          <p
            className={`mt-2.5 text-13 leading-relaxed text-[var(--theme-text-secondary)] ${lineClamp}`}
          >
            {description}
          </p>
        )}

        {tags && <div className="mt-2.5">{tags}</div>}

        {extraContent && <div className="mt-2.5">{extraContent}</div>}

        <div className="flex-1" />

        {meta && <div className="mt-3">{meta}</div>}

        {(footer || actions.length > 0) && (
          <div className="scb__footer flex items-center gap-2">
            {footer && <div className="min-w-0 flex-1">{footer}</div>}
            {singleAction ? (
              <SingleAction
                type={singleAction.href ? undefined : "button"}
                href={singleAction.disabled ? undefined : singleAction.href}
                target={singleAction.href ? "_blank" : undefined}
                rel={singleAction.href ? "noopener noreferrer" : undefined}
                disabled={singleAction.href ? undefined : singleAction.disabled}
                aria-disabled={singleAction.disabled || undefined}
                aria-label={singleAction.label}
                title={singleAction.label}
                aria-pressed={singleAction.checked}
                aria-current={singleAction.current ? "page" : undefined}
                className={`scb__action-btn scb__action-btn--ghost ml-auto min-h-11 min-w-11 shrink-0 aria-disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] ${singleAction.danger ? "!text-theme-error" : ""}`}
                onClick={(event) => {
                  event.stopPropagation();
                  if (singleAction.disabled) {
                    event.preventDefault();
                    return;
                  }
                  singleAction.onClick?.();
                }}
              >
                {singleAction.icon ?? singleAction.label}
              </SingleAction>
            ) : (
              actions.length > 1 && (
                <button
                  type="button"
                  aria-label={t("common.moreOptions")}
                  aria-haspopup="menu"
                  aria-expanded={Boolean(menuPosition)}
                  aria-controls={menuPosition ? menuId : undefined}
                  className="scb__action-btn scb__action-btn--ghost ml-auto min-h-11 min-w-11 shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (menuPosition) {
                      closeMenu(true);
                      return;
                    }
                    focusReturn.current = e.currentTarget;
                    const rect = e.currentTarget.getBoundingClientRect();
                    setMenuPosition({
                      x: rect.right - 224,
                      y: rect.bottom + 4,
                    });
                  }}
                >
                  <MoreHorizontal size={16} />
                </button>
              )
            )}
          </div>
        )}
      </div>
      {menuPosition && actions.length > 0 && (
        <ResourceCardMenu
          id={menuId}
          title={title}
          actions={actions}
          position={menuPosition}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
