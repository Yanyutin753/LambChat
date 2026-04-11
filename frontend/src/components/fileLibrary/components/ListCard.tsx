import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api";
import { getFileTypeInfo } from "../../documents/utils";
import { useContextMenu } from "../hooks/useContextMenu";
import { buildMeta } from "../utils";
import { FileContextMenu } from "./FileContextMenu";

interface ListCardProps {
  file: RevealedFileItem;
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string) => void;
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
  const isProject = file.file_type === "project";
  const isImage = !isProject && file.file_type === "image" && file.url;
  const meta = buildMeta(file, t);
  const ctx = useContextMenu();

  return (
    <>
      <div
        onClick={() => onPreview(file)}
        onContextMenu={(e) => ctx.show(e, file)}
        className="group/card relative flex items-center gap-3.5 px-4 py-3 rounded-xl bg-white dark:bg-stone-900/40 border border-stone-200/60 dark:border-stone-700/40 cursor-pointer select-none transition-all duration-150 hover:bg-stone-50 dark:hover:bg-stone-800/30 hover:border-stone-300/80 dark:hover:border-stone-600/50 hover:shadow-sm hover:shadow-stone-900/[0.04] dark:hover:shadow-black/10"
      >
        {/* Icon / thumbnail */}
        <div className="shrink-0">
          {isImage ? (
            <div className="w-10 h-10 rounded-lg overflow-hidden ring-1 ring-stone-200/50 dark:ring-stone-700/40">
              <img
                src={getFullUrl(file.url!)}
                alt={file.file_name}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            </div>
          ) : (
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                isProject
                  ? "bg-violet-50 dark:bg-violet-500/10 ring-1 ring-violet-200/50 dark:ring-violet-500/20"
                  : fileInfo.bg
              }`}
            >
              <FileIcon
                size={17}
                className={
                  isProject
                    ? "text-violet-500 dark:text-violet-400"
                    : fileInfo.color
                }
              />
            </div>
          )}
        </div>

        {/* Name + meta */}
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-medium text-stone-800 dark:text-stone-200 truncate leading-snug">
            {file.file_name}
          </p>
          <p className="mt-0.5 text-[11px] text-stone-400 dark:text-stone-500 truncate">
            {meta}
          </p>
        </div>

        {/* More button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            ctx.show(e, file);
          }}
          className="shrink-0 p-1.5 rounded-md text-stone-300 dark:text-stone-600 hover:text-stone-500 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800/60 transition-all"
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
