/**
 * ShareDialog - Dialog for creating and managing session shares
 */

import { useCallback, useEffect, useState } from "react";
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
} from "lucide-react";
import toast from "react-hot-toast";
import { shareApi } from "../../services/api/share";
import type {
  ShareType,
  ShareVisibility,
  SharedSession,
  RunSummary,
} from "../../types";
import { sessionApi } from "../../services/api/session";

interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  sessionName: string;
}

export function ShareDialog({
  isOpen,
  onClose,
  sessionId,
  sessionName,
}: ShareDialogProps) {
  const { t } = useTranslation();
  const [shareType, setShareType] = useState<ShareType>("full");
  const [visibility, setVisibility] = useState<ShareVisibility>("public");
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [existingShares, setExistingShares] = useState<SharedSession[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadExistingShares = useCallback(async () => {
    setIsLoading(true);
    try {
      const shares = await shareApi.listBySession(sessionId);
      setExistingShares(shares);
    } catch (error) {
      console.error("Failed to load shares:", error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const loadRuns = useCallback(async () => {
    setIsLoadingRuns(true);
    try {
      const response = await sessionApi.getRuns(sessionId);
      setRuns(response.runs || []);
    } catch (error) {
      console.error("Failed to load runs:", error);
    } finally {
      setIsLoadingRuns(false);
    }
  }, [sessionId]);

  // Load existing shares and runs when dialog opens
  useEffect(() => {
    if (isOpen) {
      loadExistingShares();
      loadRuns();
    }
  }, [isOpen, loadExistingShares, loadRuns]);

  const handleCreateShare = async () => {
    setIsCreating(true);
    try {
      const response = await shareApi.create({
        session_id: sessionId,
        share_type: shareType,
        run_ids: shareType === "partial" ? selectedRunIds : undefined,
        visibility,
      });

      // Copy link to clipboard
      const shareUrl = `${window.location.origin}${response.url}`;
      await navigator.clipboard.writeText(shareUrl);
      toast.success(t("share.linkCopied"));

      // Refresh shares list
      await loadExistingShares();
    } catch (error) {
      console.error("Failed to create share:", error);
      toast.error(t("share.createFailed") || "Failed to create share");
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopyLink = async (shareId: string) => {
    const shareUrl = `${window.location.origin}/shared/${shareId}`;
    await navigator.clipboard.writeText(shareUrl);
    setCopiedId(shareId);
    toast.success(t("share.linkCopied"));
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDeleteShare = async (shareId: string) => {
    try {
      await shareApi.delete(shareId);
      toast.success(t("share.deleteSuccess"));
      await loadExistingShares();
    } catch (error) {
      console.error("Failed to delete share:", error);
      toast.error(t("share.deleteFailed"));
    }
  };

  const toggleRunSelection = (runId: string) => {
    setSelectedRunIds((prev) =>
      prev.includes(runId)
        ? prev.filter((id) => id !== runId)
        : [...prev, runId],
    );
  };

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop - using solid color instead of backdrop-blur for better performance */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-lg mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-gray-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-stone-700">
          <div className="flex items-center gap-2">
            <Share2 size={20} className="text-blue-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-stone-100">
              {t("share.title")}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
          >
            <X size={20} className="text-gray-500 dark:text-stone-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Session name */}
          <div className="text-sm text-gray-600 dark:text-stone-400">
            <span className="font-medium">{t("share.session")}:</span>{" "}
            {sessionName || t("sidebar.newChat")}
          </div>

          {/* Share Type */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-stone-300">
              {t("share.shareType")}
            </label>
            <div className="flex gap-3">
              <button
                onClick={() => setShareType("full")}
                className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                  shareType === "full"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400"
                    : "border-gray-200 dark:border-stone-600 text-gray-700 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700"
                }`}
              >
                {t("share.fullSession")}
              </button>
              <button
                onClick={() => setShareType("partial")}
                className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                  shareType === "partial"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400"
                    : "border-gray-200 dark:border-stone-600 text-gray-700 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700"
                }`}
              >
                {t("share.partialSession")}
              </button>
            </div>
          </div>

          {/* Run selection for partial share */}
          {shareType === "partial" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("share.selectRuns")}
              </label>
              {isLoadingRuns ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 size={20} className="animate-spin text-gray-400" />
                </div>
              ) : runs.length === 0 ? (
                <div className="text-sm text-gray-500 dark:text-stone-400 py-2">
                  {t("share.noRuns")}
                </div>
              ) : (
                <div className="max-h-40 overflow-y-auto space-y-1 border rounded-lg p-2 dark:border-stone-600">
                  {runs.map((run) => (
                    <button
                      key={run.run_id}
                      onClick={() => toggleRunSelection(run.run_id)}
                      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedRunIds.includes(run.run_id)
                          ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400"
                          : "hover:bg-gray-50 dark:hover:bg-stone-700 text-gray-700 dark:text-stone-300"
                      }`}
                    >
                      <div
                        className={`w-4 h-4 rounded border flex items-center justify-center ${
                          selectedRunIds.includes(run.run_id)
                            ? "border-blue-500 bg-blue-500"
                            : "border-gray-300 dark:border-stone-500"
                        }`}
                      >
                        {selectedRunIds.includes(run.run_id) && (
                          <Check size={12} className="text-white" />
                        )}
                      </div>
                      <span className="truncate">
                        {t("share.run")} #{run.run_id?.slice(0, 8)}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-stone-500">
                        ({run.event_count} {t("share.events")})
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Visibility */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-stone-300">
              {t("share.visibility")}
            </label>
            <div className="space-y-2">
              <button
                onClick={() => setVisibility("public")}
                className={`w-full flex items-start gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                  visibility === "public"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                    : "border-gray-200 dark:border-stone-600 hover:bg-gray-50 dark:hover:bg-stone-700"
                }`}
              >
                <Globe
                  size={20}
                  className={
                    visibility === "public"
                      ? "text-blue-500"
                      : "text-gray-400 dark:text-stone-500"
                  }
                />
                <div>
                  <div
                    className={`text-sm font-medium ${
                      visibility === "public"
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-gray-700 dark:text-stone-300"
                    }`}
                  >
                    {t("share.public")}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-stone-400 mt-0.5">
                    {t("share.publicDesc")}
                  </div>
                </div>
              </button>
              <button
                onClick={() => setVisibility("authenticated")}
                className={`w-full flex items-start gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                  visibility === "authenticated"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                    : "border-gray-200 dark:border-stone-600 hover:bg-gray-50 dark:hover:bg-stone-700"
                }`}
              >
                <Lock
                  size={20}
                  className={
                    visibility === "authenticated"
                      ? "text-blue-500"
                      : "text-gray-400 dark:text-stone-500"
                  }
                />
                <div>
                  <div
                    className={`text-sm font-medium ${
                      visibility === "authenticated"
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-gray-700 dark:text-stone-300"
                    }`}
                  >
                    {t("share.authenticated")}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-stone-400 mt-0.5">
                    {t("share.authenticatedDesc")}
                  </div>
                </div>
              </button>
            </div>
          </div>

          {/* Existing shares */}
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={20} className="animate-spin text-gray-400" />
            </div>
          ) : existingShares.length > 0 ? (
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("share.existingShares")}
              </label>
              <div className="space-y-2">
                {existingShares.map((share) => (
                  <div
                    key={share.id}
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-stone-900/50 rounded-lg border border-gray-200 dark:border-stone-700"
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
                      <span className="text-xs text-gray-500 dark:text-stone-400 truncate">
                        /shared/{share.share_id}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-stone-500">
                        (
                        {share.share_type === "full"
                          ? t("share.fullSession")
                          : t("share.partialSession")}
                        )
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleCopyLink(share.share_id)}
                        className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-stone-700 transition-colors"
                        title={t("share.copyLink")}
                      >
                        {copiedId === share.share_id ? (
                          <Check size={14} className="text-green-500" />
                        ) : (
                          <Copy
                            size={14}
                            className="text-gray-400 dark:text-stone-500"
                          />
                        )}
                      </button>
                      <button
                        onClick={() => handleDeleteShare(share.id)}
                        className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-stone-700 transition-colors"
                        title={t("share.deleteShare")}
                      >
                        <Trash2
                          size={14}
                          className="text-gray-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400"
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
        <div className="flex items-center justify-end gap-2 px-5 py-4 bg-gray-50 dark:bg-stone-900/50 border-t border-gray-100 dark:border-stone-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-gray-200 dark:border-stone-600 rounded-lg hover:bg-gray-50 dark:hover:bg-stone-700 transition-colors"
          >
            {t("common.close")}
          </button>
          <button
            onClick={handleCreateShare}
            disabled={
              isCreating ||
              (shareType === "partial" && selectedRunIds.length === 0)
            }
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isCreating ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Share2 size={16} />
            )}
            {t("share.createShare")}
          </button>
        </div>
      </div>
    </div>
  );
}
