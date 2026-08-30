/**
 * 反馈管理面板 — 电商平台评价风格
 *
 * 布局参考淘宝/京东评价页：
 * - 顶部：好评率大数字 + 分布统计条
 * - 标签栏：全部 / 好评 / 差评（带数量角标）
 * - 列表：连续卡片 + 分隔线
 * - 图片：3 列网格，hover 放大
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  ThumbsUp,
  ThumbsDown,
  Trash2,
  Star,
  Copy,
  Check,
  ChevronRight,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { FeedbackPanelSkeleton } from "../skeletons";
import { Pagination } from "../common/Pagination";
import { ImageViewer } from "../common";
import { feedbackApi } from "../../services/api/feedback";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Feedback,
  FeedbackStats,
  RatingValue,
} from "../../types/feedback";
import { formatDateTimeShort, formatDateTime } from "../../utils/datetime";
import { copyToClipboard } from "../../utils/clipboard";

// ─── Rating summary header ───

function RatingSummary({ stats }: { stats: FeedbackStats }) {
  const { t } = useTranslation();
  const upPct = stats.up_percentage;

  return (
    <div className="mx-4 sm:mx-6 mt-4 mb-3 p-4 rounded-2xl bg-gradient-to-br from-stone-50 via-white to-stone-50 dark:from-stone-800 dark:via-stone-800/80 dark:to-stone-900 border border-stone-200/60 dark:border-stone-700/50">
      <div className="flex items-center gap-5">
        {/* Left: big percentage */}
        <div className="flex flex-col items-center flex-shrink-0">
          <div className="relative">
            <svg className="w-20 h-20 -rotate-90" viewBox="0 0 36 36">
              <circle
                cx="18"
                cy="18"
                r="15.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                className="text-stone-100 dark:text-stone-700"
              />
              <circle
                cx="18"
                cy="18"
                r="15.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeDasharray={`${upPct * 0.9738} 100`}
                strokeLinecap="round"
                className="text-emerald-500 dark:text-emerald-400"
                style={{ transition: "stroke-dasharray 0.8s ease-out" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-bold font-serif tabular-nums text-stone-900 dark:text-stone-100 leading-none">
                {upPct.toFixed(0)}
                <span className="text-xs font-semibold">%</span>
              </span>
            </div>
          </div>
          <span className="mt-1.5 text-10 text-stone-400 dark:text-stone-500 font-medium">
            {t("feedback.positiveRate")}
          </span>
        </div>

        {/* Right: distribution bars */}
        <div className="flex-1 space-y-2.5 min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="w-7 text-11 text-stone-500 dark:text-stone-400 flex-shrink-0">
              {t("feedback.positive")}
            </span>
            <div className="flex-1 h-2 rounded-full bg-stone-100 dark:bg-stone-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-500"
                style={{
                  width: `${Math.max(upPct, 2)}%`,
                  transition: "width 0.6s ease-out",
                }}
              />
            </div>
            <span className="w-8 text-right text-11 font-semibold text-emerald-600 dark:text-emerald-400 tabular-nums flex-shrink-0">
              {stats.up_count}
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="w-7 text-11 text-stone-500 dark:text-stone-400 flex-shrink-0">
              {t("feedback.negative")}
            </span>
            <div className="flex-1 h-2 rounded-full bg-stone-100 dark:bg-stone-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-red-300 to-red-400 dark:from-red-500 dark:to-red-400"
                style={{
                  width: `${Math.max(100 - upPct, 2)}%`,
                  transition: "width 0.6s ease-out",
                }}
              />
            </div>
            <span className="w-8 text-right text-11 font-semibold text-red-500 dark:text-red-400 tabular-nums flex-shrink-0">
              {stats.down_count}
            </span>
          </div>
          <div className="pt-1 border-t border-stone-100 dark:border-stone-700/60">
            <span className="text-11 text-stone-400 dark:text-stone-500">
              {t("feedback.totalCount")}&nbsp;
              <span className="font-semibold text-stone-600 dark:text-stone-300">
                {stats.total_count}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Filter tabs ───

type FilterKey = "all" | "up" | "down";

function FilterTabs({
  active,
  stats,
  onChange,
}: {
  active: FilterKey;
  stats: FeedbackStats;
  onChange: (key: FilterKey) => void;
}) {
  const { t } = useTranslation();

  const tabs: { key: FilterKey; label: string; count: number }[] = [
    { key: "all", label: t("feedback.allRatings"), count: stats.total_count },
    { key: "up", label: t("feedback.positive"), count: stats.up_count },
    { key: "down", label: t("feedback.negative"), count: stats.down_count },
  ];

  return (
    <div className="flex items-center gap-1 px-4 sm:px-6 pb-3">
      {tabs.map((tab) => {
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`relative flex items-center gap-1.5 px-3.5 py-[7px] rounded-lg text-13 font-medium whitespace-nowrap transition-all duration-200 ${
              isActive
                ? "bg-stone-900 text-white dark:bg-white dark:text-stone-900 shadow-sm"
                : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-100 dark:hover:bg-white/5"
            }`}
          >
            {tab.label}
            <span
              className={`min-w-[20px] text-center px-1 py-0.5 rounded-full text-10 font-semibold tabular-nums ${
                isActive
                  ? "bg-white/20 dark:bg-stone-900/20 text-inherit"
                  : "bg-stone-100 dark:bg-stone-700 text-stone-400 dark:text-stone-500"
              }`}
            >
              {tab.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ─── Image grid (3-column) ───

function ReviewImageGrid({
  attachments,
  onImageClick,
}: {
  attachments: NonNullable<Feedback["attachments"]>;
  onImageClick: (index: number) => void;
}) {
  const maxShow = 9;
  const shown = attachments.slice(0, maxShow);
  const remaining = attachments.length - maxShow;

  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((att, idx) => (
        <button
          key={att.id}
          onClick={(e) => {
            e.stopPropagation();
            onImageClick(idx);
          }}
          title={att.name}
          className="group/thumb relative h-16 w-16 overflow-hidden rounded-lg bg-stone-100 dark:bg-stone-800 flex-shrink-0
            transition-all duration-200 ease-out
            hover:scale-105 hover:shadow-md hover:shadow-stone-400/30 dark:hover:shadow-stone-900/50 hover:z-10
            active:scale-[0.97]"
        >
          <img
            src={att.url}
            alt={att.name}
            className="h-full w-full object-cover"
            loading="lazy"
          />
          <div className="absolute inset-0 bg-black/0 group-hover/thumb:bg-black/10 transition-colors duration-200 pointer-events-none rounded-lg" />
        </button>
      ))}
      {remaining > 0 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onImageClick(0);
          }}
          className="h-16 w-16 overflow-hidden rounded-lg bg-stone-100 dark:bg-stone-800
            flex items-center justify-center flex-shrink-0
            hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors"
        >
          <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">
            +{remaining}
          </span>
        </button>
      )}
    </div>
  );
}

// ─── Feedback card ───

function FeedbackCard({
  feedback,
  canDelete,
  onViewDetail,
  onDelete,
  onImageClick,
}: {
  feedback: Feedback;
  canDelete: boolean;
  onViewDetail: () => void;
  onDelete: () => void;
  onImageClick: (index: number) => void;
}) {
  const { t } = useTranslation();
  const hasImages = feedback.attachments && feedback.attachments.length > 0;
  const isUp = feedback.rating === "up";

  return (
    <div
      className="px-4 sm:px-6 py-4 border-b border-stone-100/80 dark:border-stone-800/60 last:border-b-0
      hover:bg-stone-50/60 dark:hover:bg-white/[0.02] transition-colors duration-150"
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full
            bg-gradient-to-br from-stone-200 to-stone-300 dark:from-stone-600 dark:to-stone-700
            text-stone-500 dark:text-stone-300 text-11 font-bold"
          >
            {feedback.username.charAt(0).toUpperCase()}
          </div>
          <span className="text-13 font-medium text-stone-800 dark:text-stone-200 truncate">
            {feedback.username}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span
            className={`inline-flex items-center gap-1 text-11 font-medium select-none ${
              isUp
                ? "text-amber-600 dark:text-amber-400"
                : "text-stone-400 dark:text-stone-500"
            }`}
          >
            {isUp ? <ThumbsUp size={12} /> : <ThumbsDown size={12} />}
            {isUp ? t("feedback.positive") : t("feedback.negative")}
          </span>
          <span className="text-11 text-stone-300 dark:text-stone-600 tabular-nums">
            {formatDateTimeShort(feedback.created_at)}
          </span>
        </div>
      </div>

      {/* Content: images */}
      {hasImages && (
        <div className="mb-2">
          <ReviewImageGrid
            attachments={feedback.attachments!}
            onImageClick={onImageClick}
          />
        </div>
      )}

      {/* Content: comment */}
      {feedback.comment && (
        <p className="text-13 text-stone-600 dark:text-stone-300 leading-relaxed whitespace-pre-wrap line-clamp-3">
          {feedback.comment}
        </p>
      )}

      {/* Action bar — always visible */}
      <div className="flex items-center justify-between mt-2.5 pt-0">
        <button
          onClick={onViewDetail}
          className="flex items-center gap-0.5 text-11 text-stone-400 dark:text-stone-500
            hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
        >
          <span>{t("feedback.viewDetail", "查看详情")}</span>
          <ChevronRight size={12} />
        </button>

        {canDelete && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="flex items-center gap-1 text-11 text-stone-300 dark:text-stone-600
              hover:text-red-500 dark:hover:text-red-400 transition-colors"
            title={t("feedback.delete")}
          >
            <Trash2 size={12} />
            <span>{t("feedback.delete")}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Detail modal ───

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
  const [viewerSrc, setViewerSrc] = useState<string | null>(null);
  const attachments = feedback.attachments;
  const isUp = feedback.rating === "up";

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="safe-area-viewport-padding fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center">
        <div
          className="w-full sm:max-w-lg bg-white dark:bg-stone-800 sm:rounded-2xl rounded-t-2xl shadow-2xl border-t sm:border border-stone-200/50 dark:border-stone-700/50 max-h-[85vh] flex flex-col animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Handle (mobile) */}
          <div className="sm:hidden flex justify-center pt-3 pb-1">
            <div className="w-8 h-1 rounded-full bg-stone-300 dark:bg-stone-600" />
          </div>

          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-stone-100 dark:border-stone-700/60 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div
                className="flex h-9 w-9 items-center justify-center rounded-full
                bg-gradient-to-br from-stone-200 to-stone-300 dark:from-stone-600 dark:to-stone-700
                text-stone-600 dark:text-stone-200 font-bold text-xs"
              >
                {feedback.username.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="text-sm font-medium text-stone-900 dark:text-stone-100">
                  {feedback.username}
                </p>
                <p className="text-11 text-stone-400 dark:text-stone-500">
                  {formatDateTime(feedback.created_at)}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
            >
              <svg
                className="h-4 w-4"
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

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {/* Rating */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${
                isUp
                  ? "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                  : "bg-stone-100 text-stone-500 dark:bg-stone-700 dark:text-stone-400"
              }`}
            >
              {isUp ? <ThumbsUp size={13} /> : <ThumbsDown size={13} />}
              {isUp ? t("feedback.positive") : t("feedback.negative")}
            </span>

            {/* Images */}
            {attachments && attachments.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {attachments.map((att) => (
                  <button
                    key={att.id}
                    onClick={() => setViewerSrc(att.url || null)}
                    className="aspect-square overflow-hidden rounded-xl bg-stone-100 dark:bg-stone-800
                      hover:opacity-90 transition-opacity active:scale-[0.97]"
                  >
                    <img
                      src={att.url}
                      alt={att.name}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  </button>
                ))}
              </div>
            )}

            {/* Comment */}
            {feedback.comment && (
              <p className="text-sm text-stone-700 dark:text-stone-300 leading-[1.7] whitespace-pre-wrap">
                {feedback.comment}
              </p>
            )}

            {/* Session & Run IDs */}
            <div className="pt-3 mt-1 border-t border-stone-100 dark:border-stone-700/50 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-10 uppercase tracking-wider text-stone-400 dark:text-stone-500 flex-shrink-0 w-[58px]">
                  Session
                </span>
                <code className="flex-1 text-11 text-stone-400 dark:text-stone-500 font-mono truncate bg-stone-50 dark:bg-stone-900/50 rounded px-2 py-1">
                  {feedback.session_id}
                </code>
                <button
                  onClick={() => onCopy(feedback.session_id, "session")}
                  className="flex-shrink-0 p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
                >
                  {copiedField === "session" ? (
                    <Check size={12} className="text-emerald-500" />
                  ) : (
                    <Copy size={12} className="text-stone-400" />
                  )}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-10 uppercase tracking-wider text-stone-400 dark:text-stone-500 flex-shrink-0 w-[58px]">
                  Run
                </span>
                <code className="flex-1 text-11 text-stone-400 dark:text-stone-500 font-mono truncate bg-stone-50 dark:bg-stone-900/50 rounded px-2 py-1">
                  {feedback.run_id}
                </code>
                <button
                  onClick={() => onCopy(feedback.run_id, "run")}
                  className="flex-shrink-0 p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
                >
                  {copiedField === "run" ? (
                    <Check size={12} className="text-emerald-500" />
                  ) : (
                    <Copy size={12} className="text-stone-400" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {viewerSrc && (
        <ImageViewer
          src={viewerSrc}
          isOpen={!!viewerSrc}
          onClose={() => setViewerSrc(null)}
        />
      )}
    </>
  );
}

// ─── Main panel ───

export function FeedbackPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [feedbackList, setFeedbackList] = useState<Feedback[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [deleteTarget, setDeleteTarget] = useState<Feedback | null>(null);
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(
    null,
  );
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [viewerSrc, setViewerSrc] = useState<string | null>(null);

  const canDelete = hasPermission(Permission.FEEDBACK_ADMIN);

  const ratingFilter: RatingValue | undefined = useMemo(() => {
    if (activeFilter === "up") return "up";
    if (activeFilter === "down") return "down";
    return undefined;
  }, [activeFilter]);

  const handleCopy = async (text: string, field: string) => {
    try {
      await copyToClipboard(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

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

  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  const handleFilterChange = useCallback((key: FilterKey) => {
    setActiveFilter(key);
    setSkip(0);
  }, []);

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

  const handleCardImageClick = useCallback(
    (feedback: Feedback, index: number) => {
      if (feedback.attachments && feedback.attachments[index]) {
        setViewerSrc(feedback.attachments[index].url || null);
      }
    },
    [],
  );

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("feedback.title")}
        subtitle={t("feedback.subtitle")}
        icon={<Star size={20} className="text-stone-600 dark:text-stone-400" />}
      />

      {/* Rating summary */}
      {stats && <RatingSummary stats={stats} />}

      {/* Filter tabs */}
      {stats && (
        <FilterTabs
          active={activeFilter}
          stats={stats}
          onChange={handleFilterChange}
        />
      )}

      {/* Feedback list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && feedbackList.length === 0 ? (
          <FeedbackPanelSkeleton />
        ) : !isLoading && feedbackList.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-stone-100 dark:bg-stone-800">
              <ThumbsUp
                size={24}
                className="text-stone-300 dark:text-stone-600"
              />
            </div>
            <p className="text-sm font-medium text-stone-500 dark:text-stone-400">
              {t("feedback.noFeedback")}
            </p>
            <p className="mt-1 text-xs text-stone-400 dark:text-stone-600">
              {t("feedback.noFeedbackHint")}
            </p>
          </div>
        ) : (
          feedbackList.map((feedback) => (
            <FeedbackCard
              key={feedback.id}
              feedback={feedback}
              canDelete={canDelete}
              onViewDetail={() => setSelectedFeedback(feedback)}
              onDelete={() => setDeleteTarget(feedback)}
              onImageClick={(idx) => handleCardImageClick(feedback, idx)}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="glass-divider bg-transparent px-4 py-3 sm:px-6">
          <Pagination
            page={Math.floor(skip / limit) + 1}
            pageSize={limit}
            total={total}
            onChange={(page) => setSkip((page - 1) * limit)}
          />
        </div>
      )}

      {/* Modals */}
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

      {selectedFeedback && (
        <FeedbackDetailModal
          feedback={selectedFeedback}
          onClose={() => setSelectedFeedback(null)}
          onCopy={handleCopy}
          copiedField={copiedField}
        />
      )}

      {viewerSrc && (
        <ImageViewer
          src={viewerSrc}
          isOpen={!!viewerSrc}
          onClose={() => setViewerSrc(null)}
        />
      )}
    </div>
  );
}
