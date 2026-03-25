import { X } from "lucide-react";
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
  return (
    <div className="flex items-center gap-1 overflow-x-auto scrollbar-none px-1">
      {files.map((file, index) => (
        <button
          key={index}
          type="button"
          onClick={() => onSelect(index)}
          className={`group flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all duration-150 ${
            activeFileIndex === index
              ? "bg-[var(--theme-primary-light)] text-[var(--theme-text)] shadow-sm"
              : "text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
          }`}
          title={file.path || untitledLabel}
        >
          {getFileIcon(file.path || "untitled")}
          <span className="max-w-[120px] sm:max-w-[200px] truncate">
            {file.path
              ? file.path.split("/").pop() || file.path
              : untitledLabel}
          </span>
          {files.length > 1 && (
            <span
              role="button"
              onClick={(e) => {
                e.stopPropagation();
                onRemove(index);
              }}
              className="hidden group-hover:inline-flex items-center justify-center h-3.5 w-3.5 rounded-full hover:bg-stone-300/60 dark:hover:bg-stone-600/60 text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
            >
              <X size={10} />
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
