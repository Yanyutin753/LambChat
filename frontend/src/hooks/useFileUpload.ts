import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { uploadApi } from "../services/api";
import { buildApiUrl } from "../services/api/config";
import {
  getFileExtension,
  isImageFile,
} from "../components/documents/utils/fileTypeChecks";
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
  if (type.startsWith("image/") || isImageFile(getFileExtension(file.name)))
    return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
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
      const interruptedIds = new Set(abortMap.keys());
      for (const abort of abortMap.values()) {
        abort();
      }
      abortMap.clear();
      if (interruptedIds.size) {
        onAttachmentsChange((current) =>
          current.map((attachment) =>
            interruptedIds.has(attachment.id) && attachment.isUploading
              ? {
                  ...attachment,
                  isUploading: false,
                  uploadError: "interrupted",
                }
              : attachment,
          ),
        );
      }
    };
  }, [onAttachmentsChange]);

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
    (
      file: File,
      category?: FileCategory,
      clientMeta?: UploadClientMeta,
      replaceId?: string,
      signal?: AbortSignal,
    ) => {
      const fileCategory = category || getFileCategory(file);
      if (!validateInputSize(file, fileCategory)) {
        if (replaceId)
          onAttachmentsChange((previous) =>
            previous.map((item) =>
              item.id === replaceId
                ? {
                    ...item,
                    isUploading: false,
                    uploadError: t("fileUpload.fileTooLarge"),
                  }
                : item,
            ),
          );
        return;
      }

      const replacedSource = replaceId
        ? attachments.find((item) => item.id === replaceId)
        : undefined;
      const tempId = replaceId || `temp-${uuid()}`;
      const controller = new AbortController();
      let xhrAbort: (() => void) | undefined;
      let disposeProgress: (() => void) | undefined;
      const cancelTask = () => {
        controller.abort();
        xhrAbort?.();
        disposeProgress?.();
      };
      abortMapRef.current.set(tempId, cancelTask);
      signal?.addEventListener("abort", cancelTask, { once: true });
      if (signal?.aborted) cancelTask();

      const preparing: MessageAttachment = {
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
        ...(replacedSource?.localFile
          ? { localFile: replacedSource.localFile }
          : {}),
        ...clientMeta,
      };
      onAttachmentsChange((prev) =>
        replaceId
          ? prev.map((item) => (item.id === replaceId ? preparing : item))
          : [...prev, preparing],
      );

      const task = (async () => {
        try {
          if (controller.signal.aborted)
            throw new DOMException("Aborted", "AbortError");
          const progressController = createUploadProgressController(
            ({ progress, stage, processingProgress }) => {
              if (!isMountedRef.current || controller.signal.aborted) return;
              onAttachmentsChange((prev) =>
                prev.map((attachment) =>
                  attachment.id === tempId
                    ? {
                        ...attachment,
                        uploadProgress: progress,
                        uploadStage: stage,
                        uploadProcessingProgress: processingProgress,
                        isUploading: true,
                      }
                    : attachment,
                ),
              );
            },
            250,
          );
          disposeProgress = progressController.dispose;
          const handle = uploadApi.uploadFile(file, {
            onProgress: progressController.report,
            onProcessingProgress: progressController.reportProcessing,
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
            name: result.name || file.name,
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
            replacedSource
              ? prev.map((item) =>
                  item.id === tempId
                    ? {
                        ...replacedSource,
                        isUploading: false,
                        uploadStage: undefined,
                        uploadError: message,
                      }
                    : item,
                )
              : clientMeta?.composerReferenceId
                ? prev.map((attachment) =>
                    attachment.id === tempId
                      ? {
                          ...attachment,
                          isUploading: false,
                          uploadProgress: undefined,
                          uploadStage: undefined,
                          uploadProcessingProgress: undefined,
                          uploadError: message,
                        }
                      : attachment,
                  )
                : prev.filter((attachment) => attachment.id !== tempId),
          );
        } finally {
          disposeProgress?.();
          signal?.removeEventListener("abort", cancelTask);
          if (abortMapRef.current.get(tempId) === cancelTask)
            abortMapRef.current.delete(tempId);
        }
      })();
      return replaceId ? task : undefined;
    },
    [attachments, onAttachmentsChange, t, validateInputSize],
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
