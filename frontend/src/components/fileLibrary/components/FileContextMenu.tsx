import { useTranslation } from "react-i18next";
import { MessageSquare, Star, Download, ExternalLink } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api";

interface FileContextMenuProps {
  menu: { x: number; y: number; file: RevealedFileItem } | null;
  menuRef: React.RefObject<HTMLDivElement | null>;
  file: RevealedFileItem;
  onGoToSession: (sessionId: string, file?: RevealedFileItem) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
}

export function FileContextMenu({
  menu,
  menuRef,
  file,
  onGoToSession,
  onToggleFavorite,
}: FileContextMenuProps) {
  const { t } = useTranslation();
  if (!menu) return null;

  const isProject = file.file_type === "project";
  const hasUrl = !!file.url && !isProject;

  const items: {
    icon: typeof MessageSquare;
    label: string;
    action: () => void;
  }[] = [
    {
      icon: MessageSquare,
      label: t("fileLibrary.context.goToSession"),
      action: () => onGoToSession(file.session_id, file),
    },
    {
      icon: Star,
      label: file.is_favorite
        ? t("fileLibrary.context.unfavorite")
        : t("fileLibrary.context.favorite"),
      action: () => onToggleFavorite(file),
    },
    ...(hasUrl
      ? [
          {
            icon: Download,
            label: t("fileLibrary.context.download"),
            action: () => {
              const a = document.createElement("a");
              a.href = getFullUrl(file.url!) || "";
              a.download = file.file_name || "download";
              a.target = "_blank";
              a.rel = "noopener noreferrer";
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
            },
          },
        ]
      : []),
    ...(hasUrl
      ? [
          {
            icon: ExternalLink,
            label: t("fileLibrary.context.openInNewTab"),
            action: () => {
              window.open(
                getFullUrl(file.url!),
                "_blank",
                "noopener noreferrer",
              );
            },
          },
        ]
      : []),
  ];

  return (
    <div
      ref={menuRef}
      className="fixed z-[999] bg-theme-bg-card shadow-xl rounded-xl border border-theme-border p-1 min-w-[240px]"
      style={{ position: "fixed", top: menu.y, left: menu.x }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item) => (
        <button
          key={item.label}
          onClick={item.action}
          className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-theme-bg-subtle cursor-pointer text-13 text-theme-text transition-colors"
        >
          <div className="size-5 flex items-center justify-center shrink-0">
            <item.icon size={16} className="text-theme-text-secondary" />
          </div>
          <span className="flex-1 text-left">{item.label}</span>
        </button>
      ))}
    </div>
  );
}
