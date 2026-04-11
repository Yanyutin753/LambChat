import { useState, useEffect } from "react";
import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api";

const PREVIEW_MAX_LINES = 6;
const PREVIEW_MAX_SIZE = 1024 * 1024; // 1 MB
const CACHE_MAX_SIZE = 100;

const previewCache = new Map<string, string>();

function evictCacheIfNeeded() {
  if (previewCache.size > CACHE_MAX_SIZE) {
    // Delete oldest entries (first inserted)
    const keysToDelete = [...previewCache.keys()].slice(
      0,
      previewCache.size - CACHE_MAX_SIZE,
    );
    for (const key of keysToDelete) {
      previewCache.delete(key);
    }
  }
}

export function useCodePreview(file: RevealedFileItem): string | null {
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (
      file.file_type !== "code" ||
      !file.url ||
      file.file_size > PREVIEW_MAX_SIZE
    )
      return;

    const cacheKey = file.url;
    if (previewCache.has(cacheKey)) {
      setPreview(previewCache.get(cacheKey)!);
      return;
    }

    let cancelled = false;
    const fullUrl = getFullUrl(file.url);
    if (!fullUrl) return;

    fetch(fullUrl)
      .then((res: Response) =>
        res.ok ? res.text() : Promise.reject(res.status),
      )
      .then((text: string) => {
        const lines = text.split("\n", PREVIEW_MAX_LINES + 1);
        const snippet = lines.slice(0, PREVIEW_MAX_LINES).join("\n");
        previewCache.set(cacheKey, snippet);
        evictCacheIfNeeded();
        if (!cancelled) setPreview(snippet);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [file.file_type, file.url, file.file_size]);

  return preview;
}
