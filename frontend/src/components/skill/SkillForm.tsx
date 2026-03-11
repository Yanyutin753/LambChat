import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
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

export function SkillForm({
  skill,
  onSave,
  onCancel,
  isLoading = false,
  isAdmin = false,
}: SkillFormProps) {
  const { t } = useTranslation();
  const isEditing = !!skill;

  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [enabled, setEnabled] = useState(skill?.enabled ?? true);
  const [isSystem, setIsSystem] = useState(skill?.is_system ?? false);
  const [errors, setErrors] = useState<Record<string, string>>({});

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
      // Don't set content here, it's handled by files initialization
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

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = t("skills.form.validation.nameRequired");
    } else if (!/^[\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\-.]+$/.test(name.trim())) {
      // Allow: letters, numbers, underscores, Chinese, Japanese (Hiragana/Katakana), Korean, hyphens, dots
      newErrors.name = t("skills.form.validation.nameInvalid");
    } else if (name.trim().length > 100) {
      newErrors.name = t("skills.form.validation.nameTooLong");
    }

    if (!description.trim()) {
      newErrors.description = t("skills.form.validation.descriptionRequired");
    }

    // Validate that SKILL.md exists and has content
    const skillMdFile = files.find((f) => f.path === "SKILL.md");
    if (!skillMdFile || !skillMdFile.content.trim()) {
      newErrors.content = t("skills.form.validation.contentRequired");
    }

    // Validate all file paths are unique
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

    // Build files dict from file entries
    const filesDict: Record<string, string> = {};
    for (const file of files) {
      if (file.path.trim()) {
        filesDict[file.path.trim()] = file.content;
      }
    }

    // Get SKILL.md content for backward compatibility
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
      // Reset form on successful creation
      setName("");
      setDescription("");
      setEnabled(true);
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
    }
  };

  // File management functions
  const addFile = () => {
    setFiles([...files, { path: "", content: "" }]);
    setActiveFileIndex(files.length);
  };

  const removeFile = (index: number) => {
    if (files.length <= 1) return; // Keep at least one file
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

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Name */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
          {t("skills.form.name")}
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isEditing}
          placeholder={t("skills.form.namePlaceholder")}
          className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
            errors.name
              ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
              : ""
          }`}
        />
        {errors.name && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.name}
          </p>
        )}
        {isEditing && (
          <p className="mt-1 text-xs text-gray-500 dark:text-stone-500">
            {t("skills.form.nameCannotChange")}
          </p>
        )}
      </div>

      {/* Description */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
          {t("skills.form.description")}
        </label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("skills.form.descriptionPlaceholder")}
          className={`w-full rounded-lg border px-3 py-2 text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
            errors.description
              ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
              : ""
          }`}
        />
        {errors.description && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.description}
          </p>
        )}
      </div>

      {/* Files */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {t("skills.form.content")}
          </label>
          <button
            type="button"
            onClick={addFile}
            className="whitespace-nowrap text-xs text-stone-600 hover:text-stone-800 dark:text-amber-500 dark:hover:text-amber-400"
          >
            + Add File
          </button>
        </div>

        {/* File tabs */}
        <div className="mb-2 flex flex-wrap gap-1 border-b border-gray-200 dark:border-stone-700">
          {files.map((file, index) => (
            <div
              key={index}
              className={`flex items-center gap-1 rounded-t-lg border-b-2 px-3 py-1.5 text-sm ${
                activeFileIndex === index
                  ? "border-stone-500 bg-stone-50 text-stone-700 dark:border-amber-500 dark:bg-stone-800 dark:text-amber-400"
                  : "border-transparent text-gray-500 hover:bg-gray-50 dark:text-stone-400 dark:hover:bg-stone-800"
              }`}
            >
              <button
                type="button"
                onClick={() => setActiveFileIndex(index)}
                className="max-w-[120px] truncate"
                title={file.path || "Untitled"}
              >
                {file.path || "Untitled"}
              </button>
              {files.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="ml-1 text-red-500 hover:text-red-700"
                  title="Remove file"
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>

        {/* File path input */}
        <div className="mb-2">
          <input
            type="text"
            value={files[activeFileIndex]?.path || ""}
            onChange={(e) => updateFilePath(activeFileIndex, e.target.value)}
            placeholder="File path (e.g., SKILL.md, templates/main.py)"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
          />
        </div>

        {/* File content editor */}
        <textarea
          value={files[activeFileIndex]?.content || ""}
          onChange={(e) => updateFileContent(activeFileIndex, e.target.value)}
          rows={12}
          placeholder={t("skills.form.contentPlaceholder")}
          className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
            errors.content
              ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
              : ""
          }`}
        />
        {errors.content && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.content}
          </p>
        )}
        {errors.files && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.files}
          </p>
        )}
      </div>

      {/* Enabled */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="skill-enabled"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-stone-600 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800 dark:text-amber-600 dark:focus:ring-amber-500"
        />
        <label
          htmlFor="skill-enabled"
          className="text-sm text-gray-700 dark:text-stone-300"
        >
          {t("skills.form.enabled")}
        </label>
      </div>

      {/* System Skill (Admin only) */}
      {isAdmin && (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="skill-system"
            checked={isSystem}
            onChange={(e) => setIsSystem(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-stone-600 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800 dark:text-amber-600 dark:focus:ring-amber-500"
          />
          <label
            htmlFor="skill-system"
            className="text-sm text-gray-700 dark:text-stone-300"
          >
            {isEditing
              ? t("skills.form.systemSkill")
              : t("skills.form.createAsSystem")}
          </label>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-stone-700 dark:text-gray-200 dark:hover:bg-stone-800"
        >
          {t("common.cancel")}
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="flex items-center gap-1 rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white hover:bg-stone-900 disabled:opacity-50 dark:bg-amber-600 dark:hover:bg-amber-700"
        >
          {isEditing
            ? t("skills.form.saveChanges")
            : t("skills.form.createSkill")}
        </button>
      </div>
    </form>
  );
}
