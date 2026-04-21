import { ZoomIcon } from "./Icons";

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
    <div
      data-reveal-scale
      className="blog-screenshot-card group relative rounded-2xl overflow-hidden cursor-pointer bg-white/80 dark:bg-stone-900/40 transition-all duration-500 hover:-translate-y-1.5 hover:shadow-2xl"
      onClick={onClick}
    >
      <div className="relative aspect-[4/3] bg-stone-50 dark:bg-stone-800/20 overflow-hidden">
        <img
          src={src}
          alt={alt}
          className="w-full h-full object-cover object-top transition-all duration-700 ease-out group-hover:scale-[1.03]"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-transparent via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="opacity-0 group-hover:opacity-100 transition-all duration-500 scale-75 group-hover:scale-100 w-11 h-11 rounded-full bg-white/90 dark:bg-stone-800/90 shadow-xl shadow-black/10 dark:shadow-black/40 flex items-center justify-center text-stone-500 dark:text-stone-400">
            <ZoomIcon />
          </div>
        </div>
      </div>
      <div className="px-4 py-3 border-t border-stone-100/40 dark:border-stone-800/20">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-stone-400 dark:text-stone-500 truncate">
            {alt}
          </span>
          {label && (
            <span className="text-[9px] text-stone-300 dark:text-stone-600 font-semibold tracking-[0.1em] uppercase shrink-0 ml-3">
              {label}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
