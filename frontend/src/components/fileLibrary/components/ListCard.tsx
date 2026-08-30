import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFileTypeInfo } from "../../documents/utils";
import { useContextMenu } from "../hooks/useContextMenu";
import { buildFileCardPreview, buildMeta } from "../utils";
import { FileContextMenu } from "./FileContextMenu";
import { FileCardPreview } from "./FileCardPreview";

interface ListCardProps {
  file: RevealedFileItem;
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string, file?: RevealedFileItem) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
}

export function ListCard({
  file,
  onPreview,
  onGoToSession,
  onToggleFavorite,
}: ListCardProps) {
  const { t } = useTranslation();
  const fileInfo = getFileTypeInfo(file.file_name, file.mime_type || undefined);
  const FileIcon = fileInfo.icon;
  const cardPreview = buildFileCardPreview(file, t);
  const meta = buildMeta(file, t);
  const ctx = useContextMenu();

  return (
    <>
      <div
        onClick={() => onPreview(file)}
        onContextMenu={(e) => ctx.show(e, file)}
        className="group/card relative flex items-center gap-3.5 px-4 py-3 rounded-xl bg-theme-bg-card border border-theme-border cursor-pointer select-none transition-all duration-150 hover:bg-theme-bg-subtle hover:border-theme-border-hover hover:shadow-sm"
      >
        {/* Icon / thumbnail */}
        <div className="shrink-0">
          <div className="h-10 w-10 overflow-hidden rounded-lg ring-1 ring-stone-200/60 dark:ring-stone-700/50">
            <FileCardPreview preview={cardPreview} icon={FileIcon} compact />
          </div>
        </div>

        {/* Name + meta */}
        <div className="flex-1 min-w-0">
          <p className="text-13 font-medium text-theme-text truncate leading-snug">
            {file.file_name}
          </p>
          <p className="mt-0.5 text-11 text-theme-text-tertiary truncate font-serif">
            {meta}
          </p>
        </div>

        {/* More button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            ctx.show(e, file);
          }}
          className="shrink-0 p-1.5 rounded-md text-theme-text-tertiary hover:text-theme-text-secondary hover:bg-theme-bg-subtle transition-all"
        >
          <MoreHorizontal size={16} />
        </button>
      </div>

      <FileContextMenu
        menu={ctx.menu}
        menuRef={ctx.menuRef}
        file={file}
        onGoToSession={onGoToSession}
        onToggleFavorite={onToggleFavorite}
      />
    </>
  );
}
