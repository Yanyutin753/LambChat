import { useState, useCallback, memo } from "react";
import { Paperclip } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { MessageAttachment, Permission } from "../../types";
import { UploadModal } from "./UploadModal";

interface FileUploadButtonProps {
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (attachments: MessageAttachment[]) => void;
}

// All upload permissions to check if user can upload anything
const UPLOAD_PERMISSIONS: Permission[] = [
  Permission.FILE_UPLOAD_IMAGE,
  Permission.FILE_UPLOAD_VIDEO,
  Permission.FILE_UPLOAD_AUDIO,
  Permission.FILE_UPLOAD_DOCUMENT,
];

export const FileUploadButton = memo(function FileUploadButton({
  attachments: externalAttachments = [],
  onAttachmentsChange,
}: FileUploadButtonProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Check if user has any upload permission
  const canUpload = UPLOAD_PERMISSIONS.some((perm) => hasPermission(perm));

  // Handle uploads from modal - append to existing attachments
  const handleUpload = useCallback(
    (newAttachments: MessageAttachment[]) => {
      const updated = [...externalAttachments, ...newAttachments];
      onAttachmentsChange?.(updated);
    },
    [externalAttachments, onAttachmentsChange],
  );

  // Open modal
  const openModal = useCallback(() => {
    setIsModalOpen(true);
  }, []);

  // Close modal
  const closeModal = useCallback(() => {
    setIsModalOpen(false);
  }, []);

  if (!canUpload) return null;

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        className="flex items-center justify-center rounded-full p-2 border border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300 transition-all duration-300"
        title={t("fileUpload.title")}
      >
        <Paperclip size={18} />
      </button>

      <UploadModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onUpload={handleUpload}
      />
    </>
  );
});
