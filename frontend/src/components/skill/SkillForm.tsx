import { useState, useEffect, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  Maximize2,
  Minimize2,
  X,
  Plus,
  FileText,
  FileCode,
  File,
  ChevronDown,
  FolderOpen,
  Tag,
} from "lucide-react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import { getLangSupport } from "../common/getLangSupport";
import type { SkillResponse, SkillCreate } from "../../types";

interface FileEntry {
  path: string;
  content: string;
}

function getFileIcon(path: string) {
  const name = path.split("/").pop() || path;
  const ext = name.includes(".") ? name.split(".").pop() : "";
  switch (ext?.toLowerCase()) {
    case "md":
      return <FileText size={14} className="text-blue-400 shrink-0" />;
    case "ts":
    case "tsx":
      return <FileCode size={14} className="text-blue-500 shrink-0" />;
    case "js":
    case "jsx":
      return <FileCode size={14} className="text-yellow-500 shrink-0" />;
    case "py":
      return <FileCode size={14} className="text-green-500 shrink-0" />;
    case "json":
      return <FileCode size={14} className="text-yellow-400 shrink-0" />;
    case "yaml":
    case "yml":
      return <FileCode size={14} className="text-pink-400 shrink-0" />;
    default:
      return <File size={14} className="text-stone-400 dark:text-stone-500 shrink-0" />;
  }
}

interface SkillFormProps {
  skill?: SkillResponse | null;
  onSave: (data: SkillCreate) => Promise<boolean>;
  onCancel: () => void;
  isLoading?: boolean;
  onFullscreenChange?: (fullscreen: boolean) => void;
}

const DEFAULT_CONTENT = `---
name: skill-name
description: Describe what this skill does
---

# Skill Name

## Overview
Describe what this skill does.

## When to Use
- When condition 1
- When condition 2

## Instructions
1. Step 1
2. Step 2
3. Step 3

## Examples
Example usage here.
`;

// CodeMirror-based editor with search/replace, line numbers, syntax highlighting
function SkillEditor({
  value,
  onChange,
  className,
  filePath,
}: {
  value: string;
  onChange: (val: string) => void;
  className?: string;
  filePath?: string;
}) {
  const [isDark, setIsDark] = useState(() =>
    typeof document !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : true,
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const extensions = useMemo(() => {
    const langSupport = getLangSupport(undefined, filePath);

    return [
      ...(langSupport ? [langSupport] : []),
      EditorView.lineWrapping,
      EditorView.theme({
        "&": {
          height: "100%",
          fontSize: "0.875rem",
        },
        ".cm-editor": {
          height: "100%",
        },
        ".cm-scroller": {
          overflow: "auto",
        },
        ".cm-content": {
          minHeight: "100%",
        },
      }),
    ];
  }, [filePath]);

  return (
    <div
      className={`${
        className || ""
      } h-full min-h-0 flex flex-col overflow-hidden [&_.cm-theme]:h-full [&_.cm-editor]:h-full [&_.cm-editor]:min-h-0 [&_.cm-scroller]:flex-1 [&_.cm-scroller]:min-h-0 [&_.cm-scroller]:overflow-auto`}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        theme={isDark ? oneDark : undefined}
        extensions={extensions}
        basicSetup={{
          lineNumbers: true,
          highlightActiveLineGutter: true,
          highlightActiveLine: true,
          foldGutter: true,
          searchKeymap: true,
          bracketMatching: true,
          closeBrackets: true,
          indentOnInput: true,
        }}
        className="min-h-0 flex-1"
      />
    </div>
  );
}

// ChatGPT-style toggle switch
function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (val: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer select-none">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-ring)] focus-visible:ring-offset-1 ${
          checked
            ? "bg-[var(--theme-primary)]"
            : "bg-stone-200 dark:bg-stone-700"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        <span
          className={`pointer-events-none inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ${
            checked ? "translate-x-[18px]" : "translate-x-[3px]"
          }`}
        />
      </button>
      <span className="text-sm text-stone-700 dark:text-stone-300">
        {label}
      </span>
    </label>
  );
}

interface TreeNode {
  name: string;
  type: "file" | "folder";
  fileIndex?: number;
  children: TreeNode[];
}

