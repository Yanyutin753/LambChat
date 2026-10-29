import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import type { FileCategory, MessageAttachment } from "../types";
import { isShellAvailable } from "../services/tauri/sandboxShell";
import {
  canUseLocalAttachment,
  desktopFileAttachment,
  pickDesktopFiles,
  readDesktopFile,
  type DesktopFile,
} from "../services/tauri/desktopFiles";
import { uploadApi } from "../services/api/upload";
import { getAccessToken } from "../services/api/token";
import { isCurrentFileAccount } from "../services/api/uploadFileUrl";
import { getFullUrl } from "../services/api/config";
import type { UploadClientMeta } from "./useFileUpload";

export interface DesktopAttachmentOptions {
  attachments: MessageAttachment[];
  onAttachmentsChange: (
    value:
      | MessageAttachment[]
      | ((previous: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
  mode: unknown;
  machineId: string | null;
  currentMachineId: string | null;
  accountId?: string;
  draftKey?: string;
  disabled?: boolean;
  onLocalMachine?: (machineId: string) => void;
  dropTarget?: { current: HTMLElement | null };
  allowedCategories: FileCategory[];
  validateCount: (count: number) => boolean;
  uploadFile: (
    file: File,
    category?: FileCategory,
    meta?: UploadClientMeta,
    replaceId?: string,
    signal?: AbortSignal,
  ) => void | Promise<void>;
  uploadLimits: {
    image: number;
    video: number;
    audio: number;
    document: number;
    maxFiles: number;
  } | null;
}

/** Native selection is metadata-only; only incompatible drafts read bytes for upload. */
export function useDesktopAttachments(options: DesktopAttachmentOptions) {
  const { t } = useTranslation();
  const native = isShellAvailable();
  const latest = useRef(options);
  latest.current = options;
  const active = useRef(new Map<string, AbortController>());
  const drops = useRef(
    new Map<
      string,
      { scope: string; account: string | null; server: string | undefined }
    >(),
  );
  const mounted = useRef(true);
  const scope = [
    options.accountId,
    options.draftKey,
    options.mode,
    options.machineId,
  ].join("\0");
  const currentScope = useRef(scope);
  currentScope.current = scope;
  useEffect(() => {
    mounted.current = true;
    const tasks = active.current;
    return () => {
      mounted.current = false;
      tasks.forEach((controller) => controller.abort());
      tasks.clear();
    };
  }, []);
  useEffect(() => {
    const tasks = active.current;
    const update = options.onAttachmentsChange;
    return () => {
      const ids = new Set(tasks.keys());
      tasks.forEach((controller) => controller.abort());
      tasks.clear();
      if (ids.size)
        update((previous) =>
          previous.map((item) =>
            ids.has(item.id) && item.localFile
              ? {
                  ...item,
                  isUploading: false,
                  uploadStage: undefined,
                  uploadError: undefined,
                }
              : item,
          ),
        );
    };
  }, [scope, options.onAttachmentsChange]);

  const receive = useCallback(
    (files: DesktopFile[]) => {
      const now = latest.current;
      if (
        now.disabled ||
        files.length === 0 ||
        !now.validateCount(files.length)
      )
        return;
      if (
        (now.mode !== "local" && now.mode !== "cloud") ||
        (now.mode === "local" && (!now.machineId || !now.currentMachineId))
      ) {
        toast.error(t("fileUpload.localFileUnavailable"));
        return;
      }
      const items = files.map((file) =>
        desktopFileAttachment(file, now.currentMachineId || ""),
      );
      if (
        items.some(
          (item) =>
            item.size <= 0 || !now.allowedCategories.includes(item.type),
        )
      ) {
        toast.error(t("fileUpload.localFileUnavailable"));
        return;
      }
      if (
        now.mode === "local" &&
        now.machineId === now.currentMachineId &&
        now.machineId
      )
        now.onLocalMachine?.(now.machineId);
      now.onAttachmentsChange((previous) => [...previous, ...items]);
    },
    [t],
  );
  const pickFiles = useCallback(async () => {
    const initial = currentScope.current;
    const account = getAccessToken();
    const server = getFullUrl("/");
    try {
      const files = await pickDesktopFiles(t("fileUpload.selectFiles"));
      if (
        mounted.current &&
        currentScope.current === initial &&
        isCurrentFileAccount(account) &&
        getFullUrl("/") === server
      )
        receive(files);
    } catch {
      if (mounted.current && currentScope.current === initial)
        toast.error(t("fileUpload.localFileUnavailable"));
    }
  }, [receive, t]);
  useEffect(() => {
    if (!native) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    void import("@tauri-apps/api/event")
      .then(({ listen }) =>
        listen<{
          batchId: string;
          pending?: boolean;
          files: DesktopFile[];
          error?: string;
          position: { x: number; y: number };
        }>("desktop-files-dropped", (event) => {
          if (disposed) return;
          const element = latest.current.dropTarget?.current;
          if (!element) return;
          const rect = element.getBoundingClientRect();
          const x = event.payload.position.x / window.devicePixelRatio;
          const y = event.payload.position.y / window.devicePixelRatio;
          if (
            x < rect.left ||
            x > rect.right ||
            y < rect.top ||
            y > rect.bottom
          )
            return;
          if (event.payload.pending) {
            drops.current.clear();
            drops.current.set(event.payload.batchId, {
              scope: currentScope.current,
              account: getAccessToken(),
              server: getFullUrl("/"),
            });
            return;
          }
          const started = drops.current.get(event.payload.batchId);
          drops.current.delete(event.payload.batchId);
          if (
            !started ||
            started.scope !== currentScope.current ||
            !isCurrentFileAccount(started.account) ||
            started.server !== getFullUrl("/")
          )
            return;
          if (event.payload.error)
            toast.error(t("fileUpload.localFileUnavailable"));
          else receive(event.payload.files);
        }),
      )
      .then((stop) => {
        if (disposed) stop();
        else unlisten = stop;
      })
      .catch(() => {});
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [native, receive, t]);

  useEffect(() => {
    const ids = new Set(options.attachments.map((item) => item.id));
    active.current.forEach((controller, id) => {
      if (!ids.has(id)) controller.abort();
    });
    if (
      !native ||
      (options.mode !== "cloud" &&
        (options.mode !== "local" ||
          !options.machineId ||
          !options.currentMachineId))
    )
      return;
    for (const attachment of options.attachments) {
      if (!attachment.localFile || active.current.has(attachment.id)) continue;
      if (canUseLocalAttachment(attachment, options.mode, options.machineId)) {
        if (attachment.isUploading || attachment.uploadError)
          options.onAttachmentsChange((previous) =>
            previous.map((item) =>
              item.id === attachment.id
                ? { ...item, isUploading: false, uploadError: undefined }
                : item,
            ),
          );
        continue;
      }
      if (attachment.uploadError) continue;
      const controller = new AbortController();
      active.current.set(attachment.id, controller);
      const initial = currentScope.current;
      const account = getAccessToken();
      const server = getFullUrl("/");
      const valid = () =>
        mounted.current &&
        !controller.signal.aborted &&
        currentScope.current === initial &&
        isCurrentFileAccount(account) &&
        getFullUrl("/") === server &&
        latest.current.attachments.some((item) => item.id === attachment.id);
      options.onAttachmentsChange((previous) =>
        previous.map((item) =>
          item.id === attachment.id
            ? { ...item, isUploading: true, uploadStage: "preparing" }
            : item,
        ),
      );
      void (async () => {
        try {
          const limits =
            options.uploadLimits || (await uploadApi.getConfig()).uploadLimits;
          if (!valid()) return;
          const bytes = limits[attachment.type] * 1024 * 1024;
          const max =
            attachment.type === "image"
              ? Math.max(bytes, Math.min(bytes * 2, 50 * 1024 * 1024))
              : bytes;
          const file = await readDesktopFile(
            attachment.localFile!.token,
            max,
            controller.signal,
          );
          if (!valid()) return;
          await latest.current.uploadFile(
            file,
            attachment.type,
            undefined,
            attachment.id,
            controller.signal,
          );
        } catch (error) {
          if (!valid()) return;
          const message = t(
            error instanceof Error && error.message === "file_size_limit"
              ? "fileUpload.fileTooLarge"
              : "fileUpload.localFileUnavailable",
          );
          options.onAttachmentsChange((previous) =>
            previous.map((item) =>
              item.id === attachment.id
                ? {
                    ...item,
                    isUploading: false,
                    uploadStage: undefined,
                    uploadError: message,
                  }
                : item,
            ),
          );
          toast.error(message);
        } finally {
          if (active.current.get(attachment.id) === controller)
            active.current.delete(attachment.id);
        }
      })();
    }
  }, [native, options, t]);
  return {
    pickFiles: native ? pickFiles : undefined,
    blocked: options.attachments.some(
      (item) =>
        item.localFile &&
        (!native ||
          !canUseLocalAttachment(item, options.mode, options.machineId)),
    ),
  };
}
