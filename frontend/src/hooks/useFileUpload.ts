import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { uploadApi } from "../services/api";
import { buildApiUrl } from "../services/api/config";
import type { FileCheckResult } from "../types";
import { compressImageFile } from "../utils/imageCompression";
import { uuid } from "../utils/uuid";
import type { MessageAttachment, FileCategory } from "../types";
import { createUploadProgressController } from "./uploadProgress";

const MEBIBYTE = 1024 * 1024;
const MAX_IMAGE_PREPARATION_BYTES = 50 * MEBIBYTE;

export interface UploadLimits {
  image: number;
  video: number;
  audio: number;
  document: number;
  maxFiles: number;
}

export interface UseFileUploadOptions {
  attachments: MessageAttachment[];
  onAttachmentsChange: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
}

export type UploadClientMeta = Pick<
  MessageAttachment,
  "fromLongText" | "localOriginalText" | "composerReferenceId"
>;

function getFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

function computeFileHash(file: File, signal?: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new Worker(
        new URL("../workers/hashWorker.ts", import.meta.url),
        { type: "module" },
      );
    } catch (error) {
      reject(error);
      return;
    }
    const cleanup = () => {
      signal?.removeEventListener("abort", handleAbort);
      worker.terminate();
    };
    const handleAbort = () => {
      cleanup();
      reject(new DOMException("Upload was aborted", "AbortError"));
    };
    worker.onmessage = (e) => {
      cleanup();
      if (e.data.error) {
        reject(new Error(e.data.error));
      } else {
        resolve(e.data.hash);
      }
    };
    worker.onerror = (e) => {
      cleanup();
      reject(new Error(e.message));
    };
    signal?.addEventListener("abort", handleAbort, { once: true });
    worker.postMessage({ file });
  });
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.message === "Upload was aborted")
  );
}

