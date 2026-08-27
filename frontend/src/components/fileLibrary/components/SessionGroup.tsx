import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { RevealedFileCard } from "../RevealedFileCard";
import { VISIBLE_FILES_PER_SESSION } from "../constants";
import { getSessionNavigationTarget } from "../utils";
import { formatDate, parseDate } from "../../../utils/datetime";
import type { ViewMode } from "../types";

interface SessionGroupProps {
  sessionName: string;
  sessionId: string;
  files: RevealedFileItem[];
  onPreview: (file: RevealedFileItem) => void;
  onGoToSession: (sessionId: string, file?: RevealedFileItem) => void;
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
  const navigationTarget = getSessionNavigationTarget(files);
  const visibleFiles = expanded
    ? files
    : files.slice(0, VISIBLE_FILES_PER_SESSION);
  const hiddenCount = files.length - VISIBLE_FILES_PER_SESSION;

  const dateLabel = useMemo(() => {
    const created = files[0]?.created_at;
    if (!created) return "";
    const d = parseDate(created);
    if (isNaN(d.getTime())) return "";
    return formatDate(created);
  }, [files]);

  return (
    <div className="flex flex-col gap-2.5 @md:gap-3">
      {/* Session header */}
      <div className="flex items-center justify-between gap-2 pt-4 @md:pt-5 font-serif">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() =>
              onGoToSession(sessionId, navigationTarget ?? undefined)
            }
            className="min-w-0 truncate text-[14px] @md:text-[15px] font-semibold leading-[22px] text-theme-text hover:text-theme-text text-left transition-colors"
          >
            {sessionName}
          </button>
        </div>
        <span className="text-[12px] leading-[18px] text-theme-text-tertiary flex-shrink-0 tabular-nums bg-theme-bg-subtle px-2 py-0.5 rounded-md">
          {dateLabel}
        </span>
      </div>

      {/* Card grid */}
      <div
        className={
          viewMode === "grid"
            ? "grid gap-3 items-start auto-grid-cols"
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
          className="flex items-center gap-1.5 px-3 py-1.5 self-start text-[12px] font-medium text-theme-text-tertiary hover:text-theme-text-secondary rounded-lg border border-theme-border bg-theme-bg-subtle hover:bg-theme-bg-subtle transition-all duration-150"
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
