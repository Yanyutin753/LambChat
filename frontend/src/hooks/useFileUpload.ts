import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { uploadApi } from "../services/api";
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
    (file: File, category?: FileCategory) => {
      const fileCategory = category || getFileCategory(file);
      const tempId = `temp-${crypto.randomUUID()}`;

      const tempAttachment: MessageAttachment = {
        id: tempId,
        key: "",
        name: file.name,
        type: fileCategory,
        mimeType: file.type,
        size: file.size,
        url: "",
        uploadProgress: 0,
        isUploading: true,
      };

      onAttachmentsChange((prev) => [...prev, tempAttachment]);

      computeFileHash(file)
        .then((hash) => {
          onAttachmentsChange((prev: MessageAttachment[]) =>
            prev.map((a) =>
              a.id === tempId ? { ...a, uploadProgress: 1 } : a,
            ),
          );
          return uploadApi
            .checkFile(hash, file.size, file.name, file.type)
            .then((check) => ({ hash, check }));
        })
        .then(({ check }) => {
          if (check.exists) {
            abortMapRef.current.delete(tempId);
            const finalAttachment: MessageAttachment = {
              id: crypto.randomUUID(),
              key: check.key ?? "",
              name: check.name || file.name,
              type: check.type as FileCategory,
              mimeType: check.mimeType ?? file.type,
              size: check.size ?? file.size,
              url: check.url || `/api/upload/file/${check.key ?? ""}`,
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

          const handle = uploadApi.uploadFile(file, {
            onProgress: (progress) => {
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
            abortMapRef.current.delete(tempId);
            const finalAttachment: MessageAttachment = {
              id: crypto.randomUUID(),
              key: result.key,
              name: result.name || file.name,
              type: result.type as FileCategory,
              mimeType: result.mimeType,
              size: result.size,
              url: result.url,
            };
            onAttachmentsChange((prev: MessageAttachment[]) =>
              prev.map((a) => (a.id === tempId ? finalAttachment : a)),
            );
          });
        })
        .catch((error) => {
          abortMapRef.current.delete(tempId);
          if (
            error instanceof Error &&
            error.message === "Upload was aborted"
          ) {
            return;
          }
          console.error("Upload failed:", error);
          toast.error(
            error instanceof Error
              ? error.message
              : t("fileUpload.uploadFailed"),
          );
          onAttachmentsChange((prev: MessageAttachment[]) =>
            prev.filter((a) => a.id !== tempId),
          );
        });
    },
    [onAttachmentsChange, t],
  );

  /** Validate and upload multiple files */
  const uploadFiles = useCallback(
    (files: FileList | File[], category?: FileCategory) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      if (!validateCount(fileArray.length)) return;

      for (const file of fileArray) {
        const fileCategory = category || getFileCategory(file);
        if (!validateSize(file, fileCategory)) continue;
        uploadFile(file, fileCategory);
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
