import { useState, useRef, useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleHelp, ExternalLink, Keyboard } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ShortcutDialog } from "./ChatInputShortcuts";

// ── Shared styles ──────────────────────────────────────────
const theme = {
  text: "var(--theme-text)",
  textSecondary: "var(--theme-text-secondary)",
  bgCard: "var(--theme-bg-card)",
  border: "var(--theme-border)",
  bgHover: "var(--theme-bg-hover, rgba(128,128,128,0.08))",
};

const buttonStyle: React.CSSProperties = {
  backgroundColor: `color-mix(in srgb, ${theme.bgCard} 85%, transparent)`,
  border: `1px solid ${theme.border}`,
  color: theme.textSecondary,
  minWidth: 0,
  minHeight: 0,
};

const panelStyle: React.CSSProperties = {
  backgroundColor: theme.bgCard,
  border: `1px solid ${theme.border}`,
};

const menuItemClass =
  "flex gap-2 sm:gap-2.5 items-center w-full px-2.5 py-1.5 sm:px-3 sm:py-2 text-[12px] sm:text-[13px] rounded-lg cursor-pointer transition-colors";

const hover: React.DOMAttributes<HTMLElement> = {
  onMouseEnter: (e) => {
    e.currentTarget.style.backgroundColor = theme.bgHover;
  },
  onMouseLeave: (e) => {
    e.currentTarget.style.backgroundColor = "transparent";
  },
};

// ── Tiny helpers ────────────────────────────────────────────
function SecondaryIcon({ children }: { children: ReactNode }) {
  return (
    <span className="shrink-0" style={{ color: theme.textSecondary }}>
      {children}
    </span>
  );
}

function MenuLink({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      role="menuitem"
      className={`${menuItemClass} no-underline`}
      style={{ color: theme.text }}
      {...hover}
      {...props}
    >
      {children}
    </a>
  );
}

function MenuButtonItem({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      role="menuitem"
      className={menuItemClass}
      style={{ color: theme.text }}
      {...hover}
      {...props}
    >
      {children}
    </button>
  );
}

// ── Component ───────────────────────────────────────────────
export function ChatInputHelpMenu({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const close = () => setOpen(false);

  return createPortal(
    <div
      ref={ref}
      data-yields-sidebar
      className={`chat-input-help-menu fixed bottom-1 right-1 sm:bottom-2 sm:right-2 z-50${
        className ? ` ${className}` : ""
      }`}
    >
      <button
        type="button"
        aria-label={t("common.help", "帮助")}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-center w-5 h-5 sm:w-7 sm:h-7 text-xs font-medium rounded-full shadow-md transition-all duration-200 hover:shadow-lg hover:scale-110 active:scale-95"
        style={buttonStyle}
      >
        <CircleHelp size={14} className="sm:w-4 sm:h-4" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full right-0 mb-1.5 sm:mb-2 w-[170px] sm:w-[200px] rounded-xl p-1 shadow-lg"
          style={panelStyle}
        >
          <MenuLink
            href="https://yanyutin753.github.io/LambChat/"
            onClick={close}
          >
            <SecondaryIcon>
              <CircleHelp size={14} className="sm:w-4 sm:h-4" />
            </SecondaryIcon>
            <span className="flex-1 font-serif">
              {t("chat.helpDocs", "帮助文档")}
            </span>
            <SecondaryIcon>
              <ExternalLink size={12} style={{ opacity: 0.5 }} />
            </SecondaryIcon>
          </MenuLink>

          <MenuButtonItem
            onClick={() => {
              close();
              setDialogOpen(true);
            }}
          >
            <SecondaryIcon>
              <Keyboard size={14} className="sm:w-4 sm:h-4" />
            </SecondaryIcon>
            <span className="font-serif">
              {t("chat.keyboardShortcuts", "键盘快捷键")}
            </span>
          </MenuButtonItem>
        </div>
      )}

      <ShortcutDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </div>,
    document.body,
  );
}
