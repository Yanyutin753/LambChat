import { useEffect, useRef, useState } from "react";
import { useFileUpload } from "../../../hooks/useFileUpload";
import type { MessageAttachment } from "../../../types";

export function useDragAndDrop() {
  const [isPageDragging, setIsPageDragging] = useState(false);
  const [pageDragAttachments, setPageDragAttachments] = useState<
    MessageAttachment[]
  >([]);

  const { uploadFiles, validateCount } = useFileUpload({
    attachments: pageDragAttachments,
    onAttachmentsChange: setPageDragAttachments,
  });

  const dragCounterRef = useRef(0);

  useEffect(() => {
    const handleDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) {
        e.preventDefault();
        dragCounterRef.current++;
        if (dragCounterRef.current === 1) {
          setIsPageDragging(true);
        }
      }
    };

    const handleDragLeave = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) {
        dragCounterRef.current--;
        if (dragCounterRef.current <= 0) {
          dragCounterRef.current = 0;
          setIsPageDragging(false);
        }
      }
    };

    const handleDrop = (e: DragEvent) => {
      dragCounterRef.current = 0;
      setIsPageDragging(false);

      const files = e.dataTransfer?.files;
      if (!files || files.length === 0) return;

      e.preventDefault();

      if (!validateCount(files.length)) return;

      uploadFiles(files);
    };

    const handleDragOver = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) {
        e.preventDefault();
      }
    };

    document.addEventListener("dragenter", handleDragEnter);
    document.addEventListener("dragleave", handleDragLeave);
    document.addEventListener("drop", handleDrop);
    document.addEventListener("dragover", handleDragOver);

    return () => {
      document.removeEventListener("dragenter", handleDragEnter);
      document.removeEventListener("dragleave", handleDragLeave);
      document.removeEventListener("drop", handleDrop);
      document.removeEventListener("dragover", handleDragOver);
    };
  }, [uploadFiles, validateCount]);

  return {
    isPageDragging,
    pageDragAttachments,
    setPageDragAttachments,
  };
}
