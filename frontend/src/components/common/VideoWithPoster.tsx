import type { ComponentProps } from "react";
import { useUploadFileUrl } from "../../hooks/useUploadFileUrl";
import { buildFileCoverUrl } from "../../utils/chatThumbs";

/** One poster path for inline, panel and fullscreen video players. */
export function VideoWithPoster({
  posterSource,
  ...props
}: ComponentProps<"video"> & { posterSource?: string }) {
  const cover = buildFileCoverUrl(posterSource || props.src);
  const poster = useUploadFileUrl(cover);
  return (
    <video
      {...props}
      poster={props.poster || poster.src}
      preload={cover ? "none" : props.preload || "metadata"}
    />
  );
}
