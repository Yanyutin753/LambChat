import { useTranslation } from "react-i18next";
import { MessageSquare, Star, Download, ExternalLink } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api";
import { ResourceCardMenu } from "../../common/ResourceCardMenu";

interface FileContextMenuProps {
  menu: { x: number; y: number; file: RevealedFileItem } | null;
  id: string;
  onClose: (restoreFocus?: boolean) => void;
  file: RevealedFileItem;
  onGoToSession: (sessionId: string, file?: RevealedFileItem) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
}

export function FileContextMenu({
  menu,
  id,
  onClose,
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
    <ResourceCardMenu
      id={id}
      title={file.file_name}
      position={menu}
      onClose={onClose}
      actions={items.map((item) => ({
        label: item.label,
        icon: (
          <item.icon size={16} className="shrink-0 text-theme-text-secondary" />
        ),
        onClick: item.action,
      }))}
    />
  );
}
