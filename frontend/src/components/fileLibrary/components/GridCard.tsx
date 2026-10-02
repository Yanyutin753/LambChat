import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFileTypeInfo } from "../../documents/utils";
import { useContextMenu } from "../hooks/useContextMenu";
import { buildFileCardPreview, buildMeta } from "../utils";
import { FileContextMenu } from "./FileContextMenu";
import { FileCardPreview } from "./FileCardPreview";

interface GridCardProps {
  file: RevealedFileItem;
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string, file?: RevealedFileItem) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
}

export function GridCard({
  file,
  onPreview,
  onGoToSession,
  onToggleFavorite,
}: GridCardProps) {
  const { t } = useTranslation();
  const fileInfo = getFileTypeInfo(file.file_name, file.mime_type || undefined);
  const FileIcon = fileInfo.icon;
  const isProject = file.file_type === "project";
  const cardPreview = buildFileCardPreview(file, t);
  const meta = buildMeta(file, t);
  const ctx = useContextMenu();

  return (
    <>
      <div
        role="group"
        aria-label={file.file_name}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))
            ctx.show(e, file);
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onPreview(file);
          }
        }}
        onClick={() => onPreview(file)}
        onContextMenu={(e) => ctx.show(e, file)}
        className="group/card relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-theme-border bg-theme-bg-card transition-all duration-200 hover:shadow-lg hover:border-theme-border-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
      >
        {/* File header */}
        <div className="flex items-center gap-2 px-2.5 py-2.5">
          <div className="shrink-0 flex items-center justify-center">
            <FileIcon
              size={16}
              className={
                isProject
                  ? "text-violet-500 dark:text-violet-400"
                  : fileInfo.color
              }
            />
          </div>
          <div className="flex-1 min-w-0">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onPreview(file);
              }}
              className="block max-w-full text-left text-13 text-theme-text truncate leading-tight font-serif focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
              title={file.file_name}
            >
              {file.file_name}
            </button>
          </div>
          <button
            type="button"
            aria-label={t("common.moreOptions")}
            aria-haspopup="menu"
            aria-expanded={!!ctx.menu}
            aria-controls={ctx.menu ? ctx.menuId : undefined}
            onClick={(e) => {
              e.stopPropagation();
              if (ctx.menu) ctx.hide(true);
              else ctx.show(e, file);
            }}
            className="shrink-0 flex items-center justify-center size-11 sm:size-7 rounded-md hover:bg-theme-bg-subtle transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
          >
            <MoreHorizontal size={15} className="text-theme-text-tertiary" />
          </button>
        </div>

        {/* Preview area */}
        <div className="aspect-[16/9] overflow-hidden relative bg-theme-bg-subtle">
          <FileCardPreview preview={cardPreview} icon={FileIcon} />
        </div>

        {/* Meta footer */}
        <div className="px-2.5 py-2">
          <p className="text-11 text-theme-text-tertiary truncate font-serif">
            {meta}
          </p>
        </div>
      </div>

      <FileContextMenu
        menu={ctx.menu}
        menuId={ctx.menuId}
        onClose={ctx.hide}
        file={file}
        onGoToSession={onGoToSession}
        onToggleFavorite={onToggleFavorite}
      />
    </>
  );
}
