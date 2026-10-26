import type { ComponentProps } from "react";
import { buildFileCoverUrl } from "../../utils/chatThumbs";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";

export function AudioWithCover({
  posterSource,
  ...props
}: ComponentProps<"audio"> & { posterSource?: string }) {
  const cover = buildFileCoverUrl(posterSource || props.src);
  return (
    <div className="flex w-full min-w-0 flex-col gap-3">
      {cover && (
        <ImageWithSkeleton
          src={cover}
          alt=""
          inline
          className="max-h-36 w-full rounded-lg object-contain"
        />
      )}
      <audio {...props} preload={props.preload || "none"} />
    </div>
  );
}