function normalizeTags(input: string): string[] {
  return Array.from(
    new Set(
      input
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  );
}

function escapeYamlString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function buildSkillFrontmatter(
  name: string,
  description: string,
  tags: string[],
): string {
  const tagLines =
    tags.length > 0
      ? ["tags:", ...tags.map((tag) => `  - "${escapeYamlString(tag)}"`)]
      : ["tags: []"];

  return [
    "---",
    `name: "${escapeYamlString(name)}"`,
    `description: "${escapeYamlString(description)}"`,
    ...tagLines,
    "---",
  ].join("\n");
}

function syncSkillMarkdownMetadata(
  content: string,
  name: string,
  description: string,
  tags: string[],
): string {
  const normalizedContent = content.replace(/\r\n/g, "\n");
  const body = normalizedContent.replace(/^---\n[\s\S]*?\n---\n?/, "").trimStart();
  const frontmatter = buildSkillFrontmatter(name, description, tags);

  return body ? `${frontmatter}\n\n${body}` : `${frontmatter}\n`;
}

function buildFileTree(files: FileEntry[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (let i = 0; i < files.length; i++) {
    const path = files[i].path || `untitled-${i}`;
    const parts = path.split("/");
    let current = root;
    for (let j = 0; j < parts.length; j++) {
      const part = parts[j];
      const isFile = j === parts.length - 1;
      let existing = current.find((n) => n.name === part && n.type === (isFile ? "file" : "folder"));
      if (!existing) {
        existing = { name: part, type: isFile ? "file" : "folder", children: [] };
        if (isFile) existing.fileIndex = i;
        current.push(existing);
      } else if (isFile && !existing.fileIndex && existing.fileIndex !== 0) {
        existing.fileIndex = i;
      }
      if (!isFile) {
        current = existing.children;
      }
    }
  }
  // Sort: folders first, then files, alphabetical
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => { if (n.type === "folder") sortNodes(n.children); });
  };
  sortNodes(root);
  return root;
}

