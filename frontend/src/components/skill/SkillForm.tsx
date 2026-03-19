import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Maximize2, Minimize2, X, Plus } from "lucide-react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { oneDark } from "@codemirror/theme-one-dark";
import { getLangSupport } from "../common/CodeMirrorViewer";
import type { SkillResponse, SkillCreate } from "../../types";

interface FileEntry {
  path: string;
  content: string;
}

interface SkillFormProps {
  skill?: SkillResponse | null;
  onSave: (data: SkillCreate, isSystem: boolean) => Promise<boolean>;
  onCancel: () => void;
  isLoading?: boolean;
  isAdmin?: boolean;
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

  return (
    <div
      className={`${
        className || ""
      } [&_.cm-editor]:h-full [&_.cm-scroller]:!overflow-auto`}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        theme={isDark ? oneDark : undefined}
        extensions={[
          getLangSupport(filePath) ?? [],
          EditorView.theme({
            "&": { whiteSpace: "pre" },
            ".cm-content": { whiteSpace: "pre" },
            ".cm-line": { whiteSpace: "pre" },
          }),
        ]}
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
        className="h-full"
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

// File tabs — ChatGPT style with pill shape
function FileTabs({
  files,
  activeFileIndex,
  onSelect,
  onRemove,
}: {
  files: FileEntry[];
  activeFileIndex: number;
  onSelect: (i: number) => void;
  onRemove: (i: number) => void;
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
          title={file.path || "Untitled"}
        >
          <span className="max-w-[120px] sm:max-w-[200px] truncate">
            {file.path ? file.path.split("/").pop() || file.path : "Untitled"}
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
  isAdmin = false,
  onFullscreenChange,
}: SkillFormProps) {
  const { t } = useTranslation();
  const isEditing = !!skill;

  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [enabled, setEnabled] = useState(skill?.enabled ?? true);
  const [isSystem, setIsSystem] = useState(skill?.is_system ?? false);
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
      setEnabled(skill.enabled);
      setIsSystem(skill.is_system);
    } else {
      setName("");
      setDescription("");
      setEnabled(true);
      setIsSystem(false);
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

    const skillMdFile = files.find((f) => f.path === "SKILL.md");
    if (!skillMdFile || !skillMdFile.content.trim()) {
      newErrors.content = t("skills.form.validation.contentRequired");
    }

    const paths = files.map((f) => f.path);
    if (new Set(paths).size !== paths.length) {
      newErrors.files = "Duplicate file paths are not allowed";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const filesDict: Record<string, string> = {};
    for (const file of files) {
      if (file.path.trim()) {
        filesDict[file.path.trim()] = file.content;
      }
    }

    const skillMdContent = filesDict["SKILL.md"] || "";

    const data: SkillCreate = {
      name: name.trim(),
      description: description.trim(),
      content: skillMdContent,
      enabled,
      source: isSystem ? "builtin" : "manual",
      files: filesDict,
    };

    const success = await onSave(data, isSystem);
    if (success && !isEditing) {
      setName("");
      setDescription("");
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
          <div className="px-4 py-3 border-b border-[var(--theme-border)] shrink-0 bg-[var(--theme-bg-card)]">
            <div className="flex items-center justify-between gap-3">
              <div className="flex flex-col min-w-0 flex-1">
                <span className="font-mono text-lg font-semibold text-[var(--theme-text)] truncate">
                  {name || "Untitled"}
                </span>
                <span className="text-xs text-[var(--theme-text-secondary)] truncate mt-0.5">
                  {description}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsFullscreen(false)}
                  className="rounded-lg p-1.5 text-stone-400 hover:text-[var(--theme-text)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                  title="Exit fullscreen"
                >
                  <Minimize2 size={16} />
                </button>
              </div>
            </div>
            <div className="flex items-center gap-4 mt-2.5">
              <Toggle
                checked={enabled}
                onChange={setEnabled}
                label={t("skills.form.enabled")}
              />
              {isAdmin && (
                <Toggle
                  checked={isSystem}
                  onChange={setIsSystem}
                  label={t("skills.form.systemSkill")}
                />
              )}
            </div>
          </div>

          {/* File tabs + path input + editor */}
          <div className="flex flex-1 min-h-0 overflow-y-hidden overflow-x-auto">
            {/* Desktop: left sidebar file list */}
            <div className="hidden sm:flex flex-col w-48 lg:w-56 shrink-0 border-r border-[var(--theme-border)] bg-[var(--theme-primary-light)]">
              <div className="flex-1 overflow-y-auto py-1.5">
                {files.map((file, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => setActiveFileIndex(index)}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left group transition-colors duration-150 ${
                      activeFileIndex === index
                        ? "bg-[var(--theme-bg-card)] text-[var(--theme-text)] font-medium border-r-2 border-[var(--theme-primary)]"
                        : "text-stone-500 hover:bg-stone-100/80 dark:text-stone-400 dark:hover:bg-stone-800/60"
                    }`}
                  >
                    <span
                      className="truncate flex-1"
                      title={file.path || "Untitled"}
                    >
                      {file.path
                        ? file.path.split("/").pop() || file.path
                        : "Untitled"}
                    </span>
                    {files.length > 1 && (
                      <span
                        role="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(index);
                        }}
                        className="hidden group-hover:inline-flex items-center justify-center h-4 w-4 rounded hover:bg-stone-200 dark:hover:bg-stone-600 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
                      >
                        <X size={10} />
                      </span>
                    )}
                  </button>
                ))}
              </div>
              <div className="shrink-0 px-2 py-2 border-t border-[var(--theme-border)]">
                <button
                  type="button"
                  onClick={addFile}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  <Plus size={12} />
                  {t("skills.form.addFile", "Add file")}
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
                />
                <button
                  type="button"
                  onClick={addFile}
                  className="shrink-0 flex items-center justify-center h-7 w-7 rounded-lg text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  <Plus size={14} />
                </button>
              </div>

              {/* File path input */}
              <div className="px-3 sm:px-4 py-2 shrink-0">
                <input
                  type="text"
                  value={files[activeFileIndex]?.path || ""}
                  onChange={(e) =>
                    updateFilePath(activeFileIndex, e.target.value)
                  }
                  placeholder="File path"
                  className="w-full rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-3 py-1.5 font-mono text-xs text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:border-[var(--theme-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150"
                />
              </div>

              {/* Editor area */}
              <div
                className={`mx-3 sm:mx-4 mb-3 rounded-xl border overflow-y-hidden overflow-x-auto flex-1 min-h-0 flex flex-col transition-colors duration-150 ${
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
          {/* Metadata: Name + Description */}
          <div className="shrink-0 space-y-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-[var(--theme-text)]">
                {t("skills.form.name")}
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isEditing}
                placeholder={t("skills.form.namePlaceholder")}
                className={`w-full rounded-xl border px-3.5 py-2.5 font-mono text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
                  errors.name
                    ? "border-red-300 focus:border-red-400 dark:border-red-700"
                    : "border-[var(--theme-border)] focus:border-[var(--theme-primary)]"
                } bg-[var(--theme-bg-card)]`}
              />
              {errors.name && (
                <p className="mt-1 text-xs text-red-500">{errors.name}</p>
              )}
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-[var(--theme-text)]">
                {t("skills.form.description")}
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("skills.form.descriptionPlaceholder")}
                className={`w-full rounded-xl border px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150 ${
                  errors.description
                    ? "border-red-300 focus:border-red-400 dark:border-red-700"
                    : "border-[var(--theme-border)] focus:border-[var(--theme-primary)]"
                } bg-[var(--theme-bg-card)]`}
              />
              {errors.description && (
                <p className="mt-1 text-xs text-red-500">
                  {errors.description}
                </p>
              )}
            </div>
          </div>

          {/* Settings row */}
          <div className="shrink-0 flex flex-wrap items-center gap-x-5 gap-y-2">
            <Toggle
              checked={enabled}
              onChange={setEnabled}
              label={t("skills.form.enabled")}
            />
            {isAdmin && (
              <Toggle
                checked={isSystem}
                onChange={setIsSystem}
                label={
                  isEditing
                    ? t("skills.form.systemSkill")
                    : t("skills.form.createAsSystem")
                }
              />
            )}
            {isEditing && (
              <span className="text-xs text-stone-400 dark:text-stone-500">
                {t("skills.form.nameCannotChange")}
              </span>
            )}
          </div>

          {/* Editor area */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* File tabs + add + fullscreen */}
            <div className="shrink-0 flex items-center justify-between gap-2 pb-2">
              <FileTabs
                files={files}
                activeFileIndex={activeFileIndex}
                onSelect={setActiveFileIndex}
                onRemove={removeFile}
              />
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={addFile}
                  className="flex items-center justify-center h-7 w-7 rounded-lg text-stone-400 hover:text-[var(--theme-text)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors duration-150"
                  title={t("skills.form.addFile", "Add file")}
                >
                  <Plus size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => toggleFullscreen(true)}
                  className="flex items-center justify-center h-7 w-7 rounded-lg text-stone-400 hover:text-[var(--theme-text)] hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors duration-150"
                  title="Fullscreen editor"
                >
                  <Maximize2 size={14} />
                </button>
              </div>
            </div>

            {/* File path input */}
            <div className="shrink-0 pb-2">
              <input
                type="text"
                value={files[activeFileIndex]?.path || ""}
                onChange={(e) =>
                  updateFilePath(activeFileIndex, e.target.value)
                }
                placeholder="File path (e.g., SKILL.md)"
                className="w-full rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-3 py-1.5 font-mono text-xs text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:border-[var(--theme-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 transition-all duration-150"
              />
            </div>

            {/* Editor */}
            <div
              className={`flex-1 min-h-[8rem] sm:min-h-[12rem] rounded-xl border overflow-y-hidden overflow-x-auto flex flex-col transition-colors duration-150 ${
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
              <p className="mt-1.5 text-xs text-red-500">
                {errors.content || errors.files}
              </p>
            )}
          </div>

          {/* Bottom action bar */}
          <div className="shrink-0 flex items-center justify-end gap-2 pt-3 border-t border-[var(--theme-border)]">
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
