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
  const cardPreview = buildFileCardPreview(file);
  const meta = buildMeta(file, t);
  const ctx = useContextMenu();

  return (
    <>
      <div
        onClick={() => onPreview(file)}
        onContextMenu={(e) => ctx.show(e, file)}
        className="group/card relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-stone-200/60 dark:border-stone-700/40 bg-white dark:bg-stone-900/50 transition-all duration-200 hover:shadow-lg hover:shadow-stone-900/[0.06] dark:hover:shadow-black/20 hover:border-stone-300/80 dark:hover:border-stone-600/50"
      >
        {/* File header */}
        <div className="flex items-center gap-2 px-2.5 py-2.5 border-b border-stone-100 dark:border-stone-800/80">
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
            <p
              className="text-[13px] text-stone-800 dark:text-stone-100 truncate leading-tight"
              title={file.file_name}
            >
              {file.file_name}
            </p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              ctx.show(e, file);
            }}
            className="shrink-0 flex items-center justify-center w-7 h-7 rounded-md hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <MoreHorizontal
              size={15}
              className="text-stone-400 dark:text-stone-500"
            />
          </button>
        </div>

        {/* Preview area */}
        <div className="aspect-[16/9] overflow-hidden relative bg-stone-50/80 dark:bg-stone-800/20">
          <FileCardPreview preview={cardPreview} icon={FileIcon} />
        </div>

        {/* Meta footer */}
        <div className="px-2.5 py-2">
          <p className="text-[11px] text-stone-400 dark:text-stone-500 truncate">
            {meta}
          </p>
        </div>
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
