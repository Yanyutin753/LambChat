import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { sanitizeSkillName } from "../../utils/skillFilters";
import {
  buildSkillFilesPayload,
  normalizeTags,
  syncSkillMarkdownMetadata,
} from "./SkillForm.utils";
import { DEFAULT_CONTENT } from "./SkillForm.types";
import type { SkillFormProps, FileEntry } from "./SkillForm.types";
import type { BinaryFileInfo } from "../../types/skill";
import { skillApi } from "../../services/api/skill";
import { SkillFormFullscreen } from "./SkillFormFullscreen";
import { SkillFormNormal } from "./SkillFormNormal";
import { useDialogFocus } from "../common/useDialogFocus";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";

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
  const formRef = useRef<HTMLFormElement>(null);
  const wasFullscreen = useRef(false);

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [activeFileIndex, setActiveFileIndex] = useState<number>(0);
  const focusAfterRemoval = useRef(false);
  useEffect(() => {
    if (!focusAfterRemoval.current) return;
    focusAfterRemoval.current = false;
    const controls = Array.from(
      formRef.current?.querySelectorAll<HTMLElement>("[data-file-select]") ??
        [],
    ).filter((button) => button.getClientRects().length);
    (
      controls.find(
        (button) => button.getAttribute("aria-pressed") === "true",
      ) ??
      controls[0] ??
      formRef.current
    )?.focus();
  }, [files, activeFileIndex]);
  useEffect(() => {
    if (Object.keys(errors).length) {
      formRef.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]:not(:disabled)')
        ?.focus();
    }
  }, [errors]);
  const [binaryFiles, setBinaryFiles] = useState<
    Record<string, BinaryFileInfo>
  >({});
  const [pendingBinaryFiles, setPendingBinaryFiles] = useState<
    Record<string, File>
  >({});
  const [loadingFilePaths, setLoadingFilePaths] = useState<Set<string>>(
    new Set(),
  );
  const [fileLoadErrors, setFileLoadErrors] = useState<Record<string, string>>(
    {},
  );
  const binaryFileInputRef = useRef<HTMLInputElement>(null);

  // Track which file paths have been loaded
  const loadedFilePaths = useRef<Set<string>>(new Set());
  // Track which file paths are currently being loaded (prevent concurrent loads of same file)
  const loadingPaths = useRef<Map<string, symbol>>(new Map());

  const toggleFullscreen = useCallback(
    (fs: boolean) => {
      setIsFullscreen(fs);
      onFullscreenChange?.(fs);
    },
    [onFullscreenChange],
  );

  // Initialize files from skill prop
  useEffect(() => {
    loadedFilePaths.current = new Set();
    const requests = loadingPaths.current;
    requests.clear();
    setLoadingFilePaths(new Set());
    setFileLoadErrors({});
    setActiveFileIndex(0);
    setBinaryFiles({});
    setPendingBinaryFiles({});

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
      fileEntries.forEach((file) => loadedFilePaths.current.add(file.path));
    } else if (skill?.content) {
      setFiles([{ path: "SKILL.md", content: skill.content }]);
      loadedFilePaths.current.add("SKILL.md");
    } else {
      setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
      loadedFilePaths.current.add("SKILL.md");
    }

    if (skill?.binaryFiles) {
      setBinaryFiles(skill.binaryFiles);
    }
    return () => requests.clear();
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
      loadedFilePaths.current = new Set(["SKILL.md"]);
    }
    setErrors({});
  }, [skill]);

  useDialogFocus({
    open: isFullscreen,
    onClose: () => toggleFullscreen(false),
    surfaceRef: formRef,
  });
  useBodyScrollLock(isFullscreen, true, true);
  useEffect(() => {
    if (!isFullscreen && wasFullscreen.current) {
      formRef.current
        ?.querySelector<HTMLElement>("[data-fullscreen-trigger]")
        ?.focus();
    }
    wasFullscreen.current = isFullscreen;
  }, [isFullscreen]);

  // Load a single file's content on demand
  const loadFileContent = useCallback(
    (index: number) => {
      if (!skill?.name) return;
      const file = files[index];
      if (!file || loadedFilePaths.current.has(file.path)) return;

      const filePath = file.path;
      // Prevent duplicate concurrent loads of the same file
      if (loadingPaths.current.has(filePath)) return;
      const request = Symbol(filePath);
      loadingPaths.current.set(filePath, request);
      setLoadingFilePaths(new Set(loadingPaths.current.keys()));
      setFileLoadErrors((prev) => {
        const next = { ...prev };
        delete next[filePath];
        return next;
      });

      skillApi
        .getFile(skill.name, filePath)
        .then((fileResp) => {
          if (loadingPaths.current.get(filePath) !== request) return;
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
              prev.map((f) =>
                f.path === filePath
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
              prev.map((f) =>
                f.path === filePath ? { ...f, content: fileResp.content } : f,
              ),
            );
          }
          loadedFilePaths.current.add(filePath);
        })
        .catch(() => {
          if (loadingPaths.current.get(filePath) !== request) return;
          setFileLoadErrors((prev) => ({
            ...prev,
            [filePath]: t("files.loadFailed"),
          }));
        })
        .finally(() => {
          if (loadingPaths.current.get(filePath) !== request) return;
          loadingPaths.current.delete(filePath);
          setLoadingFilePaths(new Set(loadingPaths.current.keys()));
        });
    },
    [skill?.name, files, t],
  );

  // Auto-load SKILL.md on mount
  useEffect(() => {
    if (!skill?.name || !skill?.filePaths) return;
    const skillMdIndex = files.findIndex((f) => f.path === "SKILL.md");
    if (
      skillMdIndex >= 0 &&
      !loadedFilePaths.current.has("SKILL.md") &&
      !fileLoadErrors["SKILL.md"]
    ) {
      loadFileContent(skillMdIndex);
    }
  }, [files, skill?.name, skill?.filePaths, loadFileContent, fileLoadErrors]);

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
    const synced = syncSkillMarkdownMetadata(
      files[activeFileIndex]?.path === "SKILL.md"
        ? files[activeFileIndex]?.content || ""
        : files.find((f) => f.path === "SKILL.md")?.content || DEFAULT_CONTENT,
      name.trim(),
      description.trim(),
      tags,
    );

    const filesDict = buildSkillFilesPayload({
      files,
      syncedSkillMarkdown: synced,
      isEditing,
      loadedFilePaths: loadedFilePaths.current,
      pendingBinaryPaths,
    });
    const filePaths = files.map((file) => file.path.trim()).filter(Boolean);

    const data = {
      name: sanitizeSkillName(name.trim()),
      description: description.trim(),
      tags,
      content: filesDict["SKILL.md"] || "",
      enabled,
      files: filesDict,
      filePaths,
    };

    const success = await onSave(data);
    if (success) {
      // Upload pending binary files after text save succeeds
      const skillName = sanitizeSkillName(name.trim());
      let allBinariesUploaded = true;
      for (const [filePath, file] of Object.entries(pendingBinaryFiles)) {
        try {
          await skillApi.uploadBinaryFile(skillName, filePath, file);
        } catch {
          allBinariesUploaded = false;
        }
      }
      if (allBinariesUploaded) {
        setPendingBinaryFiles({});
      }

      if (!isEditing) {
        setName("");
        setDescription("");
        setTagsInput("");
        setEnabled(true);
        setFiles([{ path: "SKILL.md", content: DEFAULT_CONTENT }]);
        setPendingBinaryFiles({});
      }
    }
  };

  const addFile = () => {
    setFiles([...files, { path: "", content: "" }]);
    setActiveFileIndex(files.length);
    loadedFilePaths.current.add("");
  };

  const removeFile = (index: number) => {
    if (files.length <= 1) return;
    const removedPath = files[index]?.path ?? "";
    const next = files.filter((_, i) => i !== index);
    setFiles(next);
    focusAfterRemoval.current = true;
    if (!next.some((file) => file.path === removedPath)) {
      loadedFilePaths.current.delete(removedPath);
    }
    loadingPaths.current.delete(removedPath);
    setLoadingFilePaths(new Set(loadingPaths.current.keys()));
    setFileLoadErrors((prev) => {
      const next = { ...prev };
      delete next[removedPath];
      return next;
    });
    // Clean up pending binary entry and revoke preview URL
    setPendingBinaryFiles((prev) => {
      const next = { ...prev };
      delete next[removedPath];
      return next;
    });
    setBinaryFiles((prev) => {
      const next = { ...prev };
      const info = next[removedPath];
      if (info?.url.startsWith("blob:")) URL.revokeObjectURL(info.url);
      delete next[removedPath];
      return next;
    });
    setActiveFileIndex((current) =>
      Math.min(index < current ? current - 1 : current, next.length - 1),
    );
  };

  const updateFilePath = (index: number, path: string) => {
    if (
      path.trim() &&
      files.some((file, i) => i !== index && file.path.trim() === path.trim())
    ) {
      setErrors((prev) => ({
        ...prev,
        files: t("skills.form.validation.duplicateFilePaths"),
      }));
      return;
    }
    setErrors((prev) => {
      const next = { ...prev };
      delete next.files;
      return next;
    });
    const next = [...files];
    const previousPath = next[index]?.path;
    if (
      previousPath !== undefined &&
      !loadedFilePaths.current.has(previousPath)
    )
      return;
    next[index] = { ...next[index], path };
    setFiles(next);
    if (
      previousPath !== undefined &&
      loadedFilePaths.current.has(previousPath)
    ) {
      if (!next.some((file) => file.path === previousPath)) {
        loadedFilePaths.current.delete(previousPath);
      }
      loadedFilePaths.current.add(path);
    }
  };

  const updateFileContent = (index: number, content: string) => {
    const next = [...files];
    next[index] = { ...next[index], content };
    setFiles(next);
  };

  const removeTag = (targetTag: string) => {
    formRef.current?.querySelector<HTMLElement>("[data-skill-tags]")?.focus();
    setTagsInput(
      normalizeTags(tagsInput)
        .filter((tag) => tag !== targetTag)
        .join(", "),
    );
  };

  // Derive the set of paths that are pending binary uploads
  const pendingBinaryPaths = useMemo(
    () => new Set(Object.keys(pendingBinaryFiles)),
    [pendingBinaryFiles],
  );

  // Trigger the hidden file input for binary file selection
  const addBinaryFile = useCallback(() => {
    binaryFileInputRef.current?.click();
  }, []);

  // Handle file selection from the hidden input
  const handleBinaryFileSelected = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = e.target.files;
      if (!selectedFiles || selectedFiles.length === 0) return;

      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        const fileName = file.name;
        const filePath = `assets/${fileName}`;

        // Add to files array with placeholder content
        setFiles((prev) => [
          ...prev,
          {
            path: filePath,
            content: `[Binary: ${file.type || "application/octet-stream"}, ${(
              file.size / 1024
            ).toFixed(1)}KB]`,
          },
        ]);
        setActiveFileIndex(files.length + i);
        loadedFilePaths.current.add(filePath);

        // Track as pending binary upload
        setPendingBinaryFiles((prev) => ({ ...prev, [filePath]: file }));

        // Pre-populate binary preview metadata so BinaryFilePreview renders immediately
        setBinaryFiles((prev) => ({
          ...prev,
          [filePath]: {
            url: URL.createObjectURL(file),
            mime_type: file.type || "application/octet-stream",
            size: file.size,
          },
        }));
      }

      // Reset input so the same file can be re-selected
      e.target.value = "";
    },
    [files.length],
  );

  // When user clicks a file tab, load its content if not yet loaded
  const handleTabSelect = useCallback(
    (index: number) => {
      setActiveFileIndex(index);
      const file = files[index];
      if (file && !loadedFilePaths.current.has(file.path)) {
        loadFileContent(index);
      }
    },
    [files, loadFileContent],
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
    loadingFilePath: loadingFilePaths.has(files[activeFileIndex]?.path)
      ? files[activeFileIndex]?.path
      : null,
    fileLoadError: fileLoadErrors[files[activeFileIndex]?.path],
    isCurrentFileLoaded: loadedFilePaths.current.has(
      files[activeFileIndex]?.path,
    ),
    setName,
    setDescription,
    setEnabled,
    setTagsInput,
    setActiveFileIndex: handleTabSelect,
    updateFilePath,
    updateFileContent,
    removeFile,
    addFile,
    addBinaryFile,
    removeTag,
    loadFileContent: (index: number) => {
      formRef.current?.focus();
      loadFileContent(index);
    },
    handleSubmit,
    onCancel,
    toggleFullscreen,
  };

  const formElement = (
    <form
      ref={formRef}
      role={isFullscreen ? "dialog" : undefined}
      aria-modal={isFullscreen ? true : undefined}
      aria-label={isFullscreen ? t("skills.form.fullscreenEditor") : undefined}
      tabIndex={-1}
      onSubmit={handleSubmit}
      className={
        isFullscreen
          ? "skill-form skill-form--fullscreen safe-area-viewport-padding fixed inset-0 z-[1100] flex flex-col bg-[var(--theme-bg)]"
          : "skill-form flex flex-1 flex-col gap-4"
      }
    >
      {/* Hidden file input for binary file uploads */}
      <input
        ref={binaryFileInputRef}
        type="file"
        className="hidden"
        onChange={handleBinaryFileSelected}
        multiple
      />
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
