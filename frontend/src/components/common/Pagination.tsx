/**
 * Pagination Component - Page number navigation with mobile responsive layout
 */

import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
  itemLabel?: string;
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  itemLabel,
}: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.max(1, Math.min(page, totalPages));
  const navigationRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (page !== currentPage) onChange(currentPage);
  }, [page, currentPage, onChange]);

  const changePage = (nextPage: number) => {
    onChange(Math.max(1, Math.min(nextPage, totalPages)));
    const panel = navigationRef.current?.closest(
      "[data-panel], .glass-shell, .skill-theme-shell",
    );
    panel?.querySelectorAll<HTMLElement>(".overflow-y-auto").forEach((area) => {
      area.scrollTop = 0;
    });
  };

  if (total === 0) return null;

  const pages = getPageNumbers(currentPage, totalPages);

  return (
    <nav
      ref={navigationRef}
      className="pagination-wrapper"
      aria-label={t("common.pagination")}
    >
      <p className="pagination-summary" aria-live="polite">
        <span className="pagination-range">
          {t("common.paginationSummary", { total, pageSize })}
          {itemLabel ? ` ${itemLabel}` : ""}
        </span>
        <span className="pagination-position">
          {currentPage} / {totalPages}
        </span>
      </p>

      {/* Page controls */}
      {totalPages > 1 && (
        <div className="pagination-controls">
          <button
            type="button"
            onClick={() => changePage(currentPage - 1)}
            disabled={currentPage === 1}
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
                type="button"
                key={p}
                aria-label={t("common.page", { page: p })}
                aria-current={p === currentPage ? "page" : undefined}
                onClick={() => changePage(p as number)}
                className={`pagination-page ${
                  p === currentPage ? "pagination-page-active" : ""
                }`}
              >
                {p}
              </button>
            ),
          )}

          <button
            type="button"
            onClick={() => changePage(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="pagination-btn"
            aria-label={t("common.next")}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </nav>
  );
}

/**
 * Generate page numbers with ellipsis for large page counts.
 * Compact containers hide numbered buttons using CSS.
 */
function getPageNumbers(current: number, total: number): (number | string)[] {
  const maxVisible = 7;

  if (total <= maxVisible) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | string)[] = [];

  pages.push(1);

  if (current > 3) {
    pages.push("...");
  }

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push("...");
  }

  if (total > 1) {
    pages.push(total);
  }

  return pages;
}

export default Pagination;
