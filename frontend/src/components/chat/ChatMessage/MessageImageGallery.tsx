import { useMemo } from "react";
import { ExternalLink } from "lucide-react";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import { useSessionImageGallery } from "./sessionImageGallery";
import type { RevealFileImageInfo } from "./revealFileImageUtils";

interface MessageImageGalleryProps {
  images: RevealFileImageInfo[];
}

export function MessageImageGallery({ images }: MessageImageGalleryProps) {
  const sessionImageGallery = useSessionImageGallery();

  const handleImageClick = (image: RevealFileImageInfo) => {
    sessionImageGallery?.openImage(image.src, image.fileName, {
      group: "reveal-file",
    });
  };

  const layoutClass = useMemo(() => {
    const count = images.length;
    if (count === 1) return "flex justify-center";
    if (count <= 3) return "grid grid-cols-2 gap-2";
    return "columns-2 gap-2";
  }, [images.length]);

  return (
    <div className={layoutClass}>
      {images.map((image, index) => {
        const isFirstOfThree = images.length === 3 && index === 0;
        return (
          <div
            key={image.id}
            className={
              isFirstOfThree
                ? "col-span-2"
                : images.length === 1
                  ? "w-full max-w-md"
                  : "break-inside-avoid"
            }
          >
            <div
              className="group relative cursor-pointer rounded-xl border overflow-hidden transition-shadow hover:shadow-lg border-theme-border bg-white dark:bg-theme-bg"
              onClick={() => handleImageClick(image)}
            >
              <ImageWithSkeleton
                src={image.src}
                alt={image.fileName}
                skipUrlResolve
                inline
                className="w-full h-auto object-contain"
                loading="lazy"
              />
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center pointer-events-none">
                <div className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-full bg-white/90 dark:bg-theme-bg-card/90 shadow-lg pointer-events-auto cursor-pointer">
                  <ExternalLink
                    size={16}
                    className="text-theme-text-secondary"
                  />
                </div>
              </div>
              {/* File name label on hover */}
              <div className="absolute bottom-0 left-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="px-2 py-1 bg-gradient-to-t from-black/60 to-transparent">
                  <span className="text-[11px] text-white/90 truncate block">
                    {image.fileName}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
