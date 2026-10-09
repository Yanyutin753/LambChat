import { useEffect, useState } from "react";
import { getFullUrl } from "../services/api/config";

/** Private captures use short-lived local blobs; credentials never go to image hosts. */
export function usePrivateImage(src?: string, retry = 0) {
  const url = getFullUrl(src);
  const prefix = getFullUrl("/api/upload/file/cua_screenshots/");
  const legacyPrefix = getFullUrl("/api/upload/file/tool_binaries/");
  const isLegacy = !!url && !!legacyPrefix && url.startsWith(legacyPrefix);
  const isPrivate = isLegacy || (!!url && !!prefix && url.startsWith(prefix));
  const [image, setImage] = useState<{
    url?: string;
    src?: string;
    failed: boolean;
  }>({ failed: false });
  useEffect(() => {
    if (!isPrivate || !url) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setImage({ url, failed: false });
    void (async () => {
      const { authenticatedRequest } =
        await import("../services/api/authenticatedRequest");
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
  if (!isPrivate) return { src, failed: false };
  return image.url === url ? image : { src: undefined, failed: false };
}
