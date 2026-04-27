import { memo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from "lucide-react";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfPreviewProps {
  url: string;
}

const PdfPreview = memo(function PdfPreview({ url }: PdfPreviewProps) {
  const { t } = useTranslation();
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);
  const [loading, setLoading] = useState(true);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setLoading(false);
  };

  const goToPrevPage = () => setPageNumber((prev) => Math.max(prev - 1, 1));
  const goToNextPage = () =>
    setPageNumber((prev) => Math.min(prev + 1, numPages));

  const zoomIn = () => setScale((prev) => Math.min(prev + 0.25, 3));
  const zoomOut = () => setScale((prev) => Math.max(prev - 0.25, 0.5));
  const fitWidth = () => setScale(1.0);

  return (
    <div className="h-full w-full flex flex-col bg-stone-200 dark:bg-stone-950">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-stone-100 dark:bg-stone-900 border-b border-stone-300 dark:border-stone-700 shrink-0">
        {/* Page navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={goToPrevPage}
            disabled={pageNumber <= 1}
            className="p-1.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed text-stone-500 dark:text-stone-400 transition-colors"
            title={t("documents.previousPage")}
          >
            <ChevronLeft size={16} />
          </button>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white dark:bg-stone-800 border border-stone-300 dark:border-stone-600">
            <input
              type="number"
              value={pageNumber}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                if (v >= 1 && v <= numPages) setPageNumber(v);
              }}
              className="w-8 text-center text-xs text-stone-700 dark:text-stone-300 bg-transparent outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <span className="text-[11px] text-stone-400 dark:text-stone-500">
              /
            </span>
            <span className="text-xs text-stone-500 dark:text-stone-400 tabular-nums">
              {numPages || "--"}
            </span>
          </div>
          <button
            onClick={goToNextPage}
            disabled={pageNumber >= numPages}
            className="p-1.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed text-stone-500 dark:text-stone-400 transition-colors"
            title={t("documents.nextPage")}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={zoomOut}
            disabled={scale <= 0.5}
            className="p-1.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed text-stone-500 dark:text-stone-400 transition-colors"
            title={t("documents.zoomOut")}
          >
            <ZoomOut size={16} />
          </button>
          <button
            onClick={fitWidth}
            className="px-2 py-0.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 text-[11px] font-medium text-stone-500 dark:text-stone-400 tabular-nums transition-colors"
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            onClick={zoomIn}
            disabled={scale >= 3}
            className="p-1.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed text-stone-500 dark:text-stone-400 transition-colors"
            title={t("documents.zoomIn")}
          >
            <ZoomIn size={16} />
          </button>
          <div className="w-px h-4 bg-stone-300 dark:bg-stone-600 mx-0.5" />
          <button
            onClick={fitWidth}
            className="p-1.5 rounded-md hover:bg-stone-200 dark:hover:bg-stone-800 text-stone-500 dark:text-stone-400 transition-colors"
            title="适合宽度"
          >
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      {/* PDF content */}
      <div className="flex-1 overflow-auto flex items-start justify-center py-6 px-4">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <LoadingSpinner
              className="text-stone-400 dark:text-stone-500"
              size="lg"
            />
          </div>
        )}
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={(error) => console.error("PDF load error:", error)}
          loading={null}
          className={loading ? "hidden" : ""}
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            className="shadow-2xl rounded-sm"
          />
        </Document>
      </div>
    </div>
  );
});

export default PdfPreview;
