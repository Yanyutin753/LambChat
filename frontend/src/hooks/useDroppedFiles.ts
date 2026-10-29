import { useEffect, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import {
  classifyClipboardFiles,
  decodeEmbeddedClipboardImage,
} from "../components/chat/clipboardFiles";
import { getAccessToken } from "../services/api/token";
import { isCurrentFileAccount } from "../services/api/uploadFileUrl";
import { getFullUrl } from "../services/api/config";
import {
  resolveDroppedDesktopFiles,
  type DesktopFile,
} from "../services/tauri/desktopFiles";
import { isShellAvailable } from "../services/tauri/sandboxShell";

interface Options {
  disabled?: boolean;
  accountId?: string;
  draftKey?: string;
  mode: unknown;
  machineId: string | null;
  validateCount: (count: number) => boolean;
  uploadFiles: (files: File[] | FileList) => void;
  receiveFiles?: (files: DesktopFile[]) => void;
}

export function useDroppedFiles(options: Options) {
  const { t } = useTranslation();
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const latest = useRef(options);
  latest.current = options;
  const scope = [
    options.accountId,
    options.draftKey,
    options.mode,
    options.machineId,
  ].join("\0");
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const active = useRef(new Set<AbortController>());
  useEffect(() => {
    const tasks = active.current;
    return () => {
      tasks.forEach((task) => task.abort());
      tasks.clear();
    };
  }, [scope]);

  const handleDrop = async (event: DragEvent) => {
    event.preventDefault();
    setIsDraggingOver(false);
    if (options.disabled || !event.dataTransfer) return;
    const controller = new AbortController();
    active.current.add(controller);
    const account = getAccessToken();
    const server = getFullUrl("/");
    const initialScope = currentScope.current;
    const valid = () =>
      !controller.signal.aborted &&
      !latest.current.disabled &&
      currentScope.current === initialScope &&
      isCurrentFileAccount(account) &&
      getFullUrl("/") === server;
    try {
      const data = event.dataTransfer;
      const files = Array.from(data.files);
      if (!files.length)
        for (const item of Array.from(data.items ?? [])) {
          if (item.kind === "file") {
            const file = item.getAsFile();
            if (file) files.push(file);
          }
        }
      const result = classifyClipboardFiles({
        files,
        getData: (type) => data.getData(type),
      });
      if (result.kind === "none") {
        if (
          Array.from(data.types ?? []).some(
            (type) => type === "Files" || type === "text/uri-list",
          ) ||
          Array.from(data.items ?? []).some((item) => item.kind === "file")
        )
          throw new Error("unreadable_drop");
        return;
      }
      if (result.kind === "invalid-image") throw new Error("unreadable_drop");
      const readable =
        result.kind === "files"
          ? result.files
          : [
              await decodeEmbeddedClipboardImage(
                result.source,
                result.mimeType,
                controller.signal,
              ),
            ];
      if (!valid() || !latest.current.validateCount(readable.length)) return;
      if (isShellAvailable() && options.mode === "pending")
        throw new Error("environment_pending");
      const references =
        isShellAvailable() && options.mode === "local"
          ? await resolveDroppedDesktopFiles(readable, controller.signal)
          : null;
      if (!valid()) return;
      // Re-check after the native reply, since another selection may have filled the draft.
      if (!latest.current.validateCount(readable.length)) return;
      const originals =
        references?.filter((file): file is DesktopFile => !!file) ?? [];
      const blobs = readable.filter((_, index) => !references?.[index]);
      if (originals.length) latest.current.receiveFiles?.(originals);
      if (blobs.length) latest.current.uploadFiles(blobs);
    } catch {
      if (valid()) toast.error(t("fileUpload.dropUnavailable"));
    } finally {
      active.current.delete(controller);
    }
  };
  return {
    isDraggingOver,
    handleDragOver: (event: DragEvent) => {
      event.preventDefault();
      if (!options.disabled) setIsDraggingOver(true);
    },
    handleDragLeave: (event: DragEvent) => {
      event.preventDefault();
      if (
        event.relatedTarget instanceof Node &&
        event.currentTarget.contains(event.relatedTarget)
      )
        return;
      setIsDraggingOver(false);
    },
    handleDrop,
  };
}
