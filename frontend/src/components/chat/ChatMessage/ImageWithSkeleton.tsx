import { useState, useCallback, useEffect } from "react";
import { getFullUrl } from "../../../services/api/config";

/** Tracks URLs that have already loaded — skip skeleton for cached images */
const loadedImages = new Set<string>();

interface ImageWithSkeletonProps {
  /** Image source URL (will be resolved via getFullUrl if relative) */
  src?: string;
  /**
   * Lightweight thumbnail URL (already resolved, used as-is). Rendered in
   * place of src; when it fails to load the original src is tried once
   * before the error state kicks in.
   */
  thumbSrc?: string;
  alt?: string;
  className?: string;
  loading?: "lazy" | "eager";
  onClick?: () => void;
  /** Skip getFullUrl resolution (src is already absolute or data: URI) */
  skipUrlResolve?: boolean;
  /** Render inline without wrapper div (for thumbnails, avatars, etc.) */
  inline?: boolean;
  /** Aspect ratio for skeleton placeholder, e.g. "16/10", "1/1", "4/3" */
  aspectRatio?: string;
  /** Wrapper className for the outer container */
  wrapperClassName?: string;
  /** img element style overrides */
  style?: React.CSSProperties;
  /** Custom error fallback (e.g. avatar initial letter). Defaults to generic placeholder. */
  errorFallback?: React.ReactNode;
  /** Optional callback when image loads successfully */
  onLoad?: () => void;
  /** Optional callback when image fails to load */
  onError?: () => void;
}

/**
 * Renders an <img> with a shimmer skeleton placeholder while loading.
 * Uses the shared `.skeleton-line` CSS class for consistent skeleton styling.
 *
 * Modes:
 * - Default (block): wraps in a relative container with rounded-lg shadow
 * - Inline: no wrapper, just the img + hidden skeleton — fits inside existing containers
 */
export function ImageWithSkeleton({
  src,
  thumbSrc,
  alt,
  className,
  loading = "lazy",
  onClick,
  skipUrlResolve = false,
  inline = false,
  aspectRatio = "16 / 10",
  wrapperClassName,
  style,
  errorFallback,
  onLoad: onExternalLoad,
  onError: onExternalError,
}: ImageWithSkeletonProps) {
  const resolvedSrc = skipUrlResolve ? src : getFullUrl(src);
  const [srcUsed, setSrcUsed] = useState<string | undefined>(
    () => thumbSrc ?? resolvedSrc,
  );
  const [isLoaded, setIsLoaded] = useState(() =>
    loadedImages.has((thumbSrc ?? resolvedSrc) ?? ""),
  );
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const initial = thumbSrc ?? resolvedSrc;
    setSrcUsed(initial);
    setHasError(false);
    setIsLoaded(loadedImages.has(initial ?? ""));
  }, [thumbSrc, resolvedSrc]);

  const handleLoad = useCallback(() => {
    setIsLoaded(true);
    if (srcUsed) loadedImages.add(srcUsed);
    onExternalLoad?.();
  }, [onExternalLoad, srcUsed]);
  const handleError = useCallback(() => {
    if (srcUsed !== resolvedSrc && resolvedSrc) {
      // Thumbnail unavailable (unsupported provider/format) — try the
      // original once before reporting failure.
      setSrcUsed(resolvedSrc);
      return;
    }
    setIsLoaded(true);
    setHasError(true);
    onExternalError?.();
  }, [srcUsed, resolvedSrc, onExternalError]);

  if (!resolvedSrc) return null;

  // Inline mode: skeleton sits behind the img in the same space, no extra wrapper
  if (inline) {
    return (
      <div className={`relative overflow-hidden ${className ?? ""}`}>
        {!isLoaded && !hasError && (
          <div className="absolute inset-0 skeleton-line rounded-[inherit]" />
        )}
        {hasError ? (
          errorFallback ?? (
            <div className="absolute inset-0 flex items-center justify-center bg-stone-100 dark:bg-stone-800 rounded-[inherit]">
              <span className="text-xs text-stone-400 truncate px-1">
                {alt || "…"}
              </span>
            </div>
          )
        ) : (
          <img
            src={srcUsed}
            alt={alt}
            loading={loading}
            onLoad={handleLoad}
            onError={handleError}
            onClick={onClick}
            referrerPolicy="no-referrer"
            style={{
              opacity: isLoaded ? 1 : 0,
              transition: isLoaded ? "opacity 0.3s ease" : "none",
              width: "100%",
              height: "100%",
              objectFit: "cover",
              ...style,
            }}
          />
        )}
      </div>
    );
  }

  // Block mode: full wrapper with skeleton, error state
  return (
    <div
      className={`relative my-2 overflow-hidden rounded-lg shadow ${
        wrapperClassName ?? ""
      }`}
    >
      {/* Skeleton placeholder */}
      {!isLoaded && !hasError && (
        <div
          className="skeleton-line w-full rounded-lg"
          style={{ aspectRatio }}
        />
      )}

      {/* Actual image */}
      {!hasError && (
        <img
          src={srcUsed}
          alt={alt}
          loading={loading}
          onLoad={handleLoad}
          onError={handleError}
          onClick={onClick}
          className={`${
            !isLoaded ? "absolute inset-0 pointer-events-none" : ""
          } ${className ?? ""}`}
          style={{
            opacity: isLoaded ? 1 : 0,
            transition: isLoaded ? "opacity 0.3s ease" : "none",
            maxWidth: "100%",
            height: isLoaded ? "auto" : "100%",
            width: "100%",
            objectFit: isLoaded ? undefined : "cover",
            cursor: onClick ? "zoom-in" : undefined,
            ...style,
          }}
        />
      )}

      {/* Error state */}
      {hasError &&
        (errorFallback ?? (
          <div
            className="flex items-center justify-center rounded-lg text-xs text-stone-400"
            style={{
              aspectRatio,
              backgroundColor: "var(--theme-bg-card, #f5f5f4)",
              border: "1px solid var(--theme-border, #e7e5e4)",
            }}
          >
            <span>{alt || "Image failed to load"}</span>
          </div>
        ))}
    </div>
  );
}
