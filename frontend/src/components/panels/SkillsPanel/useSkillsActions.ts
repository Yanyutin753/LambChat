import { useCallback, useMemo, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useLocation, useNavigate } from "react-router-dom";
import { exportProjectZip } from "../../../utils/exportProjectZip";
import { useSkills } from "../../../hooks/useSkills";
import { sanitizeSkillName } from "../../../utils/skillFilters";
import type { SkillResponse, SkillCreate } from "../../../types";

interface GitHubSkill {
  name: string;
  path: string;
  description: string;
}

export interface ZipSkillPreview {
  name: string;
  description: string;
  file_count: number;
  files: string[];
  already_exists: boolean;
}

export function useSkillsActions() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  // Search & filter
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [enabledFilter, setEnabledFilter] = useState<
    "all" | "enabled" | "disabled"
  >("all");

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const handleSearchQueryChange = useCallback((query: string) => {
    setPage(1);
    setSearchQuery(query);
  }, []);
  const handleEnabledFilterChange = useCallback(
    (filter: "all" | "enabled" | "disabled") => {
      setPage(1);
      setEnabledFilter(filter);
    },
    [],
  );
  const listParams = useMemo(
    () => ({
      skip: (page - 1) * pageSize,
      limit: pageSize,
      q: searchQuery.trim() || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
    }),
    [page, pageSize, searchQuery, selectedTags],
  );

  const {
    skills,
    availableTags,
    total,
    isLoading,
    error,
    getSkill,
    getFullSkill,
    createSkill,
    updateSkill,
    deleteSkill,
    batchDeleteSkills,
    batchToggleSkills,
    toggleSkill,
    updateSkillPreference,
    uploadSkill,
    previewZipSkills,
    previewGitHubSkills,
    installGitHubSkills,
    publishToMarketplace,
    isPublishing,
    clearError,
    fetchSkills,
  } = useSkills({ listParams });

  // Client-side enabled/disabled filter on top of server results
  const filteredSkills = useMemo(() => {
    if (enabledFilter === "all") return skills;
    return skills.filter((s) =>
      enabledFilter === "enabled" ? s.enabled : !s.enabled,
    );
  }, [skills, enabledFilter]);

  useEffect(() => {
    const prefillSearch = (
      location.state as { prefillSkillSearch?: string } | null
    )?.prefillSkillSearch;
    if (!prefillSearch) {
      return;
    }
    setPage(1);
    setSearchQuery(prefillSearch);
    navigate(location.pathname, { replace: true });
  }, [location.pathname, location.state, navigate]);

  const paginatedSkills = filteredSkills;

  const toggleTag = (tag: string) => {
    setPage(1);
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    );
  };

  const clearFilters = () => {
    setPage(1);
    setSearchQuery("");
    setSelectedTags([]);
    setEnabledFilter("all");
  };

  // Form modal state
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [savedSkillName, setSavedSkillName] = useState<string | null>(null);
  const formSession = useRef(0);

  // Batch selection state
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const batchRequest = useRef<symbol | null>(null);
  const lastBatchAction = useRef<"delete" | "enable" | "disable">("delete");
  const lastBatchNames = useRef<string[]>([]);
  useEffect(
    () => () => {
      batchRequest.current = null;
    },
    [],
  );

  // Delete confirmation
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
  } | null>(null);

  // Publish confirmation
  const [publishConfirm, setPublishConfirm] = useState<{
    isOpen: boolean;
    localSkillName: string;
    marketplaceSkillName: string;
    description: string;
    tagsInput: string;
    isPublished: boolean;
    error?: string;
  } | null>(null);

  // ZIP upload state
  const [showZipModal, setShowZipModal] = useState(false);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipUploading, setZipUploading] = useState(false);
  const [zipPreviewing, setZipPreviewing] = useState(false);
  const [zipError, setZipError] = useState<string | null>(null);
  const zipRequest = useRef(0);
  const [zipSkills, setZipSkills] = useState<ZipSkillPreview[]>([]);
  const [selectedZipSkills, setSelectedZipSkills] = useState<string[]>([]);
  const zipInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  // GitHub import state
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubUrl, setGithubUrl] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");
  const [githubSkills, setGithubSkills] = useState<GitHubSkill[]>([]);
  const [selectedGithubSkills, setSelectedGithubSkills] = useState<string[]>(
    [],
  );
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubInstalling, setGithubInstalling] = useState(false);
  const [githubError, setGithubError] = useState<string | null>(null);
  const [githubPreviewed, setGithubPreviewed] = useState(false);
  const githubRequest = useRef(0);

  useEffect(() => {
    const request = githubRequest;
    request.current++;
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    setGithubError(null);
    setGithubPreviewed(false);
    setGithubLoading(false);
    setGithubInstalling(false);
    return () => {
      request.current++;
    };
  }, [githubUrl, githubBranch, showGithubModal]);
  useEffect(() => {
    const request = zipRequest;
    if (!showZipModal) {
      request.current++;
      setZipPreviewing(false);
      setZipUploading(false);
    }
    return () => {
      request.current++;
    };
  }, [showZipModal]);

  // CRUD handlers
  const handleCreate = () => {
    formSession.current++;
    setSavedSkillName(null);
    setIsCreating(true);
    setEditingSkill(null);
    setShowModal(true);
  };

  const handleEdit = async (skill: SkillResponse) => {
    const request = ++formSession.current;
    setShowModal(false);
    setSavedSkillName(null);
    const fullSkill = await getSkill(skill.name);
    if (formSession.current !== request) return;
    setEditingSkill(fullSkill || skill);
    setIsCreating(false);
    setShowModal(true);
  };

  const handleSave = async (data: SkillCreate): Promise<boolean> => {
    const request = formSession.current;
    let success = false;
    try {
      if (isCreating && !savedSkillName) {
        success = await createSkill(data);
      } else if (editingSkill || savedSkillName) {
        // A retry reads the actual manifest, including completed binary uploads.
        const current = savedSkillName
          ? await getSkill(savedSkillName)
          : editingSkill;
        if (!current || formSession.current !== request) return false;
        // Use filePaths (lazy-load mode) when available, fallback to files keys
        const oldFiles = current.filePaths?.length
          ? current.filePaths
          : Object.keys(current.files);
        const newFiles = data.filePaths?.length
          ? data.filePaths
          : data.files
            ? Object.keys(data.files)
            : [];
        const deletedFiles = oldFiles.filter((f) => !newFiles.includes(f));
        success = await updateSkill(current.name, {
          description: data.description,
          content: data.content,
          files: data.files,
          deletedFiles,
        });
      }
      if (formSession.current !== request) return false;
      if (success) setSavedSkillName(data.name);
    } catch {
      success = false;
    }
    return success;
  };

  const handleCancel = () => {
    formSession.current++;
    setSavedSkillName(null);
    setShowModal(false);
    setEditingSkill(null);
    setIsCreating(false);
  };

  const activeFormSession = formSession.current;
  const handleComplete = () => {
    if (formSession.current !== activeFormSession) return;
    handleCancel();
    void fetchSkills();
  };

  const handleExportZip = async (name: string) => {
    const fullSkill = await getFullSkill(name);
    if (!fullSkill) {
      toast.error(t("skills.exportFailed"));
      return;
    }
    try {
      await exportProjectZip(fullSkill.files, name);
      toast.success(t("skills.exportSuccess"));
    } catch {
      toast.error(t("skills.exportFailed"));
    }
  };

  const handleDelete = (name: string) => {
    setDeleteConfirmData({ name });
    setIsDeleteConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleteConfirmData) return;
    try {
      await deleteSkill(deleteConfirmData.name);
    } finally {
      setIsDeleteConfirmOpen(false);
      setDeleteConfirmData(null);
    }
  };

  const cancelDelete = () => {
    setIsDeleteConfirmOpen(false);
    setDeleteConfirmData(null);
  };

  const handleToggle = async (name: string) => {
    await toggleSkill(name);
  };

  const handleTogglePreference = async (
    skill: SkillResponse,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => {
    await updateSkillPreference(skill.name, preference);
  };

  // Batch handlers
  const selectionMode = selectedNames.size > 0;

  const handleSelectSkill = (name: string) => {
    setBatchError(null);
    setSelectedNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleSelectAll = () => {
    setBatchError(null);
    if (selectedNames.size === filteredSkills.length) {
      setSelectedNames(new Set());
    } else {
      setSelectedNames(new Set(filteredSkills.map((s) => s.name)));
    }
  };

  const clearSelection = () => {
    if (batchRequest.current) return;
    setBatchError(null);
    setSelectedNames(new Set());
  };

  const handleBatchAction = async (
    action: "delete" | "enable" | "disable",
    names = Array.from(selectedNames),
  ) => {
    if (names.length === 0 || batchRequest.current) return;
    const request = Symbol();
    batchRequest.current = request;
    lastBatchAction.current = action;
    lastBatchNames.current = names;
    setBatchLoading(true);
    setBatchError(null);
    try {
      const result =
        action === "delete"
          ? await batchDeleteSkills(names)
          : await batchToggleSkills(names, action === "enable");
      if (batchRequest.current !== request) return;
      const completed = result
        ? "deleted" in result
          ? result.deleted
          : result.updated
        : [];
      lastBatchNames.current = names.filter(
        (name) => !completed.includes(name),
      );
      setSelectedNames(
        (previous) =>
          new Set(
            Array.from(previous).filter(
              (name) => !names.includes(name) || !completed.includes(name),
            ),
          ),
      );
      if (
        result &&
        result.errors.length === 0 &&
        completed.length === names.length
      )
        toast.success(
          t(
            action === "delete"
              ? "skills.batchDeleteSuccess"
              : action === "enable"
                ? "skills.batchEnableSuccess"
                : "skills.batchDisableSuccess",
            { count: completed.length },
          ),
        );
      else
        setBatchError(
          t(
            action === "delete"
              ? "skills.batchDeleteFailed"
              : "skills.batchToggleFailed",
          ),
        );
    } catch {
      if (batchRequest.current === request)
        setBatchError(
          t(
            action === "delete"
              ? "skills.batchDeleteFailed"
              : "skills.batchToggleFailed",
          ),
        );
    } finally {
      if (batchRequest.current === request) {
        batchRequest.current = null;
        setBatchLoading(false);
      }
    }
  };

  const handleBatchDelete = () => handleBatchAction("delete");
  const handleBatchToggle = (enabled: boolean) =>
    handleBatchAction(enabled ? "enable" : "disable");
  const handleBatchRetry = () =>
    handleBatchAction(
      lastBatchAction.current,
      lastBatchNames.current.filter((name) => selectedNames.has(name)),
    );

  // Publish handler
  const confirmPublish = async () => {
    if (!publishConfirm || isPublishing) return;
    const { localSkillName, marketplaceSkillName, description } =
      publishConfirm;

    if (!marketplaceSkillName.trim()) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.nameRequired"),
      });
      return;
    }
    if (!description.trim()) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.descriptionRequired"),
      });
      return;
    }

    const normalizedTags = Array.from(
      new Set(
        publishConfirm.tagsInput
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      ),
    );

    const success = await publishToMarketplace(localSkillName, {
      skill_name: sanitizeSkillName(marketplaceSkillName.trim()),
      description: description.trim() || undefined,
      tags: normalizedTags,
    });

    if (success) {
      toast.success(
        publishConfirm.isPublished
          ? t("skills.republishSuccess")
          : t("skills.publishSuccess"),
      );
      setPublishConfirm(null);
      return;
    }

    setPublishConfirm({
      ...publishConfirm,
      error: t("skills.publishFailed") || "Publish failed",
    });
  };

  // ZIP upload handlers
  const handleZipClick = () => {
    setZipFile(null);
    setZipSkills([]);
    setSelectedZipSkills([]);
    setIsDragging(false);
    setZipError(null);
    setShowZipModal(true);
  };

  const processZipFile = (file: File) => {
    if (zipUploading || zipPreviewing) return;
    if (!file.name.endsWith(".zip")) {
      toast.error(t("skills.invalidZipFile"));
      return;
    }
    setZipFile(file);
    setZipSkills([]);
    setSelectedZipSkills([]);
    handleZipPreviewWithFile(file);
  };

  const handleZipFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (file) processZipFile(file);
  };

  const handleZipPreviewWithFile = async (file: File) => {
    const request = ++zipRequest.current;
    setZipPreviewing(true);
    setZipError(null);
    setZipSkills([]);
    setSelectedZipSkills([]);
    try {
      const result = await previewZipSkills(file);
      if (request !== zipRequest.current) return;
      if (result && result.skills) {
        setZipSkills(result.skills);
        setSelectedZipSkills(
          result.skills.filter((s) => !s.already_exists).map((s) => s.name),
        );
      } else {
        setZipError(t("skills.previewZipFailed"));
      }
    } catch {
      if (request === zipRequest.current)
        setZipError(t("skills.previewZipFailed"));
    } finally {
      if (request === zipRequest.current) setZipPreviewing(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0] || null;
    if (file) processZipFile(file);
  };

  const handleZipSkillToggle = (name: string) => {
    setSelectedZipSkills((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleZipSelectAll = (names: string[]) => {
    setSelectedZipSkills(names);
  };

  const handleZipUpload = async () => {
    if (
      !zipFile ||
      selectedZipSkills.length === 0 ||
      zipUploading ||
      zipPreviewing
    )
      return;
    const request = zipRequest.current;
    setZipUploading(true);
    setZipError(null);
    try {
      const result = await uploadSkill(zipFile, selectedZipSkills);
      if (request !== zipRequest.current) return;
      if (result && result.created.length > 0 && result.errors.length === 0) {
        setShowZipModal(false);
        setZipFile(null);
        setZipSkills([]);
        setSelectedZipSkills([]);
      } else {
        const created = new Set(
          result?.created.map((skill) => skill.name) ?? [],
        );
        setSelectedZipSkills((prev) =>
          prev.filter((name) => !created.has(name)),
        );
        setZipSkills((prev) =>
          prev.map((skill) =>
            created.has(skill.name)
              ? { ...skill, already_exists: true }
              : skill,
          ),
        );
        setZipError(t("skills.uploadFailed"));
      }
    } catch {
      if (request === zipRequest.current) setZipError(t("skills.uploadFailed"));
    } finally {
      if (request === zipRequest.current) setZipUploading(false);
    }
  };

  const handleZipRetry = () => {
    if (zipSkills.length > 0 && selectedZipSkills.length > 0)
      void handleZipUpload();
    else if (zipFile) void handleZipPreviewWithFile(zipFile);
  };

  // GitHub import handlers
  const handleGithubClick = () => {
    setGithubUrl("");
    setGithubBranch("main");
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    setShowGithubModal(true);
  };

  const handleGithubPreview = async () => {
    if (!githubUrl.trim() || githubLoading || githubInstalling) return;
    const request = ++githubRequest.current;
    setGithubLoading(true);
    setGithubError(null);
    setGithubPreviewed(false);
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    try {
      const result = await previewGitHubSkills(githubUrl, githubBranch);
      if (request !== githubRequest.current) return;
      if (result && result.skills) {
        setGithubSkills(result.skills);
        setGithubPreviewed(true);
      } else {
        setGithubError(t("skills.previewGitHubFailed"));
      }
    } catch {
      if (request === githubRequest.current)
        setGithubError(t("skills.previewGitHubFailed"));
    } finally {
      if (request === githubRequest.current) setGithubLoading(false);
    }
  };

  const handleGithubSkillToggle = (name: string) => {
    setSelectedGithubSkills((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleGithubInstall = async () => {
    if (
      selectedGithubSkills.length === 0 ||
      githubLoading ||
      githubInstalling ||
      !githubPreviewed
    )
      return;
    const request = githubRequest.current;
    setGithubInstalling(true);
    setGithubError(null);
    try {
      const result = await installGitHubSkills(
        githubUrl,
        selectedGithubSkills,
        githubBranch,
      );
      if (request !== githubRequest.current) return;
      if (result && result.errors.length === 0) {
        setShowGithubModal(false);
        setGithubSkills([]);
        setSelectedGithubSkills([]);
      } else {
        setSelectedGithubSkills((prev) =>
          prev.filter((name) => !result?.installed.includes(name)),
        );
        setGithubSkills((prev) =>
          prev.filter((skill) => !result?.installed.includes(skill.name)),
        );
        setGithubError(t("skills.installGitHubFailed"));
      }
    } catch {
      if (request === githubRequest.current)
        setGithubError(t("skills.installGitHubFailed"));
    } finally {
      if (request === githubRequest.current) setGithubInstalling(false);
    }
  };

  return {
    // Data
    skills,
    isLoading,
    error,
    filteredSkills,
    paginatedSkills,
    availableTags,
    total,
    page,
    pageSize,

    // Search & filter
    searchQuery,
    setSearchQuery: handleSearchQueryChange,
    selectedTags,
    enabledFilter,
    setEnabledFilter: handleEnabledFilterChange,
    toggleTag,
    clearFilters,
    setPage,

    // Form modal
    editingSkill,
    isCreating,
    showModal,
    isNameLocked: !!savedSkillName,
    handleCreate,
    handleEdit,
    handleSave,
    handleCancel,
    handleComplete,

    // CRUD
    handleExportZip,
    handleDelete,
    handleToggle,
    handleTogglePreference,
    clearError,

    // Delete confirm
    isDeleteConfirmOpen,
    deleteConfirmData,
    confirmDelete,
    cancelDelete,

    // Publish
    publishConfirm,
    setPublishConfirm,
    confirmPublish,
    isPublishing,

    // Batch
    selectedNames,
    selectionMode,
    batchLoading,
    batchError,
    batchAction: lastBatchAction.current,
    handleBatchRetry,
    canBatchRetry: lastBatchNames.current.some((name) =>
      selectedNames.has(name),
    ),
    handleSelectSkill,
    handleSelectAll,
    clearSelection,
    handleBatchDelete,
    handleBatchToggle,

    // ZIP upload
    showZipModal,
    setShowZipModal,
    zipFile,
    zipUploading,
    zipPreviewing,
    zipError,
    handleZipRetry,
    zipSkills,
    selectedZipSkills,
    zipInputRef,
    isDragging,
    handleZipClick,
    handleZipFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleZipSkillToggle,
    handleZipSelectAll,
    handleZipUpload,

    // GitHub import
    showGithubModal,
    setShowGithubModal,
    githubUrl,
    setGithubUrl,
    githubBranch,
    setGithubBranch,
    githubSkills,
    selectedGithubSkills,
    githubLoading,
    githubInstalling,
    githubError,
    githubPreviewed,
    handleGithubClick,
    handleGithubPreview,
    handleGithubSkillToggle,
    setSelectedGithubSkills,
    handleGithubInstall,
  };
}
