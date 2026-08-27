/**
 * ShareProjectDialog - 创建/管理项目分享
 *
 * 样式对齐 ShareDialog（会话分享）。
 * - full：实时分享项目内全部会话
 * - partial：选中若干会话创建快照
 */

import { type RefObject, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  Share2,
  Copy,
  Trash2,
  Globe,
  Lock,
  Loader2,
  Check,
  X,
  AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";
import { SkeletonList } from "../skeletons";
import { Checkbox } from "../common/Checkbox";
import { shareApi } from "../../services/api/share";
import { sessionApi } from "../../services/api/session";
import type { SharedSession, ShareType, ShareVisibility } from "../../types";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { copyToClipboard } from "../../utils/clipboard";
import { getFullUrl } from "../../services/api/config";
import {
  PROJECT_SHARE_SESSION_LIMIT,
  buildInitialProjectSessionSelection,
  resolveSessionTitle,
  toggleProjectSessionSelection,
} from "./shareProjectDialogState";

interface ProjectSessionOption {
  session_id: string;
  name: string;
  updated_at?: string;
}

interface ShareProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  projectName: string;
  projectIcon?: string;
}

export function ShareProjectDialog({
  isOpen,
  onClose,
  projectId,
  projectName,
  projectIcon,
}: ShareProjectDialogProps) {
  const { t } = useTranslation();
  const [shareType, setShareType] = useState<ShareType>("full");
  const [visibility, setVisibility] = useState<ShareVisibility>("public");
  const [sessions, setSessions] = useState<ProjectSessionOption[]>([]);
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [existingShares, setExistingShares] = useState<SharedSession[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingShares, setIsLoadingShares] = useState(false);
  const [hasLoadedShares, setHasLoadedShares] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const swipeRef = useSwipeToClose({ onClose, enabled: isOpen });
  useBodyScrollLock(isOpen);

  const loadExistingShares = useCallback(async () => {
    setIsLoadingShares(true);
    try {
      const shares = await shareApi.listByProject(projectId);
      setExistingShares(shares);
    } catch (error) {
      console.error("Failed to load project shares:", error);
    } finally {
      setIsLoadingShares(false);
      setHasLoadedShares(true);
    }
  }, [projectId]);

  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const res = await sessionApi.list({ project_id: projectId, limit: 100 });
      const raw = (Array.isArray(res)
        ? res
        : res.sessions ?? []) as unknown as Array<Record<string, unknown>>;
      const opts: ProjectSessionOption[] = raw.map((item) => {
        return {
          session_id:
            (item.session_id as string | undefined) ??
            (item.id as string | undefined) ??
            "",
          // 会话名优先级与 getSessionTitle 一致:顶层 name → metadata.title
          name: resolveSessionTitle(item),
          updated_at: item.updated_at as string | undefined,
        };
      });
      setSessions(opts);
      setSelectedSessionIds(
        buildInitialProjectSessionSelection(opts.map((o) => o.session_id)),
      );
    } catch (error) {
      console.error("Failed to load project sessions:", error);
    } finally {
      setIsLoadingSessions(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (isOpen) {
      loadExistingShares();
    }
  }, [isOpen, loadExistingShares]);

  useEffect(() => {
    if (isOpen && shareType === "partial") {
      loadSessions();
    }
  }, [isOpen, shareType, loadSessions]);

  const handleCreate = async () => {
    if (shareType === "partial" && selectedSessionIds.length === 0) {
      toast.error(t("share.selectAtLeastOneSession", "请至少选择一个会话"));
      return;
    }
    setIsCreating(true);
    try {
      await shareApi.create({
        share_scope: "project",
        project_id: projectId,
        share_type: shareType,
        visibility,
        session_ids: shareType === "partial" ? selectedSessionIds : undefined,
      });
      toast.success(t("share.created", "分享链接已创建"));
      await loadExistingShares();
    } catch (error) {
      console.error("Failed to create project share:", error);
      toast.error(t("share.createFailed", "创建分享失败"));
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopy = async (shareId: string) => {
    await copyToClipboard(getFullUrl(`/shared/${shareId}`) ?? "");
    setCopiedId(shareId);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleDelete = async (shareDbId: string) => {
    try {
      await shareApi.delete(shareDbId);
      setExistingShares((prev) => prev.filter((s) => s.id !== shareDbId));
      toast.success(t("share.deleted", "已删除"));
    } catch (error) {
      console.error("Failed to delete share:", error);
      toast.error(t("share.deleteFailed", "删除失败"));
    }
  };

  const toggleSession = (sessionId: string) => {
    const result = toggleProjectSessionSelection(selectedSessionIds, sessionId);
    if (result.limitReached) {
      toast.error(
        t("share.selectionLimitReached", {
          count: PROJECT_SHARE_SESSION_LIMIT,
        }),
      );
    }
    setSelectedSessionIds(result.selected);
  };

  const selectableSessionIds = buildInitialProjectSessionSelection(
    sessions.map((session) => session.session_id),
  );
  const allSelected =
    selectableSessionIds.length > 0 &&
    selectableSessionIds.every((id) => selectedSessionIds.includes(id));
  const toggleAll = () => {
    setSelectedSessionIds(allSelected ? [] : selectableSessionIds);
  };

  if (!isOpen) return null;

  return createPortal(
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[299] bg-black/50" onClick={onClose} />

      {/* Dialog - bottom sheet on mobile, centered on desktop */}
      <div
        data-yields-sidebar
        className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-end sm:items-center sm:justify-center sm:pointer-events-none"
      >
        <div
          ref={swipeRef as RefObject<HTMLDivElement>}
          className="relative z-10 w-full sm:max-w-xl sm:mx-4 sm:pointer-events-auto bg-white dark:bg-stone-800 sm:rounded-xl rounded-t-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden duration-300 max-h-[90vh] max-h-[90dvh] flex flex-col animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200 dark:border-stone-700">
            {/* Mobile drag handle */}
            <div className="sm:hidden absolute top-2 left-1/2 -translate-x-1/2 w-9 h-1 bg-stone-300 dark:bg-stone-600 rounded-full" />
            <div className="flex items-center gap-2 pt-2 sm:pt-0">
              <Share2
                size={20}
                className="text-stone-500 dark:text-stone-400"
              />
              <h3 className="text-lg font-semibold font-serif text-stone-900 dark:text-stone-100">
                {t("sidebar.shareProject")}
              </h3>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
            >
              <X size={20} className="text-stone-500 dark:text-stone-400" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* Project name */}
            <div className="text-sm text-stone-600 dark:text-stone-400">
              <span className="font-medium">{t("share.project", "项目")}:</span>{" "}
              {projectIcon ? `${projectIcon} ` : ""}
              {projectName || t("share.project", "项目")}
            </div>

            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
              <AlertTriangle
                size={16}
                className="mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-300"
              />
              <p className="leading-5">{t("share.privacyReminder")}</p>
            </div>

            {/* Share Type */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("share.shareType")}
              </label>
              <div className="flex gap-3">
                <button
                  onClick={() => setShareType("full")}
                  className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                    shareType === "full"
                      ? "border-stone-500 bg-stone-100 dark:bg-stone-700 text-stone-700 dark:text-stone-200"
                      : "border-stone-200 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"
                  }`}
                >
                  {t("share.fullProject", "完整项目")}
                </button>
                <button
                  onClick={() => setShareType("partial")}
                  className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                    shareType === "partial"
                      ? "border-stone-500 bg-stone-100 dark:bg-stone-700 text-stone-700 dark:text-stone-200"
                      : "border-stone-200 dark:border-stone-600 text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700"
                  }`}
                >
                  {t("share.partialSessions", "部分会话")}
                </button>
              </div>
              {shareType === "full" && (
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("share.fullProjectHint", "实时包含项目内全部会话")}
                </p>
              )}
              {shareType === "partial" && (
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("share.partialSessionsHint", "仅分享选中的会话（快照）")}
                </p>
              )}
            </div>

            {/* Session selection for partial share */}
            {shareType === "partial" && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("share.selectSessions", "选择会话")}
                  </label>
                  {!isLoadingSessions && sessions.length > 0 && (
                    <button
                      type="button"
                      onClick={toggleAll}
                      className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
                    >
                      {allSelected
                        ? t("share.deselectAll")
                        : sessions.length > PROJECT_SHARE_SESSION_LIMIT
                          ? t("share.selectUpToLimit", {
                              count: PROJECT_SHARE_SESSION_LIMIT,
                            })
                          : t("share.selectAll")}
                    </button>
                  )}
                </div>
                {isLoadingSessions ? (
                  <SkeletonList count={3} className="py-2" />
                ) : sessions.length === 0 ? (
                  <div className="text-sm text-stone-500 dark:text-stone-400 py-2">
                    {t("share.noSessions", "项目内暂无会话")}
                  </div>
                ) : (
                  <div className="max-h-40 overflow-y-auto space-y-1 border rounded-lg p-2 dark:border-stone-600">
                    {sessions.map((session) => (
                      <button
                        key={session.session_id}
                        type="button"
                        onClick={() => toggleSession(session.session_id)}
                        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                          selectedSessionIds.includes(session.session_id)
                            ? "bg-stone-100 dark:bg-stone-700 text-stone-700 dark:text-stone-200"
                            : "hover:bg-stone-50 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-300"
                        }`}
                      >
                        <Checkbox
                          checked={selectedSessionIds.includes(
                            session.session_id,
                          )}
                          size="sm"
                          onChange={() => toggleSession(session.session_id)}
                        />
                        <span className="flex-1 min-w-0 truncate text-left">
                          {session.name ||
                            t("share.untitledSession", "未命名会话")}
                        </span>
                        {session.updated_at && (
                          <span className="text-xs text-stone-400 dark:text-stone-500 whitespace-nowrap">
                            {new Date(session.updated_at).toLocaleDateString()}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Visibility */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("share.visibility")}
              </label>
              <div className="space-y-2">
                <button
                  onClick={() => setVisibility("public")}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                    visibility === "public"
                      ? "border-stone-500 bg-stone-100 dark:bg-stone-700"
                      : "border-stone-200 dark:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-700"
                  }`}
                >
                  <Globe
                    size={20}
                    className={
                      visibility === "public"
                        ? "text-stone-600 dark:text-stone-300"
                        : "text-stone-400 dark:text-stone-500"
                    }
                  />
                  <div>
                    <div className="text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("share.public")}
                    </div>
                    <div className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                      {t("share.publicDesc")}
                    </div>
                  </div>
                </button>
                <button
                  onClick={() => setVisibility("authenticated")}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                    visibility === "authenticated"
                      ? "border-stone-500 bg-stone-100 dark:bg-stone-700"
                      : "border-stone-200 dark:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-700"
                  }`}
                >
                  <Lock
                    size={20}
                    className={
                      visibility === "authenticated"
                        ? "text-stone-600 dark:text-stone-300"
                        : "text-stone-400 dark:text-stone-500"
                    }
                  />
                  <div>
                    <div className="text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("share.authenticated")}
                    </div>
                    <div className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
                      {t("share.authenticatedDesc")}
                    </div>
                  </div>
                </button>
              </div>
            </div>

            {/* Existing shares */}
            {isLoadingShares && !hasLoadedShares ? (
              <div className="space-y-2 py-2">
                <SkeletonList count={2} className="py-2" />
              </div>
            ) : existingShares.length > 0 ? (
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("share.existingShares")}
                </label>
                <div className="space-y-2">
                  {existingShares.map((share) => (
                    <div
                      key={share.id}
                      className="flex items-center justify-between p-3 bg-stone-50 dark:bg-stone-900/50 rounded-lg border border-stone-200 dark:border-stone-700"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {share.visibility === "public" ? (
                          <Globe
                            size={14}
                            className="text-green-500 flex-shrink-0"
                          />
                        ) : (
                          <Lock
                            size={14}
                            className="text-amber-500 flex-shrink-0"
                          />
                        )}
                        <span className="text-xs text-stone-500 dark:text-stone-400 truncate">
                          /shared/{share.share_id}
                        </span>
                        <span className="text-xs text-stone-400 dark:text-stone-500">
                          (
                          {share.share_type === "full"
                            ? t("share.fullProject", "完整项目")
                            : t("share.partialSessions", "部分会话")}
                          )
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleCopy(share.share_id)}
                          className="p-1.5 rounded hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors"
                          title={t("share.copyLink")}
                        >
                          {copiedId === share.share_id ? (
                            <Check size={14} className="text-green-500" />
                          ) : (
                            <Copy
                              size={14}
                              className="text-stone-400 dark:text-stone-500"
                            />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(share.id)}
                          className="p-1.5 rounded hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors"
                          title={t("share.deleteShare")}
                        >
                          <Trash2
                            size={14}
                            className="text-stone-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400"
                          />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          {/* Footer */}
          <div className="safe-area-bottom flex items-center justify-end gap-2 px-5 pt-4 [--safe-area-bottom-extra:1rem] bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors"
            >
              {t("common.close")}
            </button>
            <button
              onClick={handleCreate}
              disabled={
                isCreating ||
                (shareType === "partial" && selectedSessionIds.length === 0)
              }
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-stone-900 hover:bg-stone-800 dark:bg-stone-600 dark:hover:bg-stone-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="inline-flex h-4 w-4 items-center justify-center">
                {isCreating ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Share2 size={16} />
                )}
              </span>
              <span>{t("share.createShare")}</span>
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
