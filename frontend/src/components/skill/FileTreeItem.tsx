import { useState } from "react";
import { ChevronDown, FolderOpen, X } from "lucide-react";
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
  const [expanded, setExpanded] = useState(true);
  const indent = 10 + depth * 16;

  if (node.type === "folder") {
    return (
      <div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-1.5 py-[4px] text-[13px] text-left text-stone-500 dark:text-stone-400 hover:bg-stone-100/80 dark:hover:bg-white/5 transition-colors duration-100 select-none"
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
    <button
      type="button"
      onClick={() => node.fileIndex !== undefined && onSelect(node.fileIndex)}
      className={`w-full flex items-center gap-2 py-[5px] text-[13px] text-left group transition-colors duration-100 ${
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
      {getFileIcon(node.name)}
      <span className="truncate flex-1" title={node.name}>
        {node.name}
      </span>
      {canRemove && node.fileIndex !== undefined && (
        <span
          role="button"
          onClick={(e) => {
            e.stopPropagation();
            if (node.fileIndex !== undefined) {
              onRemove(node.fileIndex);
            }
          }}
          className="hidden group-hover:inline-flex items-center justify-center h-4 w-4 rounded hover:bg-stone-300/60 dark:hover:bg-stone-600/60 text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
        >
          <X size={10} />
        </span>
      )}
    </button>
  );
}
