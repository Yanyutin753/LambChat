import { memo, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Document, Page, pdfjs } from "react-pdf";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { DocumentViewerFrame } from "./DocumentViewerFrame";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface PdfPreviewProps {
  url: string;
}

const PDF_NATURAL_PAGE_WIDTH = 980;

const PdfPreview = memo(function PdfPreview({ url }: PdfPreviewProps) {
  const { t } = useTranslation();
  const [numPages, setNumPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    setNumPages(0);
    setLoading(true);
    setLoadFailed(false);
  }, [url]);

  const pageCountLabel = numPages
    ? t("documents.pdfPageCount", "{{count}} 页", { count: numPages })
    : t("documents.pdfPreviewTitle", "PDF 预览");

  if (loadFailed) {
    return (
      <div className="flex h-full min-h-[400px] w-full flex-col items-center justify-center gap-4 bg-stone-100 px-6 text-center dark:bg-stone-950">
        <div>
          <p className="text-sm font-medium text-stone-700 dark:text-stone-200">
            {t("documents.pdfPreviewUnavailable", "PDF 预览不可用")}
          </p>
          <p className="mt-1 max-w-sm text-xs text-stone-500 dark:text-stone-400">
            {t(
              "documents.pdfPreviewUnavailableHint",
              "当前浏览器无法在页面内打开这个 PDF，可以在新窗口中查看。",
            )}
          </p>
        </div>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-stone-700 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-stone-300"
        >
          {t("documents.openInNewTab", "在新窗口打开")}
        </a>
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-[400px] w-full">
      <DocumentViewerFrame
        naturalWidth={PDF_NATURAL_PAGE_WIDTH}
        loading={loading}
        ariaLabel={pageCountLabel}
      >
        {({ displayScale }) => {
          const pageWidth = Math.round(PDF_NATURAL_PAGE_WIDTH * displayScale);

          return (
            <Document
              file={url}
              onLoadSuccess={({ numPages: loadedPageCount }) => {
                setNumPages(loadedPageCount);
                setLoading(false);
              }}
              onLoadError={() => {
                setLoading(false);
                setLoadFailed(true);
              }}
              loading={null}
              error={null}
              className="flex flex-col items-center gap-4 sm:gap-5"
            >
              {Array.from({ length: numPages }, (_, pageNumber) => (
                <Page
                  key={`page_${pageNumber + 1}`}
                  pageNumber={pageNumber + 1}
                  width={pageWidth}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  loading={
                    <div
                      className="flex items-center justify-center bg-white shadow-xl ring-1 ring-black/5"
                      style={{
                        width: pageWidth,
                        minHeight: Math.round(pageWidth * 1.35),
                      }}
                    >
                      <LoadingSpinner className="text-stone-300" size="sm" />
                    </div>
                  }
                  className="overflow-hidden bg-white shadow-xl ring-1 ring-black/5"
                />
              ))}
            </Document>
          );
        }}
      </DocumentViewerFrame>

      {numPages > 0 && (
        <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-lg bg-black/60 px-2.5 py-1.5 text-xs font-medium text-white/75 backdrop-blur-sm sm:left-4 sm:top-4">
          {pageCountLabel}
        </div>
      )}
    </div>
  );
});

export default PdfPreview;