export function useFileUpload({
  attachments,
  onAttachmentsChange,
}: UseFileUploadOptions) {
  const { t } = useTranslation();
  const [uploadLimits, setUploadLimits] = useState<UploadLimits | null>(null);
  const limitsFetched = useRef(false);
  const abortMapRef = useRef<Map<string, () => void>>(new Map());
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    const abortMap = abortMapRef.current;
    return () => {
      isMountedRef.current = false;
      for (const abort of abortMap.values()) {
        abort();
      }
      abortMap.clear();
    };
  }, []);

  // Fetch upload limits once
  useEffect(() => {
    if (limitsFetched.current) {
      return;
    }

    limitsFetched.current = true;
    let isMounted = true;

    uploadApi
      .getConfig()
      .then((config) => {
        if (isMounted && config.uploadLimits) {
          setUploadLimits(config.uploadLimits);
        }
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  /** Validate file size, returns true if ok */
  const validateSize = useCallback(
    (file: File, category: FileCategory): boolean => {
      if (file.size <= 0) {
        toast.error(t("fileUpload.emptyFile"));
        return false;
      }
      if (!uploadLimits) return true;
      const maxMB = uploadLimits[category];
      if (file.size > maxMB * 1024 * 1024) {
        toast.error(`${t("fileUpload.fileTooLarge")} (${maxMB}MB)`);
        return false;
      }
      return true;
    },
    [uploadLimits, t],
  );

  const validateInputSize = useCallback(
    (file: File, category: FileCategory): boolean => {
      if (file.size <= 0) {
        toast.error(t("fileUpload.emptyFile"));
        return false;
      }
      if (!uploadLimits) return true;
      const maxBytes = uploadLimits[category] * MEBIBYTE;
      if (file.size <= maxBytes) return true;
      const preparationCeiling = Math.max(
        maxBytes,
        Math.min(maxBytes * 2, MAX_IMAGE_PREPARATION_BYTES),
      );
      if (category === "image" && file.size <= preparationCeiling) return true;
      toast.error(
        `${t("fileUpload.fileTooLarge")} (${uploadLimits[category]}MB)`,
      );
      return false;
    },
    [uploadLimits, t],
  );

  /** Validate file count (existing + new), returns true if ok */
  const validateCount = useCallback(
    (newFileCount: number): boolean => {
      if (!uploadLimits) return true;
      const remaining = uploadLimits.maxFiles - attachments.length;
      if (remaining <= 0 || newFileCount > remaining) {
        toast.error(
          t("fileUpload.tooManyFiles", { count: uploadLimits.maxFiles }),
        );
        return false;
      }
      return true;
    },
    [uploadLimits, attachments.length, t],
  );

  /** Cancel an in-progress upload by attachment id */
  const cancelUpload = useCallback(
    (id: string) => {
      const abort = abortMapRef.current.get(id);
      if (abort) {
        abort();
        abortMapRef.current.delete(id);
      }
      onAttachmentsChange((prev) => prev.filter((a) => a.id !== id));
    },
    [onAttachmentsChange],
  );

  /** Upload a single file with progress tracking */
  const uploadFile = useCallback(
    (file: File, category?: FileCategory, clientMeta?: UploadClientMeta) => {
      const fileCategory = category || getFileCategory(file);
      if (!validateInputSize(file, fileCategory)) return;

      const tempId = `temp-${uuid()}`;
      const controller = new AbortController();
      let xhrAbort: (() => void) | undefined;
      let disposeProgress: (() => void) | undefined;
      const cancelTask = () => {
        controller.abort();
        xhrAbort?.();
        disposeProgress?.();
      };
      abortMapRef.current.set(tempId, cancelTask);

      onAttachmentsChange((prev) => [
        ...prev,
        {
          id: tempId,
          key: "",
          name: file.name,
          type: fileCategory,
          mimeType: file.type,
          size: file.size,
          url: "",
          uploadProgress: 0,
          uploadStage: "preparing",
          isUploading: true,
          ...clientMeta,
        },
      ]);

      void (async () => {
        try {
          const maxBytes = uploadLimits
            ? uploadLimits[fileCategory] * MEBIBYTE
            : null;
          const processedFile =
            fileCategory === "image"
              ? await compressImageFile(file, {
                  signal: controller.signal,
                  fallback:
                    maxBytes !== null && file.size > maxBytes
                      ? "main-thread"
                      : "original",
                })
              : file;
          if (controller.signal.aborted)
            throw new DOMException("Aborted", "AbortError");
          if (!validateSize(processedFile, fileCategory)) {
            onAttachmentsChange((prev) => prev.filter((a) => a.id !== tempId));
            return;
          }

          onAttachmentsChange((prev) =>
            prev.map((attachment) =>
              attachment.id === tempId
                ? {
                    ...attachment,
                    name: processedFile.name,
                    mimeType: processedFile.type,
                    size: processedFile.size,
                  }
                : attachment,
            ),
          );

          let check: FileCheckResult = { exists: false };
          try {
            const hash = await computeFileHash(
              processedFile,
              controller.signal,
            );
            if (controller.signal.aborted)
              throw new DOMException("Aborted", "AbortError");
            check = await uploadApi.checkFile(
              hash,
              processedFile.size,
              processedFile.name,
              processedFile.type,
            );
          } catch (error) {
            if (isAbortError(error)) throw error;
          }

          if (check.exists && check.key) {
            const finalAttachment: MessageAttachment = {
              id: uuid(),
              key: check.key,
              name: check.name || processedFile.name,
              type: (check.type as FileCategory) || fileCategory,
              mimeType: check.mimeType ?? processedFile.type,
              size: check.size ?? processedFile.size,
              url: buildApiUrl(check.url || `/api/upload/file/${check.key}`),
              ...clientMeta,
            };
            onAttachmentsChange((prev) =>
              prev.map((attachment) =>
                attachment.id === tempId ? finalAttachment : attachment,
              ),
            );
            return;
          }

          const progressController = createUploadProgressController(
            ({ progress, stage }) => {
              if (!isMountedRef.current || controller.signal.aborted) return;
              onAttachmentsChange((prev) =>
                prev.map((attachment) =>
                  attachment.id === tempId
                    ? {
                        ...attachment,
                        uploadProgress: progress,
                        uploadStage: stage,
                        isUploading: true,
                      }
                    : attachment,
                ),
              );
            },
          );
          disposeProgress = progressController.dispose;
          const handle = uploadApi.uploadFile(processedFile, {
            onProgress: progressController.report,
          });
          xhrAbort = handle.abort;
          if (controller.signal.aborted) {
            handle.abort();
            throw new DOMException("Aborted", "AbortError");
          }
          const result = await handle.promise;
          progressController.dispose();

          if (!isMountedRef.current || controller.signal.aborted) return;
          const finalAttachment: MessageAttachment = {
            id: uuid(),
            key: result.key,
            name: result.name || processedFile.name,
            type: result.type as FileCategory,
            mimeType: result.mimeType,
            size: result.size,
            url: buildApiUrl(result.url),
            ...clientMeta,
          };
          onAttachmentsChange((prev) =>
            prev.map((attachment) =>
              attachment.id === tempId ? finalAttachment : attachment,
            ),
          );
        } catch (error) {
          if (!isMountedRef.current || isAbortError(error)) return;
          console.error("Upload failed:", error);
          const message =
            error instanceof Error
              ? error.message
              : t("fileUpload.uploadFailed");
          toast.error(message);
          onAttachmentsChange((prev) =>
            clientMeta?.composerReferenceId
              ? prev.map((attachment) =>
                  attachment.id === tempId
                    ? {
                        ...attachment,
                        isUploading: false,
                        uploadProgress: undefined,
                        uploadStage: undefined,
                        uploadError: message,
                      }
                    : attachment,
                )
              : prev.filter((attachment) => attachment.id !== tempId),
          );
        } finally {
          disposeProgress?.();
          abortMapRef.current.delete(tempId);
        }
      })();
    },
    [onAttachmentsChange, t, uploadLimits, validateInputSize, validateSize],
  );

  /** Validate and upload multiple files */
  const uploadFiles = useCallback(
    (
      files: FileList | File[],
      category?: FileCategory,
      clientMeta?: UploadClientMeta,
    ) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const validFiles = fileArray.filter((file) => {
        const fileCategory = category || getFileCategory(file);
        return validateInputSize(file, fileCategory);
      });
      if (validFiles.length === 0 || !validateCount(validFiles.length)) return;

      for (const file of validFiles) {
        const fileCategory = category || getFileCategory(file);
        uploadFile(file, fileCategory, clientMeta);
      }
    },
    [validateCount, validateInputSize, uploadFile],
  );

  return {
    uploadLimits,
    uploadFiles,
    uploadFile,
    validateSize,
    validateCount,
    cancelUpload,
  };
}

export { getFileCategory };
