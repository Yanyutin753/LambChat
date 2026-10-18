import { useClientPagination } from "../../hooks/useClientPagination";
import { useTranslation } from "react-i18next";
import { Pagination } from "../common/Pagination";
import type { UsageResetHistory } from "../../services/api/usage";

export function ResetCardHistory({
  history,
  timezone,
}: {
  history: UsageResetHistory[];
  timezone: string;
}) {
  const { t, i18n } = useTranslation();
  const { page, setPage, totalPages } = useClientPagination({
    total: history.length,
    pageSize: 10,
  });
  const sorted = [...history].sort(
    (a, b) => Date.parse(b.redeemed_at) - Date.parse(a.redeemed_at),
  );
  const currentPage = Math.min(page, totalPages);
  return (
    <section
      aria-label={t("usage.resetCardHistory")}
      className="space-y-2 border-t border-theme-border py-3"
    >
      <h3 className="text-13 font-semibold text-theme-text">
        {t("usage.resetCardHistory")}
      </h3>
      <p className="text-12 text-theme-text-muted">
        {t("usage.resetCardHistoryRetention")}
      </p>
      {history.length === 0 ? (
        <p className="text-12 text-theme-text-muted">
          {t("usage.resetCardHistoryEmpty")}
        </p>
      ) : (
        <>
          <div
            className="ai-data-table ai-data-table__scroll overflow-x-auto font-sans"
            tabIndex={0}
          >
            <table
              aria-label={t("usage.resetCardHistory")}
              className="ai-data-table__table whitespace-nowrap"
            >
              <thead className="ai-data-table__head">
                <tr className="ai-data-table__row">
                  {[
                    "usage.bulkCardsType",
                    "usage.resetCardUsedAt",
                    "usage.status",
                  ].map((key) => (
                    <th
                      key={key}
                      scope="col"
                      className="ai-data-table__header-cell"
                    >
                      {t(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="ai-data-table__body">
                {sorted
                  .slice((currentPage - 1) * 10, currentPage * 10)
                  .map((entry) => (
                    <tr key={entry.id} className="ai-data-table__row">
                      <td className="ai-data-table__cell">
                        {t(
                          entry.window === "five_hour"
                            ? "usage.fiveHourCard"
                            : entry.window === "weekly"
                              ? "usage.weeklyCard"
                              : "usage.legacyResetCard",
                        )}
                      </td>
                      <td className="ai-data-table__cell">
                        <time
                          dateTime={entry.redeemed_at}
                          className="tabular-nums"
                        >
                          {new Date(entry.redeemed_at).toLocaleString(
                            i18n.language,
                            {
                              timeZone: timezone,
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            },
                          )}
                        </time>
                      </td>
                      <td className="ai-data-table__cell">
                        {t("usage.resetCardUsed")}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {history.length > 10 && (
            <Pagination
              page={currentPage}
              pageSize={10}
              total={history.length}
              onChange={setPage}
            />
          )}
        </>
      )}
    </section>
  );
}
