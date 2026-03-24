import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { sanitizeSkillName } from "../../utils/skillFilters";
import { normalizeTags, syncSkillMarkdownMetadata } from "./SkillForm.utils";
import { DEFAULT_CONTENT } from "./SkillForm.types";
import type { SkillFormProps, FileEntry } from "./SkillForm.types";
import { SkillFormFullscreen } from "./SkillFormFullscreen";
import { SkillFormNormal } from "./SkillFormNormal";

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

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activeFileIndex, setActiveFileIndex] = useState<number>(0);

  const toggleFullscreen = useCallback(
    (fs: boolean) => {
      setIsFullscreen(fs);
      onFullscreenChange?.(fs);
    },
    [onFullscreenChange],
  );

  useEffect(() => {
    if (skill?.files && Object.keys(skill.files).length > 0) {
      const fileEntries = Object.entries(skill.files).map(
        ([path, content]) => ({ path, content }),
      );
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

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isFullscreen) toggleFullscreen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isFullscreen, toggleFullscreen]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    const tags = normalizeTags(tagsInput);

    if (!name.trim()) {
      newErrors.name = t("skills.form.validation.nameRequired");
    } else if (name.trim().length > 100) {
      newErrors.name = t("skills.form.validation.nameTooLong");
    }
    if (!description.trim()) {
      newErrors.description = t("skills.form.validation.descriptionRequired");
    }
    if (tags.some((tag) => tag.length > 30)) {
      newErrors.tags = t("skills.form.validation.tagTooLong");
    }
    const skillMd = files.find((f) => f.path === "SKILL.md");
    if (!skillMd || !skillMd.content.trim()) {
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

    const tags = normalizeTags(tagsInput);
    const filesDict: Record<string, string> = {};
    const synced = syncSkillMarkdownMetadata(
      files[activeFileIndex]?.path === "SKILL.md"
        ? files[activeFileIndex]?.content || ""
        : files.find((f) => f.path === "SKILL.md")?.content || DEFAULT_CONTENT,
      name.trim(),
      description.trim(),
      tags,
    );

    for (const file of files) {
      if (!file.path.trim()) continue;
      filesDict[file.path.trim()] =
        file.path.trim() === "SKILL.md" ? synced : file.content;
    }
    if (!filesDict["SKILL.md"]) filesDict["SKILL.md"] = synced;

    const data = {
      name: sanitizeSkillName(name.trim()),
      description: description.trim(),
      tags,
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

  const addFile = () => {
    setFiles([...files, { path: "", content: "" }]);
    setActiveFileIndex(files.length);
  };

  const removeFile = (index: number) => {
    if (files.length <= 1) return;
    const next = files.filter((_, i) => i !== index);
    setFiles(next);
    if (activeFileIndex >= next.length) setActiveFileIndex(next.length - 1);
  };

  const updateFilePath = (index: number, path: string) => {
    const next = [...files];
    next[index] = { ...next[index], path };
    setFiles(next);
  };

  const updateFileContent = (index: number, content: string) => {
    const next = [...files];
    next[index] = { ...next[index], content };
    setFiles(next);
  };

  const removeTag = (targetTag: string) => {
    setTagsInput(
      normalizeTags(tagsInput)
        .filter((tag) => tag !== targetTag)
        .join(", "),
    );
  };

  const formActions = {
    name,
    description,
    tagsInput,
    enabled,
    errors,
    isEditing,
    isLoading,
    files,
    activeFileIndex,
    setName,
    setDescription,
    setEnabled,
    setTagsInput,
    setActiveFileIndex,
    updateFilePath,
    updateFileContent,
    removeFile,
    addFile,
    removeTag,
    handleSubmit,
    onCancel,
    toggleFullscreen,
  };

  const formElement = (
    <form
      onSubmit={handleSubmit}
      className={
        isFullscreen
          ? "skill-form skill-form--fullscreen fixed inset-0 z-[100] flex flex-col bg-[var(--theme-bg)]"
          : "skill-form flex flex-1 flex-col gap-4"
      }
    >
      {isFullscreen ? (
        <SkillFormFullscreen {...formActions} />
      ) : (
        <SkillFormNormal {...formActions} />
      )}
    </form>
  );

  if (isFullscreen) {
    return createPortal(formElement, document.body);
  }
  return formElement;
}
