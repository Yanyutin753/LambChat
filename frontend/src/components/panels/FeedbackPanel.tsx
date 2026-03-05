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
  MessageSquare,
} from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Pagination } from "../common/Pagination";
import { feedbackApi } from "../../services/api/feedback";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Feedback,
  FeedbackStats,
  RatingValue,
} from "../../types/feedback";

// Delete confirmation modal with bottom sheet pattern
function DeleteConfirmModal({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();

  return (
    <>
      <div className="fixed inset-0" onClick={onCancel} />
      <div className="modal-bottom-sheet sm:modal-centered-wrapper">
        <div className="modal-bottom-sheet-content sm:modal-centered-content">
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Header */}
          <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <AlertCircle
                  className="text-red-600 dark:text-red-400"
                  size={20}
                />
              </div>
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                {t("feedback.deleteConfirmTitle")}
              </h3>
            </div>
          </div>
          {/* Content */}
          <div className="px-6 py-4">
            <p className="text-sm text-stone-500 dark:text-stone-400">
              {t("feedback.deleteConfirm")}
            </p>
          </div>
          {/* Actions */}
          <div className="flex gap-3 border-t border-stone-200 px-6 py-4 dark:border-stone-800">
            <button onClick={onCancel} className="btn-secondary flex-1">
              {t("common.cancel")}
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            >
              {t("feedback.delete")}
            </button>
          </div>
        </div>
      </div>
    </>
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
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="lg" className="mx-auto mb-4" />
          <p className="text-stone-500 dark:text-stone-400">
            {t("common.loading")}
          </p>
        </div>
      </div>
    );
  }

  // Render empty state
  if (!isLoading && feedbackList.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <ThumbsUp
          size={48}
          className="mb-4 text-stone-300 dark:text-stone-600"
        />
        <p className="text-lg font-medium text-stone-500 dark:text-stone-400">
          {t("feedback.noFeedback")}
        </p>
        <p className="text-sm text-stone-400 dark:text-stone-500">
          {t("feedback.noFeedbackHint")}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
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
          {/* Filter dropdown */}
          <div className="relative">
            <select
              value={ratingFilter || ""}
              onChange={(e) =>
                setRatingFilter(
                  e.target.value ? (e.target.value as RatingValue) : undefined,
                )
              }
              className="panel-search w-full sm:w-40"
            >
              <option value="">{t("feedback.allRatings")}</option>
              <option value="up">👍 {t("feedback.positive")}</option>
              <option value="down">👎 {t("feedback.negative")}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Stats Section */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 sm:gap-4 sm:p-4 bg-stone-50 dark:bg-stone-800/50">
          {/* Total Count */}
          <div className="rounded-xl border border-stone-200 bg-white p-3 sm:p-4 dark:border-stone-700 dark:bg-stone-900">
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="p-1.5 sm:p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <MessageSquare className="text-blue-500" size={18} />
              </div>
              <div>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("feedback.totalCount")}
                </p>
                <p className="text-lg sm:text-2xl font-bold text-stone-900 dark:text-stone-100">
                  {stats.total_count}
                </p>
              </div>
            </div>
          </div>

          {/* Up Count */}
          <div className="rounded-xl border border-stone-200 bg-white p-3 sm:p-4 dark:border-stone-700 dark:bg-stone-900">
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="p-1.5 sm:p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                <ThumbsUp className="text-green-500" size={18} />
              </div>
              <div>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("feedback.positive")}
                </p>
                <p className="text-lg sm:text-2xl font-bold text-stone-900 dark:text-stone-100">
                  {stats.up_count}
                </p>
              </div>
            </div>
          </div>

          {/* Down Count */}
          <div className="rounded-xl border border-stone-200 bg-white p-3 sm:p-4 dark:border-stone-700 dark:bg-stone-900">
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="p-1.5 sm:p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
                <ThumbsDown className="text-red-500" size={18} />
              </div>
              <div>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("feedback.negative")}
                </p>
                <p className="text-lg sm:text-2xl font-bold text-stone-900 dark:text-stone-100">
                  {stats.down_count}
                </p>
              </div>
            </div>
          </div>

          {/* Positive Rate */}
          <div className="rounded-xl border border-stone-200 bg-white p-3 sm:p-4 dark:border-stone-700 dark:bg-stone-900">
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="p-1.5 sm:p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
                <ThumbsUp className="text-amber-500" size={18} />
              </div>
              <div>
                <p className="text-xs text-stone-500 dark:text-stone-400">
                  {t("feedback.positiveRate")}
                </p>
                <p className="text-lg sm:text-2xl font-bold text-stone-900 dark:text-stone-100">
                  {stats.up_percentage.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Feedback List */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-6">
        {isLoading ? (
          <div className="flex h-32 items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : feedbackList.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center text-stone-500 dark:text-stone-400">
            <AlertCircle size={32} />
            <p className="mt-2">{t("feedback.noFeedback")}</p>
          </div>
        ) : (
          <>
            {/* Mobile card view */}
            <div className="space-y-3 sm:hidden">
              {feedbackList.map((feedback) => (
                <div key={feedback.id} className="panel-card">
                  {/* Header row: avatar, name, rating, delete */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="h-9 w-9 flex-shrink-0 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-sm font-medium">
                        {feedback.username.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-stone-900 dark:text-stone-100">
                          {feedback.username}
                        </p>
                        <p className="text-xs text-stone-500 dark:text-stone-400">
                          {formatDate(feedback.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span
                        className={`tag ${
                          feedback.rating === "up" ? "tag-success" : "tag-error"
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
                          onClick={() => setDeleteTarget(feedback)}
                          className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                          title={t("feedback.delete")}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Comment */}
                  {feedback.comment && (
                    <div className="mt-3 rounded-lg bg-stone-50 p-3 dark:bg-stone-800/50">
                      <p className="text-sm text-stone-700 dark:text-stone-300 whitespace-pre-wrap">
                        {feedback.comment}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Desktop card view */}
            <div className="hidden space-y-4 sm:block">
              {feedbackList.map((feedback) => (
                <div key={feedback.id} className="panel-card">
                  <div className="flex items-start justify-between gap-4">
                    {/* User Info */}
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-medium">
                        {feedback.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-medium text-stone-900 dark:text-stone-100">
                          {feedback.username}
                        </p>
                        <p className="text-xs text-stone-500 dark:text-stone-400">
                          {formatDate(feedback.created_at)}
                        </p>
                      </div>
                    </div>

                    {/* Rating Badge */}
                    <span
                      className={`tag ${
                        feedback.rating === "up" ? "tag-success" : "tag-error"
                      }`}
                    >
                      {feedback.rating === "up" ? (
                        <ThumbsUp size={12} />
                      ) : (
                        <ThumbsDown size={12} />
                      )}
                      {feedback.rating === "up"
                        ? t("feedback.positive")
                        : t("feedback.negative")}
                    </span>

                    {/* Delete Button */}
                    {canDelete && (
                      <button
                        onClick={() => setDeleteTarget(feedback)}
                        className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                        title={t("feedback.delete")}
                      >
                        <Trash2 size={18} />
                      </button>
                    )}
                  </div>

                  {/* Comment */}
                  {feedback.comment && (
                    <div className="mt-3 rounded-lg bg-stone-50 p-3 dark:bg-stone-800/50">
                      <p className="text-sm text-stone-700 dark:text-stone-300 whitespace-pre-wrap">
                        {feedback.comment}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="border-t border-stone-200 px-3 py-3 dark:border-stone-800 sm:px-6">
          <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-between">
            <p className="text-sm text-stone-500 dark:text-stone-400">
              {t("feedback.paginationInfo", {
                start: Math.floor(skip / limit) * limit + 1,
                end: Math.min(skip + limit, total),
                total,
              })}
            </p>
            <Pagination
              page={Math.floor(skip / limit) + 1}
              pageSize={limit}
              total={total}
              onChange={(page) => setSkip((page - 1) * limit)}
            />
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
