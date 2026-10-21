import { useCallback, useEffect, useState } from "react";
import { getFullUrl } from "../services/api/config";
import { buildProxyFallbackUrl } from "../components/documents/documentFetchCache";

/** Public images load directly; proxy candidates retry once and private captures stay authenticated. */
export function usePrivateImage(src?: string, retry = 0) {
  const url = getFullUrl(src);
  const uploadPrefix = getFullUrl("/api/upload/file/");
  const prefix = getFullUrl("/api/upload/file/cua_screenshots/");
  const legacyPrefix = getFullUrl("/api/upload/file/tool_binaries/");
  const isLegacy = !!url && !!legacyPrefix && url.startsWith(legacyPrefix);
  const isPrivate = isLegacy || (!!url && !!prefix && url.startsWith(prefix));
  const [proxySource, setProxySource] = useState<{
    url: string;
    retry: number;
    src: string;
    attempted: string[];
  }>();
  const [image, setImage] = useState<{
    url?: string;
    src?: string;
    failed: boolean;
  }>({ failed: false });
  useEffect(() => {
    setProxySource(undefined);
    if (!isPrivate || !url) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setImage({ url, failed: false });
    void (async () => {
      const { authenticatedRequest } = await import(
        "../services/api/authenticatedRequest"
      );
      if (controller.signal.aborted) return;
      const response = await authenticatedRequest(url, {
        signal: controller.signal,
        cache: "no-store",
        redirect: isLegacy ? "manual" : "error",
      });
      if (isLegacy && response.type === "opaqueredirect") {
        if (!controller.signal.aborted)
          setImage({ url, src: url, failed: false });
        return;
      }
      if (!response.ok) throw new Error("Image unavailable");
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) throw new Error("Invalid image");
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setImage({ url, src: objectUrl, failed: false });
    })().catch(() => {
      if (!controller.signal.aborted) setImage({ url, failed: true });
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, isPrivate, isLegacy, retry]);
  const current = isPrivate
    ? image.url === url
      ? image
      : { src: undefined, failed: false }
    : {
        src: uploadPrefix && url?.startsWith(uploadPrefix) ? url : src,
        failed: false,
      };
  const activeProxy =
    proxySource?.url === url && proxySource?.retry === retry
      ? proxySource
      : undefined;
  const displaySrc = activeProxy?.src ?? current.src;
  const retryWithProxy = useCallback(
    (candidate = src) => {
      // Only our own public uploads may retry without authentication.
      if (!url || !uploadPrefix || !url.startsWith(uploadPrefix)) return false;
      if (isPrivate && current.src !== url) return false;
      const target = getFullUrl(candidate);
      if (!target?.startsWith(uploadPrefix)) return false;
      const fallback = buildProxyFallbackUrl(target);
      if (!fallback || activeProxy?.attempted.includes(fallback)) return false;
      setProxySource({
        url,
        retry,
        src: fallback,
        attempted: [...(activeProxy?.attempted ?? []), fallback],
      });
      return true;
    },
    [url, uploadPrefix, isPrivate, current.src, src, activeProxy, retry],
  );
  return { ...current, src: displaySrc, retryWithProxy };
}
