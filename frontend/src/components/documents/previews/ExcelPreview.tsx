import { memo, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import * as XLSX from "xlsx";

interface ExcelPreviewProps {
  arrayBuffer: ArrayBuffer;
  fileName: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

interface SheetData {
  name: string;
  data: unknown[][];
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

  useEffect(() => {
    const parseExcel = async () => {
      try {
        const workbook = XLSX.read(arrayBuffer, { type: "array" });
        const sheetData = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name];
          const data = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
          }) as unknown[][];
          return { name, data };
        });
        setSheets(sheetData);
        setError(null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t("documents.excelParseError"),
        );
      } finally {
        setLoading(false);
      }
    };
    parseExcel();
  }, [arrayBuffer, t]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2
          size={32}
          className="animate-spin text-stone-400 dark:text-stone-500"
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

  const currentSheet = sheets[activeSheet];

  return (
    <div className="flex flex-col h-full">
      {/* Sheet tabs */}
      {sheets.length > 1 && (
        <div className="flex gap-1 p-2 border-b border-stone-200 dark:border-stone-700 overflow-x-auto">
          {sheets.map((sheet: SheetData, index) => (
            <button
              key={sheet.name}
              onClick={() => setActiveSheet(index)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-colors ${
                activeSheet === index
                  ? "bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900"
                  : "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700"
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto p-4">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-stone-200 dark:divide-stone-700">
            <thead className="bg-stone-50 dark:bg-stone-800">
              {currentSheet.data.slice(0, 1).map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <th
                      key={cellIndex}
                      className="px-4 py-2 text-left text-xs font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider bg-stone-100 dark:bg-stone-800"
                    >
                      {String(cell ?? "")}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-stone-200 dark:divide-stone-700 bg-white dark:bg-stone-900">
              {currentSheet.data.slice(1).map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className="hover:bg-stone-50 dark:hover:bg-stone-800/50"
                >
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className="px-4 py-2 text-sm text-stone-600 dark:text-stone-400 whitespace-nowrap"
                    >
                      {String(cell ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
});

export default ExcelPreview;
