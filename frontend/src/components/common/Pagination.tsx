/**
 * Pagination Component - Page number navigation
 */

import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.ceil(total / pageSize);

  if (totalPages <= 1) return null;

  const pages = getPageNumbers(page, totalPages);
  const startItem = (page - 1) * pageSize + 1;
  const endItem = Math.min(page * pageSize, total);

  return (
    <div className="pagination-wrapper">
      {/* Info */}
      <p className="text-sm text-stone-500 dark:text-stone-400 whitespace-nowrap">
        {startItem}-{endItem} / {total}
      </p>

      {/* Page controls */}
      <div className="pagination-controls">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page === 1}
          className="pagination-btn"
          aria-label={t("common.previous")}
        >
          <ChevronLeft size={16} />
        </button>

        {pages.map((p, idx) =>
          p === "..." ? (
            <span key={`ellipsis-${idx}`} className="pagination-ellipsis">
              <MoreHorizontal size={14} />
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onChange(p as number)}
              className={`pagination-page ${
                p === page ? "pagination-page-active" : ""
              }`}
            >
              {p}
            </button>
          ),
        )}

        <button
          onClick={() => onChange(page + 1)}
          disabled={page === totalPages}
          className="pagination-btn"
          aria-label={t("common.next")}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

/**
 * Generate page numbers with ellipsis for large page counts
 */
function getPageNumbers(current: number, total: number): (number | string)[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | string)[] = [];

  // Always show first page
  pages.push(1);

  if (current > 3) {
    pages.push("...");
  }

  // Show pages around current
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push("...");
  }

  // Always show last page
  if (total > 1) {
    pages.push(total);
  }

  return pages;
}

export default Pagination;
