/**
 * 反馈管理面板 - ChatGPT 风格
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  ThumbsUp,
  ThumbsDown,
  Trash2,
  MessageSquare,
  Star,
  TrendingUp,
  Copy,
  Check,
} from "lucide-react";
import { PanelHeader } from "../../components/common/PanelHeader";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { PanelFilterSelect } from "../../components/common";
import { FeedbackPanelSkeleton } from "../../components/skeletons";
import { Pagination } from "../../components/common/Pagination";
import { feedbackApi } from "./api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Feedback,
  FeedbackStats,
  RatingValue,
} from "./types";
import { formatDateTimeShort, formatDateTime } from "../../utils/datetime";
import { copyToClipboard } from "../../utils/clipboard";

// Stats card component
function StatsCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
}) {
  return (
    <div className="glass-card rounded-xl p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--glass-bg-subtle)]">
          <Icon size={24} className="text-stone-600 dark:text-stone-400" />
        </div>
        <div>
          <p className="text-xs text-stone-500 dark:text-stone-400">{label}</p>
          <p className="text-xl font-bold text-stone-900 dark:text-stone-100">
            {value}
          </p>
        </div>
      </div>
    </div>
  );
}

// Feedback detail modal
function FeedbackDetailModal({
  feedback,
  onClose,
  onCopy,
  copiedField,
}: {
  feedback: Feedback;
  onClose: () => void;
  onCopy: (text: string, field: string) => void;
  copiedField: string | null;
}) {
  const { t } = useTranslation();

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/50  transition-opacity"
        onClick={onClose}
      />
      {/* Modal */}
      <div className="safe-area-viewport-padding fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-lg transform overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] p-6 text-left align-middle shadow-xl transition-all"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {t("feedback.detailTitle") || "Feedback Details"}
            </h3>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
            >
              <span className="sr-only">{t("common.close", "关闭")}</span>
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* User Info */}
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300 font-semibold text-lg">
                {feedback.username.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="font-medium text-stone-900 dark:text-stone-100">
                  {feedback.username}
                </p>
                <p className="text-sm text-stone-500 dark:text-stone-400">
                  {formatDateTime(feedback.created_at)}
                </p>
              </div>
            </div>

            {/* Rating */}
            <div className="flex items-center gap-2 mb-6">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${
                  feedback.rating === "up"
                    ? "bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300"
                    : "bg-stone-800 text-stone-300 dark:bg-stone-200 dark:text-stone-700"
                }`}
              >
                {feedback.rating === "up" ? (
                  <ThumbsUp size={16} />
                ) : (
                  <ThumbsDown size={16} />
                )}
                {feedback.rating === "up"
                  ? t("feedback.positive")
                  : t("feedback.negative")}
              </span>
            </div>

            {/* Session & Run IDs */}
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                  Session ID
                </label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-600 dark:bg-stone-800 dark:text-stone-300 font-mono truncate">
                    {feedback.session_id}
                  </code>
                  <button
                    onClick={() => onCopy(feedback.session_id, "session")}
                    className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                    title={t("documents.copy")}
                  >
                    {copiedField === "session" ? (
                      <Check size={16} />
                    ) : (
                      <Copy size={16} />
                    )}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">
                  Run ID
                </label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-600 dark:bg-stone-800 dark:text-stone-300 font-mono truncate">
                    {feedback.run_id}
                  </code>
                  <button
                    onClick={() => onCopy(feedback.run_id, "run")}
                    className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                    title={t("documents.copy")}
                  >
                    {copiedField === "run" ? (
                      <Check size={16} />
                    ) : (
                      <Copy size={16} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
          {/* Comment */}
          {feedback.comment && (
            <div>
              <label className="block text-xs font-medium text-stone-500 dark:text-stone-400 mb-2">
                {t("feedback.comment") || "Comment"}
              </label>
              <div className="rounded-xl bg-[var(--glass-bg-subtle)] p-4 text-sm text-stone-700 dark:text-stone-300 whitespace-pre-wrap">
                {feedback.comment}
              </div>
            </div>
          )}

          {/* Close button */}
          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="rounded-xl border border-[var(--glass-border)] bg-[var(--theme-bg-card)] px-4 py-2.5 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 dark:text-stone-300 dark:hover:bg-stone-700"
            >
              {t("common.close") || "Close"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// Helper function removed - using formatDateTime from shared utility

export function FeedbackPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [feedbackList, setFeedbackList] = useState<Feedback[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [ratingFilter, setRatingFilter] = useState<RatingValue | undefined>(
    undefined,
  );
  const [deleteTarget, setDeleteTarget] = useState<Feedback | null>(null);
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(
    null,
  );
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const canDelete = hasPermission(Permission.FEEDBACK_ADMIN);

  // Copy to clipboard
  const handleCopy = async (text: string, field: string) => {
    try {
      await copyToClipboard(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

  // Fetch feedback data
  const fetchFeedback = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await feedbackApi.list(skip, limit, ratingFilter);
      setFeedbackList(response.items);
      setStats(response.stats);
      setTotal(response.total);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [skip, limit, ratingFilter, t]);

  // Initial load
  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  // Reset to first page when filters change
  useEffect(() => {
    setSkip(0);
  }, [ratingFilter]);

  // Handle delete
  const handleDelete = async () => {
    if (!deleteTarget) return;

    try {
      await feedbackApi.delete(deleteTarget.id);
      toast.success(t("feedback.deleteSuccess"));
      setDeleteTarget(null);
      fetchFeedback();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("feedback.deleteFailed");
      toast.error(message);
    }
  };

  // Format date - using shared utility
  const formatDateLocal = (dateString: string) =>
    formatDateTimeShort(dateString);

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("feedback.title")}
        subtitle={t("feedback.subtitle")}
        icon={<Star size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <PanelFilterSelect
            value={ratingFilter || ""}
            onChange={(v) =>
              setRatingFilter(v ? (v as RatingValue) : undefined)
            }
            options={[
              { value: "", label: t("feedback.allRatings") },
              { value: "up", label: t("feedback.positive") },
              { value: "down", label: t("feedback.negative") },
            ]}
          />
        }
      />

      {/* Stats Section - Modern card design */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 sm:gap-4">
          <StatsCard
            icon={MessageSquare}
            label={t("feedback.totalCount")}
            value={stats.total_count}
          />
          <StatsCard
            icon={ThumbsUp}
            label={t("feedback.positive")}
            value={stats.up_count}
          />
          <StatsCard
            icon={ThumbsDown}
            label={t("feedback.negative")}
            value={stats.down_count}
          />
          <StatsCard
            icon={TrendingUp}
            label={t("feedback.positiveRate")}
            value={`${stats.up_percentage.toFixed(1)}%`}
          />
        </div>
      )}

      {/* Feedback List - ChatGPT style */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6">
        {isLoading && feedbackList.length === 0 ? (
          <FeedbackPanelSkeleton />
        ) : !isLoading && feedbackList.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-stone-100 dark:bg-stone-800">
              <ThumbsUp
                size={32}
                className="text-stone-400 dark:text-stone-500"
              />
            </div>
            <p className="text-lg font-medium text-stone-700 dark:text-stone-300">
              {t("feedback.noFeedback")}
            </p>
            <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
              {t("feedback.noFeedbackHint")}
            </p>
          </div>
        ) : (
          <>
            {/* Mobile card view - modern style */}
            <div className="space-y-3 sm:hidden">
              {feedbackList.map((feedback) => (
                <button
                  key={feedback.id}
                  onClick={() => setSelectedFeedback(feedback)}
                  className="group relative w-full text-left overflow-hidden glass-card rounded-xl p-4 hover:border-stone-300 dark:hover:border-stone-600 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    {/* User Info */}
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300 text-sm font-medium">
                        {feedback.username.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-stone-900 dark:text-stone-100">
                          {feedback.username}
                        </p>
                        <p className="text-xs text-stone-400 dark:text-stone-500">
                          {formatDateLocal(feedback.created_at)}
                        </p>
                      </div>
                    </div>
                    {/* Rating & Actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                          feedback.rating === "up"
                            ? "bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300"
                            : "bg-stone-800 text-stone-300 dark:bg-stone-200 dark:text-stone-700"
                        }`}
                      >
                        {feedback.rating === "up" ? (
                          <ThumbsUp size={12} />
                        ) : (
                          <ThumbsDown size={12} />
                        )}
                      </span>
                      {canDelete && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget(feedback);
                          }}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-400 transition-all hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                          title={t("feedback.delete")}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Comment */}
                  {feedback.comment && (
                    <div className="mt-3 rounded-lg bg-[var(--glass-bg-subtle)] p-3 text-sm text-stone-600 dark:text-stone-300 whitespace-pre-wrap">
                      {feedback.comment}
                    </div>
                  )}
                </button>
              ))}
            </div>

            {/* Desktop card view - modern style */}
            <div className="hidden space-y-3 sm:block">
              {feedbackList.map((feedback) => (
                <button
                  key={feedback.id}
                  onClick={() => setSelectedFeedback(feedback)}
                  className="group relative w-full text-left overflow-hidden glass-card rounded-xl p-5 hover:border-stone-300 dark:hover:border-stone-600 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* User Info */}
                    <div className="flex items-center gap-4">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300 font-medium">
                        {feedback.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-medium text-stone-900 dark:text-stone-100">
                          {feedback.username}
                        </p>
                        <p className="text-xs text-stone-400 dark:text-stone-500">
                          {formatDateLocal(feedback.created_at)}
                        </p>
                      </div>
                    </div>

                    {/* Rating Badge */}
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
                        feedback.rating === "up"
                          ? "bg-[var(--glass-bg-subtle)] text-stone-600 dark:text-stone-300"
                          : "bg-stone-800 text-stone-300 dark:bg-stone-200 dark:text-stone-700"
                      }`}
                    >
                      {feedback.rating === "up" ? (
                        <ThumbsUp size={14} />
                      ) : (
                        <ThumbsDown size={14} />
                      )}
                      {feedback.rating === "up"
                        ? t("feedback.positive")
                        : t("feedback.negative")}
                    </span>

                    {/* Delete Button */}
                    {canDelete && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(feedback);
                        }}
                        className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-400 transition-all hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/30 dark:hover:text-red-400 opacity-0 group-hover:opacity-100"
                        title={t("feedback.delete")}
                      >
                        <Trash2 size={18} />
                      </button>
                    )}
                  </div>

                  {/* Comment */}
                  {feedback.comment && (
                    <div className="mt-4 rounded-xl bg-[var(--glass-bg-subtle)] p-4 text-sm text-stone-600 dark:text-stone-300 whitespace-pre-wrap">
                      {feedback.comment}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="glass-divider bg-transparent px-4 py-4 sm:px-6">
          <Pagination
            page={Math.floor(skip / limit) + 1}
            pageSize={limit}
            total={total}
            onChange={(page) => setSkip((page - 1) * limit)}
          />
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title={t("feedback.deleteConfirmTitle")}
        message={t("feedback.deleteConfirm")}
        confirmText={t("feedback.delete")}
        cancelText={t("common.cancel")}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
        variant="danger"
      />

      {/* Feedback Detail Modal */}
      {selectedFeedback && (
        <FeedbackDetailModal
          feedback={selectedFeedback}
          onClose={() => setSelectedFeedback(null)}
          onCopy={handleCopy}
          copiedField={copiedField}
        />
      )}
    </div>
  );
}
