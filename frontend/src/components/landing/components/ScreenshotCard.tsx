import { ZoomIcon } from "./Icons";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";

interface ScreenshotCardProps {
  src: string;
  alt: string;
  onClick: () => void;
  label?: string;
}

export function ScreenshotCard({
  src,
  alt,
  onClick,
  label,
}: ScreenshotCardProps) {
  return (
    <button
      type="button"
      aria-label={alt}
      data-reveal-scale
      className="blog-screenshot-card public-preview group relative overflow-hidden cursor-pointer"
      onClick={onClick}
    >
      <div className="relative aspect-video bg-theme-bg-secondary overflow-hidden">
        <ImageWithSkeleton
          src={src}
          alt={alt}
          skipUrlResolve
          inline
          className="w-full h-full object-cover object-top transition-transform duration-300 ease-out group-hover:scale-[1.01]"
        />
        <div className="absolute right-3 top-3 flex items-center justify-center">
          <div className="opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity duration-200 w-9 h-9 rounded-lg bg-theme-bg-card border border-theme-border flex items-center justify-center text-theme-text-secondary">
            <ZoomIcon />
          </div>
        </div>
      </div>
      <div className="px-4 py-3 border-t border-theme-border-subtle">
        <div className="flex items-center justify-between">
          <span className="text-14 font-medium text-theme-text-secondary truncate">
            {alt}
          </span>
          {label && (
            <span className="text-12 text-theme-text-tertiary shrink-0 ml-3">
              {label}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
