import { useCallback, useEffect, useState } from "react";
import { getFullUrl } from "../services/api/config";
import { useUploadFileUrl } from "./useUploadFileUrl";
import {
  getOwnUploadFileUrl,
  resolveUploadFileUrl,
} from "../services/api/uploadFileUrl";
import { buildProxyFallbackUrl } from "../components/documents/documentFetchCache";

/** Capability images load directly; proxy candidates retry once and captures stay authenticated. */
export function usePrivateImage(src?: string, retry = 0) {
  const url = getFullUrl(src);
  const uploadPrefix = getFullUrl("/api/upload/file/");
  const prefix = getFullUrl("/api/upload/file/cua_screenshots/");
  const legacyPrefix = getFullUrl("/api/upload/file/tool_binaries/");
  const isLegacy =
    !!url &&
    !!legacyPrefix &&
    url.startsWith(legacyPrefix) &&
    !getOwnUploadFileUrl(url)?.searchParams.has("file_token");
  const resolved = useUploadFileUrl(isLegacy ? undefined : src, retry);
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
        const capability = await resolveUploadFileUrl(url);
        if (!controller.signal.aborted)
          setImage({ url, src: capability, failed: false });
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
    : resolved;
  const activeProxy =
    proxySource?.url === url && proxySource?.retry === retry
      ? proxySource
      : undefined;
  const displaySrc = activeProxy?.src ?? current.src;
  const retryWithProxy = useCallback(
    (candidate = src) => {
      // Only our own upload paths can reuse the current file capability for proxy retry.
      if (!url || !uploadPrefix || !url.startsWith(uploadPrefix)) return false;
      const target = getOwnUploadFileUrl(candidate);
      if (!target || !current.src) return false;
      const currentUrl = getOwnUploadFileUrl(current.src);
      if (currentUrl?.pathname !== target.pathname) return false;
      const token = currentUrl.searchParams.get("file_token");
      if (token) target.searchParams.set("file_token", token);
      const fallback = buildProxyFallbackUrl(target.toString());
      if (!fallback || activeProxy?.attempted.includes(fallback)) return false;
      setProxySource({
        url,
        retry,
        src: fallback,
        attempted: [...(activeProxy?.attempted ?? []), fallback],
      });
      return true;
    },
    [url, uploadPrefix, current.src, src, activeProxy, retry],
  );
  return { ...current, src: displaySrc, retryWithProxy };
}
