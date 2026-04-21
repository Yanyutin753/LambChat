import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Pencil, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { Mail, ExternalLink } from "lucide-react";
import { useAuth } from "../../../hooks/useAuth";
import { useSettings } from "../../../hooks/useSettings";
import { Permission } from "../../../types";
import { authApi, uploadApi } from "../../../services/api";

export function ProfileInfoTab() {
  const { t } = useTranslation();
  const { user, refreshUser, hasPermission } = useAuth();
  const { getSettingValue } = useSettings();
  const adminEmail = getSettingValue("ADMIN_CONTACT_EMAIL") as string | null;
  const adminUrl = getSettingValue("ADMIN_CONTACT_URL") as string | null;

  // Username change state
  const [isEditingUsername, setIsEditingUsername] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [isUpdatingUsername, setIsUpdatingUsername] = useState(false);

  // Avatar upload state
  const [isUploading, setIsUploading] = useState(false);
  const [imgError, setImgError] = useState(false);

  // Permission check for avatar upload
  const canUploadAvatar = hasPermission(Permission.AVATAR_UPLOAD);

  // Compress image file to target size (default 100KB)
  const compressImage = async (
    file: File,
    targetSizeKB: number = 100,
    maxWidth: number = 512,
    maxHeight: number = 512,
  ): Promise<File> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const objectUrl = URL.createObjectURL(file);
      img.onload = () => {
        URL.revokeObjectURL(objectUrl);
        let { width, height } = img;
        if (width > maxWidth || height > maxHeight) {
          const ratio = Math.min(maxWidth / width, maxHeight / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Failed to get canvas context"));
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);

        const targetBytes = targetSizeKB * 1024;
        let quality = 0.9;
        const minQuality = 0.1;

        const tryCompress = (): void => {
          canvas.toBlob(
            (blob) => {
              if (!blob) {
                reject(new Error("Failed to compress image"));
                return;
              }

              if (blob.size <= targetBytes || quality <= minQuality) {
                const compressedFile = new File([blob], file.name, {
                  type: "image/jpeg",
                  lastModified: Date.now(),
                });
                resolve(compressedFile);
                return;
              }

              quality -= 0.1;
              tryCompress();
            },
            "image/jpeg",
            quality,
          );
        };

        tryCompress();
      };

      img.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        reject(new Error("Failed to load image"));
      };

      img.src = objectUrl;
    });
  };

  const handleAvatarUpload = async (file: File) => {
    setIsUploading(true);
    try {
      const compressedFile = await compressImage(file, 100, 512, 512);
      await uploadApi.uploadAvatar(compressedFile);
      await authApi.getProfile();
      refreshUser();
    } catch (error) {
      console.error("Failed to upload avatar:", error);
      const message = error instanceof Error ? error.message : "Upload failed";
      toast.error(message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleAvatarDelete = async () => {
    setIsUploading(true);
    try {
      await uploadApi.deleteAvatar();
      await authApi.getProfile();
      refreshUser();
      toast.success(t("profile.avatarDeleted"));
    } catch (error) {
      console.error("Failed to delete avatar:", error);
      const message = error instanceof Error ? error.message : "Delete failed";
      toast.error(message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleUsernameUpdate = async () => {
    setUsernameError("");

    if (!newUsername || newUsername.length < 3 || newUsername.length > 50) {
      setUsernameError(t("profile.usernameLengthError"));
      return;
    }

    setIsUpdatingUsername(true);
    try {
      await authApi.updateUsername(newUsername);
      refreshUser();
      setIsEditingUsername(false);
      setNewUsername("");
      toast.success(t("profile.usernameUpdated"));
    } catch (error) {
      setUsernameError(
        (error as Error).message || t("profile.usernameUpdateFailed"),
      );
    } finally {
      setIsUpdatingUsername(false);
    }
  };

  return (
    <>
      {/* Avatar */}
      <div className="flex flex-col items-center mb-6">
        <div className="relative">
          {user?.avatar_url && !imgError ? (
            <img
              src={user.avatar_url}
              alt="Avatar"
              className="w-20 h-20 rounded-full object-cover border-4 border-white dark:border-stone-700 shadow-lg ring-2 ring-stone-100 dark:ring-stone-600"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center border-4 border-white dark:border-stone-700 shadow-lg ring-2 ring-stone-100 dark:ring-stone-600">
              <span className="text-2xl font-bold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
          {isUploading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-full">
              <Loader2 size={24} className="animate-spin text-white" />
            </div>
          )}
        </div>
        {canUploadAvatar && (
          <div className="mt-3 flex items-center gap-2">
            <label className="cursor-pointer rounded-lg bg-stone-100 dark:bg-stone-700 px-3 py-1.5 text-xs font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-600 transition-colors">
              {t("profile.changeAvatar")}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                disabled={isUploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleAvatarUpload(file);
                }}
              />
            </label>
            {user?.avatar_url && (
              <button
                onClick={handleAvatarDelete}
                disabled={isUploading}
                className="rounded-lg bg-red-50 dark:bg-red-900/30 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors disabled:opacity-50"
              >
                {t("profile.deleteAvatar")}
              </button>
            )}
          </div>
        )}
      </div>

      {/* User Info */}
      <div className="space-y-0">
        {/* Username - editable */}
        <div className="py-3.5 border-b border-stone-100 dark:border-stone-700/60">
          {isEditingUsername ? (
            <div className="space-y-2">
              <input
                type="text"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="w-full rounded-lg border border-stone-300 dark:border-stone-600 bg-stone-50 dark:bg-stone-900 px-3 py-2.5 text-sm text-stone-900 dark:text-stone-100 placeholder-stone-400 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20"
                minLength={3}
                maxLength={50}
                placeholder={t("profile.usernamePlaceholder")}
                autoFocus
              />
              {usernameError && (
                <p className="text-xs text-red-500 dark:text-red-400">
                  {usernameError}
                </p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={handleUsernameUpdate}
                  disabled={
                    isUpdatingUsername || newUsername === user?.username
                  }
                  className="flex-1 sm:flex-none px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
                >
                  {isUpdatingUsername ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Check size={14} />
                  )}
                  {t("common.save")}
                </button>
                <button
                  onClick={() => {
                    setIsEditingUsername(false);
                    setNewUsername("");
                    setUsernameError("");
                  }}
                  className="flex-1 sm:flex-none px-4 py-2 border border-stone-200 dark:border-stone-600 text-stone-600 dark:text-stone-400 text-sm font-medium rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-stone-500 dark:text-stone-400 shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                  {user?.username || "-"}
                </span>
                <button
                  onClick={() => {
                    setNewUsername(user?.username || "");
                    setIsEditingUsername(true);
                  }}
                  className="shrink-0 text-amber-500 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded-md p-1 transition-colors"
                  title={t("common.edit")}
                >
                  <Pencil size={13} />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between py-3.5 border-b border-stone-100 dark:border-stone-700/60 gap-3">
          <span className="text-sm text-stone-500 dark:text-stone-400 shrink-0">
            {t("profile.email")}
          </span>
          <span className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate text-right">
            {user?.email || "-"}
          </span>
        </div>
        {user?.roles && user.roles.length > 0 && (
          <div className="flex items-center justify-between py-3.5 gap-3">
            <span className="text-sm text-stone-500 dark:text-stone-400 shrink-0">
              {t("profile.roles")}
            </span>
            <div className="flex flex-wrap justify-end gap-1.5">
              {user.roles.map((role) => (
                <span
                  key={role}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-stone-100 dark:bg-stone-700 text-stone-600 dark:text-stone-300"
                >
                  {role}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Contact Info */}
        {(adminEmail || adminUrl) && (
          <div className="mt-5 pt-5 border-t border-stone-100 dark:border-stone-700/60 space-y-0">
            <p className="text-xs text-stone-400 dark:text-stone-500 mb-1">
              {t("about.contactTitle", "Contact")}
            </p>
            {adminEmail && (
              <a
                href={`mailto:${adminEmail}`}
                className="flex items-center justify-between py-3.5 border-b border-stone-100 dark:border-stone-700/60 gap-3 group"
              >
                <span className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400 shrink-0">
                  <Mail size={14} />
                  {t("profile.email", "Email")}
                </span>
                <span className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                  {adminEmail}
                </span>
              </a>
            )}
            {adminUrl && (
              <a
                href={adminUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between py-3.5 gap-3 group"
              >
                <span className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400 shrink-0">
                  <ExternalLink size={14} />
                  {t("about.contactSupport", "Support")}
                </span>
                <span className="text-sm font-medium text-stone-400 dark:text-stone-500 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                  →
                </span>
              </a>
            )}
          </div>
        )}
      </div>
    </>
  );
}
