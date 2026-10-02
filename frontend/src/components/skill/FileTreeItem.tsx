import { useState } from "react";
import { ChevronDown, FolderOpen, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TreeNode } from "./SkillForm.types";
import { getFileIcon } from "./SkillForm.utils";

export function FileTreeItem({
  node,
  depth,
  activeFileIndex,
  onSelect,
  onRemove,
  canRemove,
}: {
  node: TreeNode;
  depth: number;
  activeFileIndex: number;
  onSelect: (i: number) => void;
  onRemove: (i: number) => void;
  canRemove: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const indent = 10 + depth * 16;

  if (node.type === "folder") {
    return (
      <div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          className="w-full flex items-center gap-1.5 py-[4px] text-13 text-left text-stone-500 dark:text-stone-400 hover:bg-stone-100/80 dark:hover:bg-white/5 transition-colors duration-100 select-none"
          style={{ paddingLeft: `${indent}px`, paddingRight: "8px" }}
        >
          <ChevronDown
            size={12}
            className={`shrink-0 transition-transform duration-150 ${
              expanded ? "" : "-rotate-90"
            }`}
          />
          <FolderOpen
            size={14}
            className="shrink-0 text-stone-400 dark:text-stone-500"
          />
          <span className="truncate">{node.name}</span>
        </button>
        {expanded &&
          node.children.map((child, i) => (
            <FileTreeItem
              key={i}
              node={child}
              depth={depth + 1}
              activeFileIndex={activeFileIndex}
              onSelect={onSelect}
              onRemove={onRemove}
              canRemove={canRemove}
            />
          ))}
      </div>
    );
  }

  const isActive = node.fileIndex === activeFileIndex;
  return (
    <div
      className={`skill-file-tree-row w-full flex items-center gap-2 text-13 text-left group transition-colors duration-100 ${
        isActive
          ? "bg-[var(--theme-primary)]/10 text-[var(--theme-text)] font-medium"
          : "text-stone-600 dark:text-stone-400 hover:bg-stone-100/80 dark:hover:bg-white/5"
      }`}
      style={
        isActive
          ? {
              borderLeft: "2px solid var(--theme-primary)",
              paddingLeft: `${indent}px`,
              paddingRight: "8px",
            }
          : {
              borderLeft: "2px solid transparent",
              paddingLeft: `${indent}px`,
              paddingRight: "8px",
            }
      }
    >
      <button
        type="button"
        onClick={() => node.fileIndex !== undefined && onSelect(node.fileIndex)}
        aria-pressed={isActive}
        data-file-select
        className="flex min-w-0 flex-1 items-center gap-2 py-[5px] text-left focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
      >
        {getFileIcon(node.name)}
        <span className="truncate flex-1" title={node.name}>
          {node.name}
        </span>
      </button>
      {canRemove && node.fileIndex !== undefined && (
        <button
          type="button"
          aria-label={`${t("common.remove")}: ${node.name}`}
          onClick={() => {
            if (node.fileIndex !== undefined) {
              onRemove(node.fileIndex);
            }
          }}
          className="skill-file-remove flex shrink-0 items-center justify-center rounded-lg text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-subtle)] focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
        >
          <X size={10} />
        </button>
      )}
    </div>
  );
}
