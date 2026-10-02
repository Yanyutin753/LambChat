import { useState, useRef, useId, useCallback } from "react";
import { createPortal } from "react-dom";
import { CircleHelp, Keyboard } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ResourceCardMenu } from "../common/ResourceCardMenu";
import { ShortcutDialog } from "./ChatInputShortcuts";

export function ChatInputHelpMenu({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [position, setPosition] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const closeMenu = useCallback((restoreFocus = false) => {
    setPosition(null);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  return createPortal(
    <div
      data-yields-sidebar
      className={`chat-input-help-menu fixed z-50${className ? ` ${className}` : ""}`}
      style={{
        bottom: "calc(0.5rem + var(--app-safe-area-bottom-active, 0px))",
        right: "calc(0.5rem + var(--app-safe-area-right, 0px))",
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={t("common.help")}
        aria-haspopup="menu"
        aria-expanded={!!position}
        aria-controls={position ? menuId : undefined}
        onClick={() => {
          if (position) closeMenu();
          else {
            const rect = triggerRef.current!.getBoundingClientRect();
            setPosition({ x: rect.right - 224, y: rect.top - 104 });
          }
        }}
        className="ui-button ui-icon-button ui-button--ghost ui-button--lg rounded-full"
      >
        <CircleHelp size={16} />
      </button>
      {position && (
        <ResourceCardMenu
          id={menuId}
          title={t("common.help")}
          position={position}
          onClose={closeMenu}
          actions={[
            {
              label: t("chat.helpDocs"),
              href: "https://yanyutin753.github.io/LambChat/",
              icon: <CircleHelp size={16} />,
            },
            {
              label: t("chat.keyboardShortcuts"),
              icon: <Keyboard size={16} />,
              onClick: () => setDialogOpen(true),
            },
          ]}
        />
      )}
      <ShortcutDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </div>,
    document.body,
  );
}
