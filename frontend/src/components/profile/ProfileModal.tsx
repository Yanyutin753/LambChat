import { createPortal } from "react-dom";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Loader2, X, Pencil, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { useAuth } from "../../hooks/useAuth";
import { useBrowserNotification } from "../../hooks/useBrowserNotification";
import { useVersion } from "../../hooks/useVersion";
import { Permission, User } from "../../types";
import { authApi, uploadApi } from "../../services/api";

interface ProfileModalProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: ReturnType<typeof useVersion>["versionInfo"];
}

export function ProfileModal({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
}: ProfileModalProps) {
  const { t } = useTranslation();
  const { user, refreshUser, hasPermission } = useAuth();
  const [userData, setUserData] = useState<User | null>(null);
  const [activeTab, setActiveTab] = useState<
    "info" | "password" | "notification"
  >("info");
  const [isLoading, setIsLoading] = useState(false);

  // Username change state
  const [isEditingUsername, setIsEditingUsername] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [isUpdatingUsername, setIsUpdatingUsername] = useState(false);

  // Password change state
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Avatar upload state
  const [isUploading, setIsUploading] = useState(false);

  // Permission check for avatar upload
  const canUploadAvatar = hasPermission(Permission.AVATAR_UPLOAD);

  // Browser notification
  const {
    requestPermission,
    isSupported,
    permission,
    isMobile,
    isMobileNotificationSupported,
  } = useBrowserNotification();

  // Sync user data when modal opens or user changes
  useEffect(() => {
    if (showProfileModal && user) {
      setUserData(user);
    }
  }, [showProfileModal, user]);

  // Reset state when modal opens
  useEffect(() => {
    if (showProfileModal) {
      setActiveTab("info");
      setIsEditingUsername(false);
      setNewUsername("");
      setUsernameError("");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordError("");
      setPasswordSuccess(false);
    }
  }, [showProfileModal]);

  // Compress image file to target size (default 100KB)
  const compressImage = async (
    file: File,
    targetSizeKB: number = 100,
    maxWidth: number = 512,
    maxHeight: number = 512,
  ): Promise<File> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        // Calculate new dimensions while maintaining aspect ratio
        let { width, height } = img;
        if (width > maxWidth || height > maxHeight) {
          const ratio = Math.min(maxWidth / width, maxHeight / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }

        // Create canvas and draw image
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Failed to get canvas context"));
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);

        // Try different quality levels to meet target size
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

              // If size is within target or we've reached minimum quality
              if (blob.size <= targetBytes || quality <= minQuality) {
                const compressedFile = new File([blob], file.name, {
                  type: "image/jpeg",
                  lastModified: Date.now(),
                });
                resolve(compressedFile);
                return;
              }

              // Reduce quality and try again
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
        reject(new Error("Failed to load image"));
      };

      img.src = URL.createObjectURL(file);
    });
  };

  // Handle avatar upload
  // Note: Avatar is stored as base64 in database, no S3 required
  const handleAvatarUpload = async (file: File) => {
    setIsUploading(true);
    try {
      // Compress image to under 100KB before uploading
      const compressedFile = await compressImage(file, 100, 512, 512);

      // Upload avatar (stored as base64 in database)
      await uploadApi.uploadAvatar(compressedFile);
      // Refresh user data in both local state and global auth context
      const user = await authApi.getProfile();
      setUserData(user);
      // Update global auth context to refresh avatar in header/sidebar
      refreshUser();
    } catch (error) {
      console.error("Failed to upload avatar:", error);
      const message = error instanceof Error ? error.message : "Upload failed";
      toast.error(message);
    } finally {
      setIsUploading(false);
    }
  };

  // Handle avatar delete
  const handleAvatarDelete = async () => {
    setIsUploading(true);
    try {
      await uploadApi.deleteAvatar();
      // Refresh user data in both local state and global auth context
      const user = await authApi.getProfile();
      setUserData(user);
      // Update global auth context to refresh avatar in header/sidebar
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

  // Handle username update
  const handleUsernameUpdate = async () => {
    setUsernameError("");

    if (!newUsername || newUsername.length < 3 || newUsername.length > 50) {
      setUsernameError(t("profile.usernameLengthError"));
      return;
    }

    setIsUpdatingUsername(true);
    try {
      const updatedUser = await authApi.updateUsername(newUsername);
      setUserData(updatedUser);
      // Refresh global auth context
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

  // Handle password change
  const handlePasswordChange = async () => {
    setPasswordError("");
    setPasswordSuccess(false);

    if (!oldPassword || !newPassword || !confirmPassword) {
      setPasswordError(
        t("profile.oldPassword") +
          ", " +
          t("profile.newPassword") +
          ", " +
          t("profile.confirmPassword") +
          " required",
      );
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordError(t("auth.validation.passwordMismatch"));
      return;
    }

    if (newPassword.length < 6) {
      setPasswordError(t("auth.validation.passwordMinLength"));
      return;
    }

    setIsLoading(true);
    try {
      await authApi.changePassword(oldPassword, newPassword);
      setPasswordSuccess(true);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      setPasswordError(
        (error as Error).message || t("profile.passwordChangeFailed"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  if (!showProfileModal) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50"
      onClick={() => onCloseProfileModal()}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white dark:bg-stone-800 shadow-2xl border border-gray-200 dark:border-stone-700 overflow-hidden mx-4 max-h-[90vh] max-h-[90dvh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-4 py-3 border-b border-gray-200 dark:border-stone-700 flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900 dark:text-stone-100">
            {t("profile.title")}
          </h3>
          <button
            onClick={onCloseProfileModal}
            className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-stone-700"
          >
            <X size={20} className="text-gray-500 dark:text-stone-400" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-stone-700">
          <button
            onClick={() => setActiveTab("info")}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "info"
                ? "text-amber-600 border-b-2 border-amber-600"
                : "text-gray-500 dark:text-stone-400 hover:text-gray-700 dark:hover:text-stone-200"
            }`}
          >
            {t("profile.title")}
          </button>
          <button
            onClick={() => setActiveTab("password")}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              activeTab === "password"
                ? "text-amber-600 border-b-2 border-amber-600"
                : "text-gray-500 dark:text-stone-400 hover:text-gray-700 dark:hover:text-stone-200"
            }`}
          >
            {t("profile.changePassword")}
          </button>
          <button
            onClick={() => setActiveTab("notification")}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "notification"
                ? "text-amber-600 border-b-2 border-amber-600"
                : "text-gray-500 dark:text-stone-400 hover:text-gray-700 dark:hover:text-stone-200"
            }`}
          >
            {t("profile.notifications")}
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {activeTab === "info" && (
            <>
              {/* Avatar */}
              <div className="flex flex-col items-center mb-6">
                <div className="relative">
                  {userData?.avatar_url ? (
                    <img
                      src={userData.avatar_url}
                      alt="Avatar"
                      className="w-20 h-20 rounded-full object-cover border-4 border-white dark:border-stone-700 shadow-md"
                    />
                  ) : (
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-stone-500 to-stone-700 flex items-center justify-center border-4 border-white dark:border-stone-700 shadow-md">
                      <span className="text-2xl font-bold text-white">
                        {userData?.username?.charAt(0).toUpperCase() || "U"}
                      </span>
                    </div>
                  )}
                  {isUploading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-full">
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
                    {userData?.avatar_url && (
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
              <div className="space-y-2">
                {/* Username - editable */}
                <div className="py-3 border-b border-gray-100 dark:border-stone-700">
                  {isEditingUsername ? (
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={newUsername}
                        onChange={(e) => setNewUsername(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 dark:border-stone-600 bg-gray-50 dark:bg-stone-900 px-3 py-2 text-sm text-gray-900 dark:text-stone-100 placeholder-gray-400 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                        minLength={3}
                        maxLength={50}
                        placeholder="Enter new username"
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
                            isUpdatingUsername ||
                            newUsername === userData?.username
                          }
                          className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-medium rounded-md transition-colors disabled:opacity-50"
                        >
                          {isUpdatingUsername ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            t("common.save")
                          )}
                        </button>
                        <button
                          onClick={() => {
                            setIsEditingUsername(false);
                            setNewUsername("");
                            setUsernameError("");
                          }}
                          className="px-3 py-1.5 border border-gray-200 dark:border-stone-600 text-gray-600 dark:text-stone-400 text-xs font-medium rounded-md hover:bg-gray-50 dark:hover:bg-stone-700 transition-colors"
                        >
                          {t("common.cancel")}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500 dark:text-stone-400">
                        {t("profile.username")}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900 dark:text-stone-100">
                          {userData?.username || "-"}
                        </span>
                        <button
                          onClick={() => {
                            setNewUsername(userData?.username || "");
                            setIsEditingUsername(true);
                          }}
                          className="text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded-md transition-colors"
                          title={t("common.edit")}
                        >
                          <Pencil size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-stone-700">
                  <span className="text-sm text-gray-500 dark:text-stone-400">
                    {t("profile.email")}
                  </span>
                  <span className="text-sm font-medium text-gray-900 dark:text-stone-100">
                    {userData?.email || "-"}
                  </span>
                </div>
                {userData?.roles && userData.roles.length > 0 && (
                  <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-stone-700">
                    <span className="text-sm text-gray-500 dark:text-stone-400">
                      {t("profile.roles")}
                    </span>
                    <span className="text-sm font-medium text-gray-900 dark:text-stone-100">
                      {userData.roles.join(", ")}
                    </span>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === "password" && (
            <div className="space-y-3">
              {passwordSuccess && (
                <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 text-sm">
                  {t("profile.passwordChanged")}
                </div>
              )}

              {passwordError && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-sm">
                  {passwordError}
                </div>
              )}

              {/* Old Password */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1">
                  {t("profile.oldPassword")}
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={oldPassword}
                    onChange={(e) => setOldPassword(e.target.value)}
                    className="w-full px-4 py-2.5 pr-10 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                    placeholder={t("profile.oldPassword")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-stone-300"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {/* New Password */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1">
                  {t("profile.newPassword")}
                </label>
                <input
                  type={showPassword ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                  placeholder={t("profile.newPassword")}
                />
              </div>

              {/* Confirm Password */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1">
                  {t("profile.confirmPassword")}
                </label>
                <input
                  type={showPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                  placeholder={t("profile.confirmPassword")}
                />
              </div>

              {/* Submit Button */}
              <button
                onClick={handlePasswordChange}
                disabled={isLoading}
                className="w-full py-2.5 px-4 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    {t("common.loading")}
                  </>
                ) : (
                  t("profile.changePassword")
                )}
              </button>
            </div>
          )}

          {activeTab === "notification" && (
            <div className="space-y-4">
              {/* Browser Notification Setting */}
              <div className="bg-gray-50 dark:bg-stone-700/50 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-gray-900 dark:text-stone-100">
                      {t("profile.browserNotification")}
                    </h4>
                    <p className="text-sm text-gray-500 dark:text-stone-400 mt-1">
                      {t("profile.browserNotificationDesc")}
                    </p>
                  </div>
                  {!isSupported ? (
                    <span className="text-xs text-gray-400">
                      {t("profile.notSupported")}
                    </span>
                  ) : permission === "granted" ? (
                    <span className="text-sm text-green-600 flex items-center gap-1">
                      <Check size={16} />
                      {t("profile.enabled")}
                    </span>
                  ) : (
                    <button
                      onClick={requestPermission}
                      className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded-lg hover:bg-amber-700"
                    >
                      {permission === "denied"
                        ? t("profile.retry")
                        : t("profile.enable")}
                    </button>
                  )}
                </div>

                {permission === "denied" && (
                  <p className="text-xs text-red-500 mt-2">
                    {t("profile.notificationDeniedHint")}
                  </p>
                )}
              </div>

              {/* Mobile Notification Status */}
              {isMobile && (
                <div className="bg-gray-50 dark:bg-stone-700/50 rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-stone-100">
                        {t("profile.mobileNotification")}
                      </h4>
                      <p className="text-sm text-gray-500 dark:text-stone-400 mt-1">
                        {t("profile.mobileNotificationDesc")}
                      </p>
                    </div>
                    <span
                      className={`text-sm flex items-center gap-1 ${
                        isMobileNotificationSupported()
                          ? "text-green-600"
                          : "text-amber-600"
                      }`}
                    >
                      {isMobileNotificationSupported() ? (
                        <>
                          <Check size={16} />
                          {t("profile.supported")}
                        </>
                      ) : (
                        t("profile.limitedSupport")
                      )}
                    </span>
                  </div>
                </div>
              )}

              {/* WebSocket Connection Status */}
              <div className="bg-gray-50 dark:bg-stone-700/50 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-gray-900 dark:text-stone-100">
                      {t("profile.realtimeNotification")}
                    </h4>
                    <p className="text-sm text-gray-500 dark:text-stone-400 mt-1">
                      {t("profile.realtimeNotificationDesc")}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-4 py-3 bg-gray-50 dark:bg-stone-700/50 flex items-center justify-end">
          <div className="text-xs text-gray-400 dark:text-stone-500">
            <span className="font-semibold text-gray-500 dark:text-stone-400 font-serif">
              LambChat
            </span>
            {versionInfo?.app_version && (
              <span className="ml-2">v{versionInfo.app_version}</span>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
