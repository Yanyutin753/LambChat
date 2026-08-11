import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { uploadApi } from "../services/api";
import { buildApiUrl } from "../services/api/config";
import type { FileCheckResult } from "../types";
import { compressImageFile } from "../utils/imageCompression";
import { uuid } from "../utils/uuid";
import type { MessageAttachment, FileCategory } from "../types";

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

function computeFileHash(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL("../workers/hashWorker.ts", import.meta.url),
      { type: "module" },
    );
    worker.onmessage = (e) => {
      worker.terminate();
      if (e.data.error) {
        reject(new Error(e.data.error));
      } else {
        resolve(e.data.hash);
      }
    };
    worker.onerror = (e) => {
      worker.terminate();
      reject(new Error(e.message));
    };
    worker.postMessage({ file });
  });
}

export function useFileUpload({
  attachments,
  onAttachmentsChange,
}: UseFileUploadOptions) {
  const { t } = useTranslation();
  const [uploadLimits, setUploadLimits] = useState<UploadLimits | null>(null);
  const limitsFetched = useRef(false);
  const abortMapRef = useRef<Map<string, () => void>>(new Map());
  const cancelledUploadIdsRef = useRef<Set<string>>(new Set());
  const isMountedRef = useRef(true);

  useEffect(() => {
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
      cancelledUploadIdsRef.current.add(id);
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

      // Compress images before upload
      const maybeCompress =
        fileCategory === "image"
          ? compressImageFile(file).catch(() => file)
          : Promise.resolve(file);

      maybeCompress.then((processedFile) => {
        if (!isMountedRef.current) {
          return;
        }
        const tempId = `temp-${uuid()}`;

        const tempAttachment: MessageAttachment = {
          id: tempId,
          key: "",
          name: processedFile.name,
          type: fileCategory,
          mimeType: processedFile.type,
          size: processedFile.size,
          url: "",
          uploadProgress: 0,
          isUploading: true,
          ...clientMeta,
        };

        onAttachmentsChange((prev) => [...prev, tempAttachment]);

        computeFileHash(processedFile)
          .then((hash) => {
            if (!isMountedRef.current) {
              throw new Error("Upload was aborted");
            }
            onAttachmentsChange((prev: MessageAttachment[]) =>
              prev.map((a) =>
                a.id === tempId ? { ...a, uploadProgress: 1 } : a,
              ),
            );
            return uploadApi
              .checkFile(
                hash,
                processedFile.size,
                processedFile.name,
                processedFile.type,
              )
              .then((check) => ({ check }));
          })
          .catch(() => ({ check: { exists: false } }))
          .then(({ check }) => {
            if (!isMountedRef.current) {
              return;
            }
            if (cancelledUploadIdsRef.current.delete(tempId)) {
              return;
            }
            if (check.exists && "key" in check) {
              abortMapRef.current.delete(tempId);
              const c = check as FileCheckResult;
              const finalAttachment: MessageAttachment = {
                id: uuid(),
                key: c.key ?? "",
                name: c.name || processedFile.name,
                type: c.type as FileCategory,
                mimeType: c.mimeType ?? processedFile.type,
                size: c.size ?? processedFile.size,
                url: buildApiUrl(c.url || `/api/upload/file/${c.key ?? ""}`),
                ...clientMeta,
              };
              onAttachmentsChange((prev: MessageAttachment[]) =>
                prev.map((a) =>
                  a.id === tempId
                    ? {
                        ...finalAttachment,
                        uploadProgress: 100,
                        isUploading: false,
                      }
                    : a,
                ),
              );
              return;
            }

            const handle = uploadApi.uploadFile(processedFile, {
              onProgress: (progress) => {
                if (!isMountedRef.current) {
                  return;
                }
                onAttachmentsChange((prev: MessageAttachment[]) =>
                  prev.map((a) =>
                    a.id === tempId
                      ? { ...a, uploadProgress: progress, isUploading: true }
                      : a,
                  ),
                );
              },
            });

            abortMapRef.current.set(tempId, handle.abort);

            return handle.promise.then((result) => {
              if (!isMountedRef.current) {
                return;
              }
              abortMapRef.current.delete(tempId);
              cancelledUploadIdsRef.current.delete(tempId);
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
              onAttachmentsChange((prev: MessageAttachment[]) =>
                prev.map((a) => (a.id === tempId ? finalAttachment : a)),
              );
            });
          })
          .catch((error) => {
            abortMapRef.current.delete(tempId);
            const wasCancelled = cancelledUploadIdsRef.current.delete(tempId);
            if (!isMountedRef.current) {
              return;
            }
            if (wasCancelled) {
              return;
            }
            if (
              error instanceof Error &&
              error.message === "Upload was aborted"
            ) {
              return;
            }
            console.error("Upload failed:", error);
            const message =
              error instanceof Error
                ? error.message
                : t("fileUpload.uploadFailed");
            toast.error(message);
            onAttachmentsChange((prev: MessageAttachment[]) =>
              clientMeta?.composerReferenceId
                ? prev.map((attachment) =>
                    attachment.id === tempId
                      ? {
                          ...attachment,
                          isUploading: false,
                          uploadError: message,
                        }
                      : attachment,
                  )
                : prev.filter((attachment) => attachment.id !== tempId),
            );
          });
      });
    },
    [onAttachmentsChange, t],
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

      if (!validateCount(fileArray.length)) return;

      for (const file of fileArray) {
        const fileCategory = category || getFileCategory(file);
        if (!validateSize(file, fileCategory)) continue;
        uploadFile(file, fileCategory, clientMeta);
      }
    },
    [validateCount, validateSize, uploadFile],
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
