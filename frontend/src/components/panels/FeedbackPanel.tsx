/**
 * 反馈管理面板
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  ThumbsUp,
  ThumbsDown,
  Trash2,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
} from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { feedbackApi } from "../../services/api/feedback";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Feedback,
  FeedbackStats,
  RatingValue,
} from "../../types/feedback";

// Rating display component
function RatingBadge({ rating }: { rating: RatingValue }) {
  const { t } = useTranslation();
  return rating === "up" ? (
    <div className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full">
      <ThumbsUp size={14} className="fill-current" />
      <span className="text-xs font-medium">{t("feedback.positive")}</span>
    </div>
  ) : (
    <div className="flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full">
      <ThumbsDown size={14} className="fill-current" />
      <span className="text-xs font-medium">{t("feedback.negative")}</span>
    </div>
  );
}

// Delete confirmation modal
function DeleteConfirmModal({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-stone-800 rounded-lg shadow-xl p-6 max-w-sm">
        <div className="flex items-center gap-3 mb-4">
          <AlertCircle className="text-red-500" size={24} />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-stone-100">
            {t("feedback.deleteConfirmTitle")}
          </h3>
        </div>
        <p className="text-sm text-gray-500 dark:text-stone-400 mb-6">
          {t("feedback.deleteConfirm")}
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-stone-300 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
          >
            {t("feedback.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

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

  const canDelete = hasPermission(Permission.FEEDBACK_ADMIN);

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

  // Format date
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Render loading state
  if (isLoading && feedbackList.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner />
      </div>
    );
  }

  // Render empty state
  if (!isLoading && feedbackList.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-stone-400">
        <ThumbsUp className="mb-4" size={48} />
        <p className="text-lg font-medium">{t("feedback.noFeedback")}</p>
        <p className="text-sm">{t("feedback.noFeedbackHint")}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="panel-header">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100">
              {t("feedback.title")}
            </h1>
            <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
              {t("feedback.subtitle")}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Section */}
      {stats && (
        <div className="flex-shrink-0 grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50 dark:bg-stone-800/50">
          {/* Total Count */}
          <div className="bg-white dark:bg-stone-800 rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <MessageSquare className="text-blue-500" size={20} />
              </div>
              <div>
                <p className="text-2xs text-gray-500 dark:text-stone-400">
                  {t("feedback.totalCount")}
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-stone-100">
                  {stats.total_count}
                </p>
              </div>
            </div>
          </div>

          {/* Up Count */}
          <div className="bg-white dark:bg-stone-800 rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                <ThumbsUp className="text-green-500" size={20} />
              </div>
              <div>
                <p className="text-2xs text-gray-500 dark:text-stone-400">
                  {t("feedback.positive")}
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-stone-100">
                  {stats.up_count}
                </p>
              </div>
            </div>
          </div>

          {/* Down Count */}
          <div className="bg-white dark:bg-stone-800 rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
                <ThumbsDown className="text-red-500" size={20} />
              </div>
              <div>
                <p className="text-2xs text-gray-500 dark:text-stone-400">
                  {t("feedback.negative")}
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-stone-100">
                  {stats.down_count}
                </p>
              </div>
            </div>
          </div>

          {/* Positive Rate */}
          <div className="bg-white dark:bg-stone-800 rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
                <ThumbsUp className="text-amber-500" size={20} />
              </div>
              <div>
                <p className="text-2xs text-gray-500 dark:text-stone-400">
                  {t("feedback.positiveRate") || "Positive Rate"}
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-stone-100">
                  {stats.up_percentage.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex-shrink-0 flex flex-col md:flex-row gap-4 p-4 bg-gray-50 dark:bg-stone-800/50">
        {/* Rating Filter */}
        <div className="flex-1">
          <label className="text-sm font-medium text-gray-700 dark:text-stone-300 mb-1">
            {t("feedback.filterByRating")}
          </label>
          <select
            value={ratingFilter || ""}
            onChange={(e) =>
              setRatingFilter(
                e.target.value ? (e.target.value as RatingValue) : undefined,
              )
            }
            className="mt-1 block w-full rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-800 px-3 py-2 text-sm text-gray-900 dark:text-stone-100"
          >
            <option value="">{t("feedback.allRatings")}</option>
            <option value="up">👍 {t("feedback.positive")}</option>
            <option value="down">👎 {t("feedback.negative")}</option>
          </select>
        </div>
      </div>

      {/* Feedback List */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-amber-500" size={24} />
          </div>
        ) : feedbackList.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-stone-400">
            <AlertCircle size={32} />
            <p className="mt-2">{t("feedback.noFeedback")}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {feedbackList.map((feedback) => (
              <div
                key={feedback.id}
                className="bg-white dark:bg-stone-800 rounded-lg border border-gray-200 dark:border-stone-700 p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-4">
                  {/* User Info */}
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-medium">
                      {feedback.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 dark:text-stone-100">
                        {feedback.username}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-stone-400">
                        {formatDate(feedback.created_at)}
                      </p>
                    </div>
                  </div>

                  {/* Rating Badge */}
                  <RatingBadge rating={feedback.rating} />

                  {/* Delete Button */}
                  {canDelete && (
                    <button
                      onClick={() => setDeleteTarget(feedback)}
                      className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
                      title={t("feedback.delete")}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>

                {/* Comment */}
                {feedback.comment && (
                  <div className="mt-3 p-3 bg-gray-50 dark:bg-stone-700/50 rounded-lg">
                    <p className="text-sm text-gray-700 dark:text-stone-300 whitespace-pre-wrap">
                      {feedback.comment}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex-shrink-0 flex items-center justify-between border-t border-gray-200 dark:border-stone-700 bg-white dark:bg-stone-800 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-stone-400">
            <span>
              {t("common.showing", {
                start: skip + 1,
                end: Math.min(skip + limit, total),
              })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSkip(Math.max(0, skip - limit))}
              disabled={skip === 0}
              className="p-1 rounded hover:bg-gray-100 dark:hover:bg-stone-700 disabled:opacity-50"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm text-gray-500 dark:text-stone-400">
              {t("common.page", { page: Math.floor(skip / limit) + 1 })}
            </span>
            <button
              onClick={() => setSkip(Math.min(skip + limit, total - limit))}
              disabled={skip + limit >= total}
              className="p-1 rounded hover:bg-gray-100 dark:hover:bg-stone-700 disabled:opacity-50"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <DeleteConfirmModal
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
