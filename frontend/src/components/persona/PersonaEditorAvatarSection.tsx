import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Camera, Smile } from "lucide-react";
import { uploadApi } from "../../services/api";
import type { UploadHandle } from "../../services/api/upload";
import { compressImageFile } from "../../utils/imageCompression";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import { Button, IconButton } from "../common/ui";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { isPersonaImageAvatar, isEmojiAvatar } from "./personaAvatar";
import { getEmojiAssetUrl } from "../../utils/emojiAssets";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import { AVATAR_EMOJIS } from "./PersonaEditorTypes";

interface AvatarSectionProps {
  avatar: string;
  onAvatarChange: (avatar: string) => void;
  onUploadingChange: (uploading: boolean) => void;
}

export function AvatarSection({
  avatar,
  onAvatarChange,
  onUploadingChange,
}: AvatarSectionProps) {
  const { t } = useTranslation();
  const pickerId = useId();
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const iconPickerRef = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  const upload = useRef<UploadHandle | null>(null);
  const uploading = useRef(false);
  const [iconPickerOpen, setIconPickerOpen] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [failedFile, setFailedFile] = useState<File | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      upload.current?.abort();
      onUploadingChange(false);
    };
  }, [onUploadingChange]);

  useEffect(() => {
    if (iconPickerOpen) iconPickerRef.current?.querySelector("button")?.focus();
  }, [iconPickerOpen]);

  const handleAvatarUpload = useCallback(
    async (file: File) => {
      if (uploading.current) return;
      uploading.current = true;
      sectionRef.current?.focus({ preventScroll: true });
      setIconPickerOpen(false);
      setFailedFile(null);
      setIsUploadingAvatar(true);
      onUploadingChange(true);
      try {
        const compressed = await compressImageFile(file, {
          maxDimension: 256,
          targetSizeKB: 100,
          skipBelowKB: 100,
        });
        if (!mounted.current) return;
        upload.current = uploadApi.uploadFile(compressed, {
          folder: "persona-avatars",
        });
        const result = await upload.current.promise;
        if (mounted.current) onAvatarChange(result.url);
      } catch {
        if (mounted.current) setFailedFile(file);
      } finally {
        if (mounted.current) {
          upload.current = null;
          uploading.current = false;
          setIsUploadingAvatar(false);
          onUploadingChange(false);
        }
      }
    },
    [onUploadingChange, onAvatarChange],
  );

  const iconTrigger = () =>
    sectionRef.current?.querySelector<HTMLButtonElement>(
      ".ppe-avatar-actions > button",
    );
  const avatarLabel = t(
    avatar ? "personaPresets.changeAvatar" : "personaPresets.uploadAvatar",
  );
  const removeLabel = `${t("common.remove")} ${t("personaPresets.avatar")}`;
  return (
    <div ref={sectionRef} tabIndex={-1} className="ppe-avatar-upload">
      <button
        type="button"
        className="ppe-avatar-preview"
        aria-label={avatarLabel}
        title={avatarLabel}
        disabled={isUploadingAvatar}
        onClick={() => avatarInputRef.current?.click()}
      >
        {isEmojiAvatar(avatar) ? (
          <PersonaAvatarImage
            avatar={getEmojiAssetUrl(avatar, "3d")}
            alt=""
            className="ppe-avatar-img"
          />
        ) : isPersonaImageAvatar(avatar) ? (
          <PersonaAvatarImage
            avatar={avatar}
            alt=""
            className="ppe-avatar-img"
          />
        ) : (
          <span className="ppe-avatar-placeholder">
            {avatar ? (
              <PersonaAvatarIcon avatar={avatar} size={20} />
            ) : (
              <Camera size={18} aria-hidden="true" />
            )}
          </span>
        )}
        {isUploadingAvatar && (
          <span className="ppe-avatar-uploading" role="status">
            <LoadingSpinner size="sm" />
            <span className="sr-only">{t("fileUpload.uploading")}</span>
          </span>
        )}
      </button>
      <input
        ref={avatarInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        disabled={isUploadingAvatar}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleAvatarUpload(file);
          e.target.value = "";
        }}
      />
      <div className="ppe-avatar-actions">
        <Button
          size="sm"
          disabled={isUploadingAvatar}
          aria-expanded={iconPickerOpen}
          aria-controls={iconPickerOpen ? pickerId : undefined}
          onClick={() => {
            setIconPickerOpen((v) => !v);
          }}
          leftIcon={<Smile size={14} aria-hidden="true" />}
        >
          {t("personaPresets.pickIcon")}
        </Button>
        {avatar && (
          <IconButton
            size="sm"
            disabled={isUploadingAvatar}
            aria-label={removeLabel}
            title={removeLabel}
            icon={<X size={14} aria-hidden="true" />}
            onClick={() => {
              setFailedFile(null);
              onAvatarChange("");
              iconTrigger()?.focus();
            }}
          />
        )}
      </div>
      {iconPickerOpen && (
        <div
          ref={iconPickerRef}
          id={pickerId}
          className="ppe-icon-picker"
          role="group"
          aria-label={t("personaPresets.pickIcon")}
          onBlur={(event) => {
            if (
              event.relatedTarget instanceof Node &&
              !event.currentTarget.contains(event.relatedTarget) &&
              event.relatedTarget !== iconTrigger()
            )
              setIconPickerOpen(false);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.stopPropagation();
            if (event.nativeEvent.isComposing || event.keyCode === 229) return;
            event.preventDefault();
            setIconPickerOpen(false);
            iconTrigger()?.focus();
          }}
        >
          {AVATAR_EMOJIS.map((item) => (
            <button
              key={item.emoji}
              type="button"
              className="ppe-icon-picker-item"
              aria-label={t(item.labelKey)}
              title={t(item.labelKey)}
              aria-pressed={avatar === item.emoji}
              onClick={() => {
                setFailedFile(null);
                onAvatarChange(item.emoji);
                setIconPickerOpen(false);
                iconTrigger()?.focus();
              }}
            >
              <span className="relative inline-flex size-5">
                <ImageWithSkeleton
                  src={getEmojiAssetUrl(item.emoji, "3d")}
                  alt=""
                  skipUrlResolve
                  inline
                  className="rounded-md"
                  style={{ width: 20, height: 20, objectFit: "contain" }}
                />
              </span>
            </button>
          ))}
        </div>
      )}
      {failedFile && (
        <div className="ppe-avatar-error">
          <p role="alert">{t("personaPresets.avatarUploadFailed")}</p>
          <Button size="sm" onClick={() => void handleAvatarUpload(failedFile)}>
            {t("common.retry")}
          </Button>
        </div>
      )}
    </div>
  );
}
