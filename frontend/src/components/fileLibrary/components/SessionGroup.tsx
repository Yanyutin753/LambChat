import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { RevealedFileCard } from "../RevealedFileCard";
import { VISIBLE_FILES_PER_SESSION } from "../constants";
import type { ViewMode } from "../types";

interface SessionGroupProps {
  sessionName: string;
  sessionId: string;
  files: RevealedFileItem[];
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string) => void;
  onToggleFavorite: (file: RevealedFileItem) => void;
  viewMode: ViewMode;
}

export function SessionGroup({
  sessionName,
  sessionId,
  files,
  onPreview,
  onGoToSession,
  onToggleFavorite,
  viewMode,
}: SessionGroupProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const visibleFiles = expanded
    ? files
    : files.slice(0, VISIBLE_FILES_PER_SESSION);
  const hiddenCount = files.length - VISIBLE_FILES_PER_SESSION;

  const dateLabel = useMemo(() => {
    const d = new Date(files[0]?.created_at);
    if (isNaN(d.getTime())) return "";
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }, [files]);

  return (
    <div className="flex flex-col gap-2.5 md:gap-3">
      {/* Session header */}
      <div className="flex items-center justify-between gap-2 pt-4 md:pt-5">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() => onGoToSession(sessionId)}
            className="min-w-0 truncate text-[14px] md:text-[15px] font-semibold leading-[22px] text-stone-800 dark:text-stone-100 hover:text-stone-900 dark:hover:text-white text-left transition-colors"
          >
            {sessionName}
          </button>
        </div>
        <span className="text-[12px] leading-[18px] text-stone-400 dark:text-stone-500 flex-shrink-0 tabular-nums bg-stone-50 dark:bg-stone-800/60 px-2 py-0.5 rounded-md">
          {dateLabel}
        </span>
      </div>

      {/* Card grid */}
      <div
        className={
          viewMode === "grid"
            ? "grid grid-cols-1 md:grid-cols-3 gap-3 items-start"
            : "flex flex-col gap-2"
        }
      >
        {visibleFiles.map((file) => (
          <RevealedFileCard
            key={file.id}
            file={file}
            onPreview={onPreview}
            onGoToSession={onGoToSession}
            onToggleFavorite={onToggleFavorite}
            viewMode={viewMode}
          />
        ))}
      </div>

      {/* Expand / collapse */}
      {hiddenCount > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 self-start text-[12px] font-medium text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 rounded-lg border border-stone-200/60 dark:border-stone-700/50 bg-stone-50/50 dark:bg-stone-800/30 hover:bg-stone-100 dark:hover:bg-stone-800/60 transition-all duration-150"
        >
          <span>
            {expanded
              ? t("fileLibrary.showLess", "收起")
              : t("fileLibrary.showMore", "还有 {{count}} 个文件", {
                  count: hiddenCount,
                })}
          </span>
          <ChevronDown
            size={13}
            className={`transition-transform duration-200 ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </button>
      )}
    </div>
  );
}
