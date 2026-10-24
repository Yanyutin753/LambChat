import { useContext, useEffect, useState } from "react";
import { getFullUrl, isWorkspaceFilePath } from "../services/api/config";
import { getAccessToken } from "../services/api/token";
import {
  getOwnUploadFileUrl,
  needsUploadFileCapability,
  resolveUploadFileUrl,
} from "../services/api/uploadFileUrl";

import {
  WorkspaceMediaContext,
  workspaceMediaPath,
  workspaceMediaSource,
} from "./workspaceMediaContext";

export function useUploadFileUrl(source?: string, retry = 0) {
  const account = getAccessToken();
  const workspace = useContext(WorkspaceMediaContext);
  source = workspaceMediaSource(source, workspace);
  const sessionId = workspace?.sessionId;
  const cloud = workspace?.cloud;
  const machineId = workspace?.machineId;
  const selection = workspace?.selection;
  const bindingKey = `${machineId ?? ""}|${selection?.id ?? ""}|${
    selection?.machineId ?? ""
  }|${selection?.path ?? ""}`;
  const local = isWorkspaceFilePath(source);
  const [localMedia, setLocalMedia] = useState<{
    source: string;
    sessionId: string;
    cloud: boolean | undefined;
    bindingKey: string;
    account: string | null;
    src?: string;
    failed: boolean;
  }>();
  useEffect(() => {
    if (!local || !source || !sessionId) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    const identity = { source, sessionId, cloud, account, bindingKey };
    void (async () => {
      const path = workspaceMediaPath(source, {
        sessionId,
        cloud: !!cloud,
        machineId,
        selection,
      });
      const { sandboxFsApi, sandboxCloudFsApi } = await import(
        "../services/api/sandboxFs"
      );
      if (controller.signal.aborted) return;
      const read = cloud ? sandboxCloudFsApi.read : sandboxFsApi.read;
      const result = await read(sessionId, path, 0, 500, controller.signal);
      if (controller.signal.aborted) return;
      if (result.error) throw new Error(result.error);
      let blob = result.blob;
      if (!blob && result.encoding === "base64" && result.content) {
        blob = new Blob([
          Uint8Array.from(atob(result.content), (c) => c.charCodeAt(0)),
        ]);
      }
      if (!blob) throw new Error("Missing media content");
      if (/\.svg$/i.test(path))
        blob = new Blob([blob], { type: "image/svg+xml" });
      objectUrl = URL.createObjectURL(blob);
      setLocalMedia({ ...identity, src: objectUrl, failed: false });
    })().catch(() => {
      if (!controller.signal.aborted)
        setLocalMedia({ ...identity, failed: true });
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    source,
    local,
    sessionId,
    cloud,
    account,
    retry,
    bindingKey,
    machineId,
    selection,
  ]);
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
  if (local) {
    if (!sessionId) return { src: undefined, failed: true };
    return localMedia &&
      localMedia.source === source &&
      localMedia.sessionId === sessionId &&
      localMedia.account === account &&
      localMedia.cloud === cloud &&
      localMedia.bindingKey === bindingKey
      ? { src: localMedia.src, failed: localMedia.failed }
      : { src: undefined, failed: false };
  }
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
