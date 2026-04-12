import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { sanitizeSkillName } from "../../utils/skillFilters";
import { normalizeTags, syncSkillMarkdownMetadata } from "./SkillForm.utils";
import { DEFAULT_CONTENT } from "./SkillForm.types";
import type { SkillFormProps, FileEntry } from "./SkillForm.types";
import type { BinaryFileInfo } from "../../types/skill";
import { skillApi } from "../../services/api/skill";
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
  const [binaryFiles, setBinaryFiles] = useState<
    Record<string, BinaryFileInfo>
  >({});
  const [loadingFilePath, setLoadingFilePath] = useState<string | null>(null);

  // Track which file indices have been loaded
  const loadedIndices = useRef<Set<number>>(new Set());
  // Track which file paths are currently being loaded (prevent concurrent loads of same file)
  const loadingPaths = useRef<Set<string>>(new Set());

  const toggleFullscreen = useCallback(
    (fs: boolean) => {
      setIsFullscreen(fs);
      onFullscreenChange?.(fs);
      if (fs) {
        toast(t("skills.form.fullscreenHint", "按 Esc 退出全屏"), {
          duration: 2000,
          position: "top-center",
          style: { borderRadius: "10px", background: "#1c1917", color: "#fff" },
        });
      }
    },
    [onFullscreenChange, t],
  );

  // Initialize files from skill prop
  useEffect(() => {
    loadedIndices.current = new Set();
    loadingPaths.current = new Set();
    setBinaryFiles({});

    if (skill?.filePaths && skill.filePaths.length > 0) {
      // Lazy mode: only paths, content loaded on demand
      const fileEntries = skill.filePaths.map((path) => ({
        path,
        content: "",
      }));
      fileEntries.sort((a, b) => {
        if (a.path === "SKILL.md") return -1;
        if (b.path === "SKILL.md") return 1;
        return a.path.localeCompare(b.path);
      });
      setFiles(fileEntries);
    } else if (skill?.files && Object.keys(skill.files).length > 0) {
      // Legacy: all content already available
      const fileEntries = Object.entries(skill.files).map(
        ([path, content]) => ({ path, content }),
      );
      fileEntries.sort((a, b) => {
        if (a.path === "SKILL.md") return -1;
        if (b.path === "SKILL.md") return 1;
        return a.path.localeCompare(b.path);
      });
      setFiles(fileEntries);
      // Mark all as loaded
      fileEntries.forEach((_, i) => loadedIndices.current.add(i));
    } else if (skill?.content) {
      setFiles([{ path: "SKILL.md", content: skill.content }]);
      loadedIndices.current.add(0);
    } else {
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
      loadedIndices.current.add(0);
    }

    if (skill?.binaryFiles) {
      setBinaryFiles(skill.binaryFiles);
    }
  }, [skill]);

  // Reset form fields when skill changes
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
      loadedIndices.current = new Set([0]);
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

  // Load a single file's content on demand
  const loadFileContent = useCallback(
    (index: number) => {
      if (!skill?.name) return;
      const file = files[index];
      if (!file || loadedIndices.current.has(index)) return;

      const filePath = file.path;
      // Prevent duplicate concurrent loads of the same file
      if (loadingPaths.current.has(filePath)) return;
      loadingPaths.current.add(filePath);
      setLoadingFilePath(filePath);

      skillApi
        .getFile(skill.name, filePath)
        .then((fileResp) => {
          if (fileResp.is_binary && fileResp.url) {
            // Binary file: store metadata
            setBinaryFiles((prev) => ({
              ...prev,
              [filePath]: {
                url: fileResp.url!,
                mime_type: fileResp.mime_type || "application/octet-stream",
                size: fileResp.size || 0,
              },
            }));
            setFiles((prev) =>
              prev.map((f, i) =>
                i === index
                  ? {
                      ...f,
                      content: `[Binary: ${fileResp.mime_type}, ${(
                        (fileResp.size ?? 0) / 1024
                      ).toFixed(1)}KB]`,
                    }
                  : f,
              ),
            );
          } else {
            setFiles((prev) =>
              prev.map((f, i) =>
                i === index ? { ...f, content: fileResp.content } : f,
              ),
            );
          }
          loadedIndices.current.add(index);
        })
        .catch(() => {
          // Failed to load file content
        })
        .finally(() => {
          loadingPaths.current.delete(filePath);
          // Only clear loading state if this was the last loading file
          if (loadingPaths.current.size === 0) {
            setLoadingFilePath(null);
          } else {
            // Update to show whichever file is still loading
            const remaining = Array.from(loadingPaths.current);
            setLoadingFilePath(remaining[remaining.length - 1]);
          }
        });
    },
    [skill?.name, files],
  );

  // Auto-load SKILL.md on mount
  useEffect(() => {
    if (!skill?.name || !skill?.filePaths) return;
    const skillMdIndex = files.findIndex((f) => f.path === "SKILL.md");
    if (skillMdIndex >= 0 && !loadedIndices.current.has(skillMdIndex)) {
      loadFileContent(skillMdIndex);
    }
  }, [files, skill?.name, skill?.filePaths, loadFileContent]);

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

  // When user clicks a file tab, load its content if not yet loaded
  const handleTabSelect = useCallback(
    (index: number) => {
      setActiveFileIndex(index);
      if (!loadedIndices.current.has(index)) {
        loadFileContent(index);
      }
    },
    [loadFileContent],
  );

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
    binaryFiles,
    loadingFilePath,
    setName,
    setDescription,
    setEnabled,
    setTagsInput,
    setActiveFileIndex: handleTabSelect,
    updateFilePath,
    updateFileContent,
    removeFile,
    addFile,
    removeTag,
    loadFileContent,
    handleSubmit,
    onCancel,
    toggleFullscreen,
  };

  const formElement = (
    <form
      onSubmit={handleSubmit}
      className={
        isFullscreen
          ? "skill-form skill-form--fullscreen fixed inset-0 z-[400] flex flex-col bg-[var(--theme-bg)]"
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