function FileTreeItem({
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
            className={`shrink-0 transition-transform duration-150 ${expanded ? "" : "-rotate-90"}`}
          />
          <FolderOpen size={14} className="shrink-0 text-stone-400 dark:text-stone-500" />
          <span className="truncate">{node.name}</span>
        </button>
        {expanded && node.children.map((child, i) => (
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
      style={isActive ? {
        borderLeft: "2px solid var(--theme-primary)",
        paddingLeft: `${indent}px`,
        paddingRight: "8px",
      } : {
        borderLeft: "2px solid transparent",
        paddingLeft: `${indent}px`,
        paddingRight: "8px",
      }}
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

// File tabs — ChatGPT style with pill shape
function FileTabs({
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
            {file.path ? file.path.split("/").pop() || file.path : untitledLabel}
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

export function SkillForm({
  skill,
  onSave,
  onCancel,
  isLoading = false,
  onFullscreenChange,
}: SkillFormProps) {
  const { t } = useTranslation();
  const isEditing = !!skill;

  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [tagsInput, setTagsInput] = useState((skill?.tags ?? []).join(", "));
  const [enabled, setEnabled] = useState(skill?.enabled ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(
    (fs: boolean) => {
      setIsFullscreen(fs);
      onFullscreenChange?.(fs);
    },
    [onFullscreenChange],
  );

  // Files state for multi-file support
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activeFileIndex, setActiveFileIndex] = useState<number>(0);

  // Initialize files from skill
  useEffect(() => {
    if (skill?.files && Object.keys(skill.files).length > 0) {
      const fileEntries = Object.entries(skill.files).map(
        ([path, fileContent]) => ({
          path,
          content: fileContent,
        }),
      );
      // Sort to put SKILL.md first
      fileEntries.sort((a, b) => {
        if (a.path === "SKILL.md") return -1;
        if (b.path === "SKILL.md") return 1;
        return a.path.localeCompare(b.path);
      });
      setFiles(fileEntries);
    } else if (skill?.content) {
      setFiles([{ path: "SKILL.md", content: skill.content }]);
    } else {
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
    }
  }, [skill]);

  // Update form when skill changes (except files, which is handled above)
  useEffect(() => {
    if (skill) {
      setName(skill.name);
      setDescription(skill.description);
      setTagsInput((skill.tags ?? []).join(", "));
      setEnabled(skill.enabled);
    } else {
      setName("");
      setDescription("");
      setTagsInput("");
      setEnabled(true);
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
    }
    setErrors({});
  }, [skill]);

  // Escape key handler to exit fullscreen
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && isFullscreen) {
        toggleFullscreen(false);
      }
    },
    [isFullscreen, toggleFullscreen],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    const normalizedTags = normalizeTags(tagsInput);

    if (!name.trim()) {
      newErrors.name = t("skills.form.validation.nameRequired");
    } else if (
      !/^[\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\-.]+$/.test(
        name.trim(),
      )
    ) {
      newErrors.name = t("skills.form.validation.nameInvalid");
    } else if (name.trim().length > 100) {
      newErrors.name = t("skills.form.validation.nameTooLong");
    }

    if (!description.trim()) {
      newErrors.description = t("skills.form.validation.descriptionRequired");
    }

    if (normalizedTags.some((tag) => tag.length > 30)) {
      newErrors.tags = t("skills.form.validation.tagTooLong");
    }

    const skillMdFile = files.find((f) => f.path === "SKILL.md");
    if (!skillMdFile || !skillMdFile.content.trim()) {
      newErrors.content = t("skills.form.validation.contentRequired");
    }

    const paths = files.map((f) => f.path);
    if (new Set(paths).size !== paths.length) {
      newErrors.files = t("skills.form.validation.duplicateFilePaths");
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!validate()) return;

    const normalizedTags = normalizeTags(tagsInput);
    const filesDict: Record<string, string> = {};
    const synchronizedSkillMd = syncSkillMarkdownMetadata(
      files[activeFileIndex]?.path === "SKILL.md"
        ? files[activeFileIndex]?.content || ""
        : files.find((file) => file.path === "SKILL.md")?.content || DEFAULT_CONTENT,
      name.trim(),
      description.trim(),
      normalizedTags,
    );

    for (const file of files) {
      if (!file.path.trim()) {
        continue;
      }

      filesDict[file.path.trim()] =
        file.path.trim() === "SKILL.md" ? synchronizedSkillMd : file.content;
    }

    if (!filesDict["SKILL.md"]) {
      filesDict["SKILL.md"] = synchronizedSkillMd;
    }

    const data: SkillCreate = {
      name: name.trim(),
      description: description.trim(),
      tags: normalizedTags,
      content: filesDict["SKILL.md"] || "",
      enabled,
      files: filesDict,
    };

    const success = await onSave(data);
    if (success && !isEditing) {
      setName("");
      setDescription("");
      setTagsInput("");
      setEnabled(true);
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
    }
  };

  // File management
  const addFile = () => {
    setFiles([...files, { path: "", content: "" }]);
    setActiveFileIndex(files.length);
  };

  const removeFile = (index: number) => {
    if (files.length <= 1) return;
    const newFiles = files.filter((_, i) => i !== index);
    setFiles(newFiles);
    if (activeFileIndex >= newFiles.length) {
      setActiveFileIndex(newFiles.length - 1);
    }
  };

  const updateFilePath = (index: number, path: string) => {
    const newFiles = [...files];
    newFiles[index] = { ...newFiles[index], path };
    setFiles(newFiles);
  };

  const updateFileContent = (index: number, content: string) => {
    const newFiles = [...files];
    newFiles[index] = { ...newFiles[index], content };
    setFiles(newFiles);
  };

  const removeTag = (targetTag: string) => {
    setTagsInput(
      normalizeTags(tagsInput)
        .filter((tag) => tag !== targetTag)
        .join(", "),
    );
  };

  const formElement = (
    <form
      onSubmit={handleSubmit}
      className={
        isFullscreen
          ? "fixed inset-0 z-[100] flex flex-col bg-[var(--theme-bg)]"
          : "flex-1 flex flex-col min-h-0 gap-4"
      }
    >
      {isFullscreen ? (
        /* ===== Fullscreen layout ===== */
        <>
          {/* Compact top bar */}
          <div className="flex items-center gap-3 px-4 py-2.5 border-b border-[var(--theme-border)] shrink-0 bg-[var(--theme-bg-card)]">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <FolderOpen size={16} className="shrink-0 text-[var(--theme-primary)]" />
              <span className="font-mono text-sm font-semibold text-[var(--theme-text)] truncate">
                {name || t("skills.form.untitled")}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Toggle
                checked={enabled}
                onChange={setEnabled}
                label={t("skills.form.enabled")}
              />
              <button
                type="button"
                onClick={() => toggleFullscreen(false)}
                className="rounded-lg p-1.5 text-stone-400 hover:text-[var(--theme-text)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                title={t("skills.form.exitFullscreen")}
              >
                <Minimize2 size={16} />
              </button>
            </div>
          </div>

          {/* File tabs + path input + editor */}
          <div className="flex flex-1 min-h-0 overflow-y-hidden overflow-x-auto">
            {/* Desktop: VS Code-style file explorer sidebar */}
            <div className="hidden sm:flex flex-col w-52 lg:w-60 shrink-0 border-r border-[var(--theme-border)] bg-[var(--theme-bg-sidebar)]">
              {/* Section header */}
              <div className="flex items-center gap-1 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-400 select-none">
                <ChevronDown size={12} />
                {t("skills.form.files", "Files")}
              </div>
              <div className="flex-1 overflow-y-auto py-0.5">
                {buildFileTree(files).map((node, i) => (
                  <FileTreeItem
                    key={i}
                    node={node}
                    depth={0}
                    activeFileIndex={activeFileIndex}
                    onSelect={setActiveFileIndex}
                    onRemove={removeFile}
                    canRemove={files.length > 1}
                  />
                ))}
              </div>
              <div className="shrink-0 px-2 py-1.5 border-t border-[var(--theme-border)]">
                <button
                  type="button"
                  onClick={addFile}
                  className="w-full flex items-center gap-1.5 rounded-md px-2 py-1 text-[13px] text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-white/5 transition-colors"
                >
                  <Plus size={13} />
                  {t("skills.form.addFile")}
                </button>
              </div>
            </div>

            {/* Right: path input + editor */}
            <div className="flex flex-1 flex-col min-h-0">
              {/* Mobile: horizontal tabs */}
              <div className="flex items-center gap-1 px-2 pt-2 shrink-0 sm:hidden">
                <FileTabs
                  files={files}
                  activeFileIndex={activeFileIndex}
                  onSelect={setActiveFileIndex}
                  onRemove={removeFile}
                  untitledLabel={t("skills.form.untitled")}
                />
                <button
                  type="button"
                  onClick={addFile}
                  className="shrink-0 flex items-center justify-center h-7 w-7 rounded-lg text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  <Plus size={14} />
                </button>
              </div>

              {/* Breadcrumb-style file path */}
              <div className="px-3 sm:px-4 py-2 shrink-0 border-b border-[var(--theme-border)] bg-[var(--theme-bg-card)]">
                <div className="flex items-center gap-1.5">
                  <span className="text-stone-400 dark:text-stone-500 text-xs">{t("skills.form.files")} /</span>
                  <input
                    type="text"
                    value={files[activeFileIndex]?.path || ""}
                    onChange={(e) =>
                      updateFilePath(activeFileIndex, e.target.value)
                    }
                    placeholder={t("skills.form.fileNamePlaceholder")}
                    className="flex-1 bg-transparent font-mono text-xs text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none py-0.5"
                  />
                </div>
              </div>

              {/* Editor area */}
              <div
                className={`flex-1 min-h-0 flex flex-col overflow-y-hidden overflow-x-auto rounded-xl border transition-colors duration-150 ${
                  errors.content
                    ? "border-red-300 dark:border-red-700"
                    : "border-[var(--theme-border)]"
                }`}
              >
                <SkillEditor
                  value={files[activeFileIndex]?.content || ""}
                  onChange={(val) => updateFileContent(activeFileIndex, val)}
                  className="flex-1 min-h-0"
                  filePath={files[activeFileIndex]?.path}
                />
              </div>
            </div>
          </div>

          {/* Fullscreen footer */}
          <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-[var(--theme-border)] shrink-0 bg-[var(--theme-bg-card)]">
            {(errors.content || errors.files) && (
              <span className="text-xs text-red-600 dark:text-red-400">
                {errors.content || errors.files}
              </span>
            )}
            {!errors.content && !errors.files && <span />}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onCancel}
                disabled={isLoading}
                className="rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-2 text-sm text-[var(--theme-text)] hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors duration-150"
              >
                {t("common.cancel")}
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="rounded-lg bg-[var(--theme-primary)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--theme-primary-hover)] disabled:opacity-50 transition-colors duration-150 dark:text-stone-950"
              >
                {isEditing
                  ? t("skills.form.saveChanges")
                  : t("skills.form.createSkill")}
              </button>
            </div>
          </div>
        </>
      ) : (
        /* ===== Normal layout ===== */
        <>
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(18rem,22rem)_minmax(0,1fr)] lg:gap-5">
            {/* Metadata card */}
            <div className="flex min-h-0 flex-col gap-4 lg:sticky lg:top-0">
              <div className="overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm">
                <div className="border-b border-[var(--theme-border)] bg-[var(--theme-bg)]/70 px-4 py-3 sm:px-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--theme-text-secondary)]/80">
                    {t("skills.form.name")}
                  </p>
                  <p className="mt-1 text-sm text-[var(--theme-text-secondary)]">
                    {isEditing
                      ? t("skills.form.nameCannotChange")
                      : t("skills.form.namePlaceholder")}
                  </p>
                </div>

                <div className="space-y-4 px-4 py-4 sm:px-5">
                  <div className="space-y-2">
                    <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                      {t("skills.form.name")}
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        disabled={isEditing}
                        placeholder={t("skills.form.namePlaceholder")}
                        className={`w-full rounded-xl border px-3 py-2 font-mono text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
                          errors.name
                            ? "border-red-300 focus:border-red-400 dark:border-red-700"
                            : "border-[var(--theme-border)] focus:border-[var(--theme-primary)]"
                        } bg-[var(--theme-bg)]`}
                      />
                      {isEditing && (
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-[var(--theme-bg-card)]/80 p-1">
                          <svg className="h-4 w-4 text-stone-400 dark:text-stone-500" viewBox="0 0 16 16" fill="none">
                            <rect x="2" y="2" width="12" height="12" rx="3" stroke="currentColor" stroke-width="1.2"/>
                            <path d="M6 8h4M8 6v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                          </svg>
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                      {t("skills.form.description")}
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder={t("skills.form.descriptionPlaceholder")}
                      rows={4}
                      className={`w-full resize-none rounded-xl border px-3 py-2 text-sm leading-6 text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150 ${
                        errors.description
                          ? "border-red-300 focus:border-red-400 dark:border-red-700"
                          : "border-[var(--theme-border)] focus:border-[var(--theme-primary)]"
                      } bg-[var(--theme-bg)]`}
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                      {t("adminMarketplace.tags")}
                    </label>
                    <div className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3 shadow-sm">
                      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]/80">
                        <Tag size={12} className="text-[var(--theme-primary)]" />
                        {t("adminMarketplace.tags")}
                      </div>
                      <p className="mt-2 text-xs leading-5 text-[var(--theme-text-secondary)]/80">
                        {t("adminMarketplace.tagsHint")}
                      </p>
                      <input
                        type="text"
                        value={tagsInput}
                        onChange={(e) => setTagsInput(e.target.value)}
                        placeholder={t("adminMarketplace.tagsPlaceholder")}
                        className={`mt-3 w-full rounded-xl border px-3 py-2 text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150 ${
                          errors.tags
                            ? "border-red-300 focus:border-red-400 dark:border-red-700"
                            : "border-[var(--theme-border)] focus:border-[var(--theme-primary)]"
                        } bg-[var(--theme-bg-card)]`}
                      />
                      <div className="mt-3 flex flex-wrap gap-2">
                        {normalizeTags(tagsInput).map((tag) => (
                          <span
                            key={tag}
                            className="skill-tag-chip skill-tag-chip--active"
                          >
                            {tag}
                            <button
                              type="button"
                              onClick={() => removeTag(tag)}
                              className="skill-tag-chip-remove"
                              aria-label={`Remove tag ${tag}`}
                            >
                              <X size={11} />
                            </button>
                          </span>
                        ))}
                        {normalizeTags(tagsInput).length === 0 && (
                          <span className="text-xs text-[var(--theme-text-secondary)]/80">
                            {t("adminMarketplace.tagsPlaceholder")}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-3">
                    <div className="min-w-0 pr-3">
                      <p className="text-sm font-medium text-[var(--theme-text)]">
                        {t("skills.form.enabled")}
                      </p>
                      <p className="mt-1 text-xs text-[var(--theme-text-secondary)]">
                        {enabled ? "Skill is available to use" : "Skill is disabled for now"}
                      </p>
                    </div>
                    <div className="shrink-0">
                      <Toggle
                        checked={enabled}
                        onChange={setEnabled}
                        label={t("skills.form.enabled")}
                      />
                    </div>
                  </div>
                </div>

                {(errors.name || errors.description || errors.tags || isEditing) && (
                  <div className="border-t border-[var(--theme-border)] bg-[var(--theme-bg)]/70 px-4 py-3 sm:px-5">
                    {errors.name && (
                      <p className="text-xs text-red-500">{errors.name}</p>
                    )}
                    {errors.description && (
                      <p className="mt-1 text-xs text-red-500">{errors.description}</p>
                    )}
                    {errors.tags && (
                      <p className="mt-1 text-xs text-red-500">{errors.tags}</p>
                    )}
                    {!errors.name && !errors.description && !errors.tags && isEditing && (
                      <p className="text-[11px] text-stone-400 dark:text-stone-500">
                        {t("skills.form.nameCannotChange")}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Editor area */}
            <div className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm">
              {/* File tabs + add + fullscreen */}
              <div className="shrink-0 border-b border-[var(--theme-border)] bg-[var(--theme-bg)]/70 px-3 py-3 sm:px-4">
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--theme-text-secondary)]/80">
                        {t("skills.form.files", "Files")}
                      </p>
                      <p className="mt-1 text-sm text-[var(--theme-text-secondary)]">
                        Edit the selected file and manage extra files here.
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={addFile}
                        className="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-stone-400 transition-colors duration-150 hover:border-[var(--theme-border)] hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                        title={t("skills.form.addFile", "Add file")}
                      >
                        <Plus size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleFullscreen(true)}
                        className="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-stone-400 transition-colors duration-150 hover:border-[var(--theme-border)] hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                        title="Fullscreen editor"
                      >
                        <Maximize2 size={15} />
                      </button>
                    </div>
                  </div>

                  <div className="min-w-0 overflow-hidden rounded-2xl bg-[var(--theme-bg-card)]/50 px-1 py-1">
                    <FileTabs
                      files={files}
                      activeFileIndex={activeFileIndex}
                      onSelect={setActiveFileIndex}
                      onRemove={removeFile}
                      untitledLabel={t("skills.form.untitled")}
                    />
                  </div>

                  <div className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-3 py-2.5">
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]/80">
                      File path
                    </label>
                    <input
                      type="text"
                      value={files[activeFileIndex]?.path || ""}
                      onChange={(e) =>
                        updateFilePath(activeFileIndex, e.target.value)
                      }
                      placeholder="File path (e.g., SKILL.md)"
                      className="w-full bg-transparent font-mono text-xs text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Editor */}
              <div className="flex-1 min-h-0 p-3 sm:p-4">
                <div
                  className={`flex h-full min-h-[18rem] sm:min-h-[24rem] flex-col overflow-hidden rounded-2xl border bg-[var(--theme-bg)] transition-colors duration-150 ${
                    errors.content
                      ? "border-red-300 dark:border-red-700"
                      : "border-[var(--theme-border)]"
                  }`}
                >
                  <SkillEditor
                    value={files[activeFileIndex]?.content || ""}
                    onChange={(val) => updateFileContent(activeFileIndex, val)}
                    className="flex-1 min-h-0"
                    filePath={files[activeFileIndex]?.path}
                  />
                </div>
                {(errors.content || errors.files) && (
                  <p className="mt-2 text-xs text-red-500">
                    {errors.content || errors.files}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Bottom action bar */}
          <div className="sticky bottom-0 shrink-0 flex items-center justify-end gap-2 border-t border-[var(--theme-border)] bg-[var(--theme-bg)]/95 px-1 pt-3 backdrop-blur">
            <button
              type="button"
              onClick={onCancel}
              disabled={isLoading}
              className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-2 text-sm text-[var(--theme-text)] hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors duration-150"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="rounded-xl bg-[var(--theme-primary)] px-5 py-2 text-sm font-medium text-white hover:bg-[var(--theme-primary-hover)] disabled:opacity-50 transition-colors duration-150 dark:text-stone-950"
            >
              {isEditing
                ? t("skills.form.saveChanges")
                : t("skills.form.createSkill")}
            </button>
          </div>
        </>
      )}
    </form>
  );

  if (isFullscreen) {
    return createPortal(formElement, document.body);
  }

  return formElement;
}
