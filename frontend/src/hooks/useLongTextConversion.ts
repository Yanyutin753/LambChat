import { useCallback, useRef, useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  buildLongTextClientMeta,
  buildLongTextFileName,
  canRestoreLongTextAttachment,
  createLongTextFile,
  prepareLongTextSubmit,
  restoreInputFromLongTextAttachment,
  shouldConvertLongText,
  shouldSkipLongTextConversion,
} from "../components/chat/longTextConversion";
import type { FileCategory, MessageAttachment } from "../types";
import { uploadApi } from "../services/api";

export interface UseLongTextConversionOptions {
  setInput: (value: string) => void;
  setAttachments: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
  uploadFiles: (
    files: FileList | File[],
    category?: FileCategory,
    clientMeta?: Pick<MessageAttachment, "fromLongText" | "localOriginalText">,
  ) => void;
  validateCount: (count: number) => boolean;
  scheduleTextareaResize?: () => void;
  expanded: boolean;
}

export function useLongTextConversion({
  setInput,
  setAttachments,
  uploadFiles,
  validateCount,
  scheduleTextareaResize,
  expanded,
}: UseLongTextConversionOptions) {
  const { t } = useTranslation();
  const [allowOversizedText, setAllowOversizedText] = useState(false);
  const convertingRef = useRef(false);

  const showConvertedToast = useCallback(() => {
    toast.success(t("chat.textAutoUploaded", "长文本已自动转为文件上传"));
  }, [t]);

  const convertTextToAttachment = useCallback(
    (text: string) => {
      if (!shouldConvertLongText(text)) return false;
      if (!validateCount(1)) return false;
      if (convertingRef.current) return false;
      convertingRef.current = true;

      const file = createLongTextFile(text, buildLongTextFileName());
      uploadFiles([file], "document", buildLongTextClientMeta(text));
      setAllowOversizedText(false);
      // The complete composer value now lives on the attachment card.
      setInput("");
      scheduleTextareaResize?.();
      showConvertedToast();

      queueMicrotask(() => {
        convertingRef.current = false;
      });
      return true;
    },
    [
      uploadFiles,
      validateCount,
      setInput,
      scheduleTextareaResize,
      showConvertedToast,
    ],
  );

  const maybeConvertInput = useCallback(
    (nextInput: string) => {
      if (
        shouldSkipLongTextConversion({
          text: nextInput,
          allowOversizedText,
          expanded,
        })
      ) {
        return false;
      }
      return convertTextToAttachment(nextInput);
    },
    [allowOversizedText, expanded, convertTextToAttachment],
  );

  const restoreLongTextAttachment = useCallback(
    (attachment: MessageAttachment) => {
      if (!canRestoreLongTextAttachment(attachment)) return false;
      const original = restoreInputFromLongTextAttachment(attachment);
      setAttachments((prev) =>
        prev.filter((item) => item.id !== attachment.id),
      );
      if (attachment.key && !attachment.isUploading) {
        uploadApi.deleteFile(attachment.key).catch((error) => {
          console.error("Failed to delete long text file from server:", error);
        });
      }
      setAllowOversizedText(true);
      setInput(original);
      scheduleTextareaResize?.();
      return true;
    },
    [setAttachments, setInput, scheduleTextareaResize],
  );

  const prepareSubmit = useCallback(
    (message: string, submitAttachments: MessageAttachment[]) =>
      prepareLongTextSubmit({
        message,
        attachments: submitAttachments,
      }),
    [],
  );

  return {
    allowOversizedText,
    setAllowOversizedText,
    convertTextToAttachment,
    maybeConvertInput,
    restoreLongTextAttachment,
    prepareSubmit,
  };
}
