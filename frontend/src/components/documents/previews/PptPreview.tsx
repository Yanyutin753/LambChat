import { memo } from "react";

interface PptPreviewProps {
  url: string;
  arrayBuffer?: ArrayBuffer | null;
  fileName: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

const PptPreview = memo(function PptPreview({
  url,
  fileName,
}: PptPreviewProps) {
  // For PowerPoint files (.ppt and .pptx), use Office Online iframe for reliable rendering
  // This avoids issues with pptx-preview library where element positions can be incorrect
  // when the PPT's original dimensions don't match the fixed 960x540 rendering size

  // Ensure the source URL uses HTTPS to avoid Mixed Content errors
  const secureUrl = url.replace(/^http:/i, "https:");
  const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(
    secureUrl,
  )}`;

  return (
    <div className="h-full w-full flex flex-col">
      <iframe
        src={officeUrl}
        className="flex-1 w-full min-h-[400px] border-0"
        title={`PowerPoint Preview - ${fileName}`}
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
    </div>
  );
});

export default PptPreview;
