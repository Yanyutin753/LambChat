import { useEffect, useState } from "react";
import { getFullUrl } from "../services/api/config";
import { getAccessToken } from "../services/api/token";
import {
  getOwnUploadFileUrl,
  needsUploadFileCapability,
  resolveUploadFileUrl,
} from "../services/api/uploadFileUrl";

export function useUploadFileUrl(source?: string, retry = 0) {
  const account = getAccessToken();
  const needsCapability = needsUploadFileCapability(source);
  const [resolved, setResolved] = useState<{
    source: string;
    account: string | null;
    url?: string;
    failed: boolean;
  }>();
  useEffect(() => {
    if (!source || !needsCapability) return;
    let cancelled = false;
    setResolved(undefined);
    void resolveUploadFileUrl(source).then(
      (url) => {
        if (!cancelled) setResolved({ source, account, url, failed: false });
      },
      () => {
        if (!cancelled) setResolved({ source, account, failed: true });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [source, account, needsCapability, retry]);
  if (!needsCapability) {
    return {
      src:
        source?.startsWith("//") || !getOwnUploadFileUrl(source)
          ? source
          : getFullUrl(source),
      failed: false,
    };
  }
  return resolved && resolved.source === source && resolved.account === account
    ? { src: resolved.url, failed: resolved.failed }
    : { src: undefined, failed: false };
}
