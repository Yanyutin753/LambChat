import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useEffect, useRef } from "react";
import type { FileEntry } from "./SkillForm.types";
import { getFileIcon } from "./SkillForm.utils";

export function FileTabs({
  files,
  activeFileIndex,
  onSelect,
  onRemove,
  untitledLabel,
}: {
  files: FileEntry[];
  activeFileIndex: number;
  onSelect: (i: number) => void;
  onRemove: (i: number) => void;
  untitledLabel: string;
}) {
  const { t } = useTranslation();
  const tabsRef = useRef<HTMLDivElement>(null);
  const activePath = files[activeFileIndex]?.path;
  useEffect(() => {
    if (tabsRef.current?.getClientRects().length) {
      tabsRef.current
        .querySelector<HTMLElement>('[aria-pressed="true"]')
        ?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [activeFileIndex, activePath]);
  return (
    <div
      ref={tabsRef}
      className="flex items-center gap-1 overflow-x-auto scrollbar-none px-1"
    >
      {files.map((file, index) => (
        <div
          key={index}
          className={`skill-file-tab group flex shrink-0 items-center rounded-lg text-12 font-medium whitespace-nowrap transition-colors duration-150 ${
            activeFileIndex === index
              ? "bg-[var(--theme-bg-subtle)] text-[var(--theme-text)] shadow-sm"
              : "text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
          }`}
        >
          <button
            type="button"
            onClick={() => onSelect(index)}
            aria-pressed={activeFileIndex === index}
            data-file-select
            aria-label={file.path || untitledLabel}
            title={file.path || untitledLabel}
            className="flex min-w-0 items-center gap-1.5 rounded-lg px-3 py-1.5 focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
          >
            {getFileIcon(file.path || "untitled")}
            <span className="max-w-[120px] sm:max-w-[200px] truncate">
              {file.path
                ? file.path.split("/").pop() || file.path
                : untitledLabel}
            </span>
          </button>
          {files.length > 1 && (
            <button
              type="button"
              aria-label={`${t("common.remove")}: ${file.path || untitledLabel}`}
              onClick={() => onRemove(index)}
              className="skill-file-remove flex shrink-0 items-center justify-center rounded-lg text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-subtle)] focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
            >
              <X size={10} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
