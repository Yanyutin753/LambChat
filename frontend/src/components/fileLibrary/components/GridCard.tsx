import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api";
import { getFileTypeInfo } from "../../documents/utils";
import { CodeMirrorViewer } from "../../common/CodeMirrorViewer";
import { useCodePreview } from "../hooks/useCodePreview";
import { useContextMenu } from "../hooks/useContextMenu";
import { buildMeta } from "../utils";
import { FileContextMenu } from "./FileContextMenu";

interface GridCardProps {
  file: RevealedFileItem;
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string) => void;
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
  const isImage = !isProject && file.file_type === "image" && file.url;
  const isCode = !isProject && file.file_type === "code";
  const codePreview = useCodePreview(file);
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
          {isImage ? (
            <img
              src={getFullUrl(file.url!)}
              alt={file.file_name}
              className="max-h-full max-w-full h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
              loading="lazy"
            />
          ) : isCode && codePreview ? (
            <div className="w-full h-full overflow-hidden">
              <CodeMirrorViewer
                value={codePreview}
                filePath={file.file_name}
                lineNumbers={false}
                maxHeight="100%"
                fontSize="11px"
              />
            </div>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <FileIcon
                size={32}
                strokeWidth={1.2}
                className={
                  isProject
                    ? "text-violet-300 dark:text-violet-600"
                    : fileInfo.color || "text-stone-300 dark:text-stone-600"
                }
              />
            </div>
          )}
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
