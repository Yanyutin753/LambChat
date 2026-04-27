import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { LoadingSpinner } from "../../common/LoadingSpinner";

interface ExcelPreviewProps {
  arrayBuffer: ArrayBuffer;
  fileName: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

interface SheetData {
  name: string;
  data: unknown[][];
}

function colLabel(index: number): string {
  let label = "";
  let n = index;
  while (n >= 0) {
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26) - 1;
  }
  return label;
}

function isNumeric(v: unknown): boolean {
  if (v == null || v === "") return false;
  return !isNaN(Number(v));
}

const ExcelPreview = memo(function ExcelPreview({
  arrayBuffer,
  fileName: _fileName,
  t,
}: ExcelPreviewProps) {
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hoveredCell, setHoveredCell] = useState<{
    row: number;
    col: number;
  } | null>(null);

  useEffect(() => {
    const parseExcel = async () => {
      try {
        const XLSX = await import("xlsx");
        const workbook = XLSX.read(arrayBuffer, { type: "array" });
        const sheetData = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name];
          // Use sheet_to_json with header:1 to get raw 2D array
          const raw = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
            defval: "",
            raw: true,
          }) as unknown[][];

          // Ensure every row has the same length (pad with "")
          const maxLen = raw.reduce((m, r) => Math.max(m, r.length), 0);
          const padded = raw.map((r) => {
            if (r.length < maxLen) {
              return [...r, ...Array(maxLen - r.length).fill("")];
            }
            return r;
          });

          return { name, data: padded };
        });
        setSheets(sheetData);
        setError(null);
      } catch (err) {
        console.error("Excel parse error:", err);
        setError(
          err instanceof Error ? err.message : t("documents.excelParseError"),
        );
      } finally {
        setLoading(false);
      }
    };
    parseExcel();
  }, [arrayBuffer, t]);

  const currentSheet = sheets[activeSheet];

  const totalRows = useMemo(() => {
    if (!currentSheet) return 0;
    return currentSheet.data.length;
  }, [currentSheet]);

  const totalCols = useMemo(() => {
    if (!currentSheet || currentSheet.data.length === 0) return 0;
    return currentSheet.data[0].length;
  }, [currentSheet]);

  // First row is header, rest is data
  const headerRow = useMemo(() => {
    if (!currentSheet || currentSheet.data.length === 0) return [];
    return currentSheet.data[0];
  }, [currentSheet]);

  const dataRows = useMemo(() => {
    if (!currentSheet || currentSheet.data.length <= 1) return [];
    return currentSheet.data.slice(1);
  }, [currentSheet]);

  const handleCellHover = useCallback((rowIndex: number, colIndex: number) => {
    setHoveredCell({ row: rowIndex, col: colIndex });
  }, []);

  const handleCellLeave = useCallback(() => {
    setHoveredCell(null);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner
          size="lg"
          className="text-stone-400 dark:text-stone-500"
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
        <p className="text-sm text-red-600 dark:text-red-400 font-medium">
          {t("documents.excelPreviewError")}: {error}
        </p>
      </div>
    );
  }

  // Get value from all rows (header is row -1 conceptually)
  function getCellValue(rowIndex: number, colIndex: number): string {
    if (rowIndex === -1) {
      return headerRow[colIndex] != null ? String(headerRow[colIndex]) : "";
    }
    if (dataRows[rowIndex]) {
      const v = dataRows[rowIndex][colIndex];
      return v != null && v !== "" ? String(v) : "";
    }
    return "";
  }

  const displayRows = totalRows; // includes header

  return (
    <div className="flex flex-col h-full bg-white dark:bg-stone-950">
      {/* Formula bar */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-50 dark:bg-stone-900 border-b border-stone-200 dark:border-stone-700 shrink-0">
        <span className="text-[11px] font-bold text-stone-600 dark:text-stone-400 w-8 text-center shrink-0 italic">
          fx
        </span>
        <span className="text-[12px] text-stone-500 dark:text-stone-400 truncate font-mono min-w-[3rem]">
          {hoveredCell
            ? `${colLabel(hoveredCell.col)}${hoveredCell.row + 1}`
            : "A1"}
        </span>
        <span className="h-4 w-px bg-stone-300 dark:bg-stone-600 shrink-0" />
        <span className="text-[12px] text-stone-700 dark:text-stone-300 truncate">
          {hoveredCell
            ? getCellValue(hoveredCell.row, hoveredCell.col)
            : headerRow.length > 0
              ? String(headerRow[0] ?? "")
              : ""}
        </span>
      </div>

      {/* Sheet tabs */}
      <div className="flex items-center gap-0.5 px-1 py-0 bg-stone-100 dark:bg-stone-900 border-b border-stone-300 dark:border-stone-700 shrink-0">
        <button
          type="button"
          onClick={() => setActiveSheet((p) => Math.max(0, p - 1))}
          disabled={activeSheet === 0}
          className="p-1 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 disabled:opacity-30 disabled:cursor-default transition-colors"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <div className="flex-1 flex items-center gap-0.5 overflow-x-auto px-1 py-1">
          {sheets.map((sheet: SheetData, index) => (
            <button
              key={sheet.name}
              onClick={() => setActiveSheet(index)}
              className={`px-3 py-0.5 text-[11px] font-medium rounded-sm whitespace-nowrap transition-all ${
                activeSheet === index
                  ? "bg-white dark:bg-stone-800 text-stone-800 dark:text-stone-100 shadow-sm border border-stone-300 dark:border-stone-600"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-200/50 dark:hover:bg-stone-800/50"
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() =>
            setActiveSheet((p) => Math.min(sheets.length - 1, p + 1))
          }
          disabled={activeSheet === sheets.length - 1}
          className="p-1 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 disabled:opacity-30 disabled:cursor-default transition-colors"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      {/* Spreadsheet grid */}
      <div className="flex-1 overflow-auto relative">
        <table className="border-collapse w-max min-w-full text-[13px]">
          {/* Column headers row */}
          <thead>
            <tr className="sticky top-0 z-10">
              {/* Top-left corner */}
              <th className="sticky left-0 z-20 w-10 min-w-[2.5rem] max-w-[2.5rem] px-0 py-0 text-center text-[11px] text-stone-500 dark:text-stone-400 bg-stone-100 dark:bg-stone-800 border border-stone-300 dark:border-stone-600 select-none" />
              {/* Column letters */}
              {Array.from({ length: totalCols }, (_, i) => (
                <th
                  key={i}
                  className={`min-w-[80px] h-6 px-0 py-0 text-center text-[11px] font-normal text-stone-500 dark:text-stone-400 bg-stone-100 dark:bg-stone-800 border border-stone-300 dark:border-stone-600 select-none leading-6 ${
                    hoveredCell?.col === i
                      ? "bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                      : ""
                  }`}
                >
                  {colLabel(i)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: displayRows }, (_, rawRowIndex) => {
              const isHeader = rawRowIndex === 0;
              const rowIndex = isHeader ? -1 : rawRowIndex - 1; // -1 for header in getCellValue
              const isRowHovered =
                hoveredCell && !isHeader && hoveredCell.row === rawRowIndex - 1;

              return (
                <tr key={rawRowIndex}>
                  {/* Row number */}
                  <td
                    className={`sticky left-0 z-10 w-10 min-w-[2.5rem] max-w-[2.5rem] px-0 py-0 text-center text-[11px] bg-stone-100 dark:bg-stone-800 border border-stone-300 dark:border-stone-600 select-none tabular-nums leading-6 ${
                      isHeader
                        ? "text-stone-400 dark:text-stone-500"
                        : isRowHovered
                          ? "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/40"
                          : "text-stone-500 dark:text-stone-400"
                    }`}
                  >
                    {isHeader ? "" : rawRowIndex}
                  </td>
                  {/* Cells */}
                  {Array.from({ length: totalCols }, (_, colIndex) => {
                    const value = getCellValue(rowIndex, colIndex);
                    const num = isNumeric(value);
                    const isCellHovered =
                      hoveredCell &&
                      !isHeader &&
                      hoveredCell.row === rawRowIndex - 1 &&
                      hoveredCell.col === colIndex;

                    // Header cells use th-style, data cells use td-style
                    if (isHeader) {
                      return (
                        <th
                          key={colIndex}
                          onMouseEnter={() => handleCellHover(0, colIndex)}
                          onMouseLeave={handleCellLeave}
                          className={`min-h-[24px] min-w-[80px] px-2 py-0 text-[13px] leading-6 border border-stone-300 dark:border-stone-600 whitespace-nowrap text-left font-semibold text-stone-700 dark:text-stone-300 bg-stone-50 dark:bg-stone-800/60 ${
                            isCellHovered
                              ? "!outline outline-2 outline-blue-500 dark:outline-blue-400 outline-offset-[-1px] bg-blue-50/60 dark:bg-blue-900/25 !border-blue-400 dark:!border-blue-500"
                              : ""
                          }`}
                        >
                          {value || " "}
                        </th>
                      );
                    }

                    return (
                      <td
                        key={colIndex}
                        onMouseEnter={() =>
                          handleCellHover(rawRowIndex - 1, colIndex)
                        }
                        onMouseLeave={handleCellLeave}
                        className={`min-h-[24px] min-w-[80px] px-2 py-0 text-[13px] leading-6 border border-stone-200 dark:border-stone-700/80 whitespace-nowrap ${
                          num
                            ? "text-right tabular-nums font-mono"
                            : "text-left"
                        } ${
                          isCellHovered
                            ? "!outline outline-2 outline-blue-500 dark:outline-blue-400 outline-offset-[-1px] bg-blue-50/60 dark:bg-blue-900/25 !border-blue-400 dark:!border-blue-500"
                            : isRowHovered
                              ? "bg-stone-50/70 dark:bg-stone-800/30"
                              : ""
                        }`}
                      >
                        {value || " "}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Empty state */}
        {totalRows === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-stone-400 dark:text-stone-500">
            <p className="text-sm">{t("documents.noData") || "No data"}</p>
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-3 py-1 text-[11px] text-stone-500 dark:text-stone-400 bg-stone-100 dark:bg-stone-800 border-t border-stone-300 dark:border-stone-600 shrink-0">
        <span className="tabular-nums">
          {sheets.length > 1 && (
            <span className="mr-2 text-stone-400 dark:text-stone-500">
              {currentSheet?.name}
            </span>
          )}
          {dataRows.length} 行 × {totalCols} 列
        </span>
        <div className="flex items-center gap-3">
          {hoveredCell && (
            <span className="px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-mono">
              {colLabel(hoveredCell.col)}
              {hoveredCell.row + 1}
            </span>
          )}
          <span className="text-stone-400 dark:text-stone-500">就绪</span>
        </div>
      </div>
    </div>
  );
});

export default ExcelPreview;
