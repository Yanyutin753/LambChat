import { memo } from "react";

interface PptPreviewProps {
  url: string;
}

const PptPreview = memo(function PptPreview({ url }: PptPreviewProps) {
  // Use Microsoft's Office Online viewer for PPT
  const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(
    url,
  )}`;

  return (
    <div className="h-full w-full flex flex-col">
      <iframe
        src={officeUrl}
        className="flex-1 w-full min-h-[400px] border-0"
        title="PowerPoint Preview"
      />
    </div>
  );
});

export default PptPreview;
