import { useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { Mail, ExternalLink } from "lucide-react";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";
import { Button, IconButton, Input } from "../../common";
import { useAuth } from "../../../hooks/useAuth";
import { useSettings } from "../../../hooks/useSettings";
import { Permission } from "../../../types";
import { authApi, getFullUrl, uploadApi } from "../../../services/api";
import { CatalogStatus } from "../../common/CatalogStatus";
import { usePreferenceWrites } from "../../../hooks/usePreferenceWrites";
import { compressImageFile } from "../../../utils/imageCompression";

export function ProfileInfoTab() {
  const { user } = useAuth();
  return <ProfileInfoContent key={user?.id} />;
}

function ProfileInfoContent() {
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

  const mounted = useRef(true);
  const usernamePending = useRef(false);
  const usernameFormRef = useRef<HTMLFormElement>(null);
  const infoRef = useRef<HTMLDivElement>(null);
  const avatarRef = useRef<HTMLDivElement>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const compressionRef = useRef<AbortController | null>(null);
  const restoreUsernameFocus = useRef(false);
  const usernameErrorId = useId();
  const { states, save, retry } = usePreferenceWrites(user?.id);
  const [avatarOperation, setAvatarOperation] = useState<"upload" | "delete">(
    "upload",
  );
  const isUploading = states.avatar === "saving";
  const canUploadAvatar = hasPermission(Permission.AVATAR_UPLOAD);

  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      compressionRef.current?.abort();
    };
  }, []);
  useLayoutEffect(() => {
    if (!isEditingUsername && restoreUsernameFocus.current) {
      infoRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
      restoreUsernameFocus.current = false;
    }
  }, [isEditingUsername]);

  const cancelUsername = () => {
    if (usernamePending.current) return;
    restoreUsernameFocus.current = true;
    setIsEditingUsername(false);
    setNewUsername("");
    setUsernameError("");
  };

  const handleAvatarUpload = (file: File) => {
    let compressed: File | undefined;
    if (
      !save(
        "avatar",
        async () => {
          if (!compressed) {
            compressionRef.current = new AbortController();
            compressed = await compressImageFile(file, {
              maxDimension: 512,
              targetSizeKB: 100,
              skipBelowKB: 100,
              fallback: "main-thread",
              signal: compressionRef.current.signal,
            });
          }
          if (!mounted.current) return;
          await uploadApi.uploadAvatar(compressed);
        },
        () => {
          void refreshUser();
        },
      )
    )
      return;
    setAvatarOperation("upload");
    avatarRef.current?.focus({ preventScroll: true });
  };

  const handleAvatarDelete = () => {
    if (
      !save(
        "avatar",
        () => uploadApi.deleteAvatar(),
        () => {
          void refreshUser();
          toast.success(t("profile.avatarDeleted"));
        },
      )
    )
      return;
    setAvatarOperation("delete");
    avatarRef.current?.focus({ preventScroll: true });
  };

  const handleUsernameUpdate = async () => {
    if (usernamePending.current) return;
    setUsernameError("");

    if (!newUsername || newUsername.length < 3 || newUsername.length > 50) {
      setUsernameError(t("profile.usernameLengthError"));
      return;
    }

    usernamePending.current = true;
    usernameFormRef.current?.focus({ preventScroll: true });
    setIsUpdatingUsername(true);
    try {
      await authApi.updateUsername(newUsername);
      if (!mounted.current) return;
      void refreshUser();
      restoreUsernameFocus.current = true;
      setIsEditingUsername(false);
      setNewUsername("");
      toast.success(t("profile.usernameUpdated"));
    } catch (error) {
      if (!mounted.current) return;
      setUsernameError(
        (error as Error).message || t("profile.usernameUpdateFailed"),
      );
    } finally {
      if (mounted.current) {
        usernamePending.current = false;
        setIsUpdatingUsername(false);
      }
    }
  };

  return (
    <>
      {/* Avatar */}
      <div
        ref={avatarRef}
        tabIndex={-1}
        className="profile-avatar"
        aria-busy={isUploading}
      >
        <div className="relative">
          {user?.avatar_url ? (
            <ImageWithSkeleton
              src={getFullUrl(user.avatar_url) ?? user.avatar_url}
              alt={t("profile.avatar", "头像")}
              skipUrlResolve
              inline
              className="size-16 rounded-full border border-theme-border"
              errorFallback={
                <div className="profile-avatar-fallback">
                  <span className="text-24 font-semibold">
                    {user?.username?.charAt(0).toUpperCase() || "U"}
                  </span>
                </div>
              }
            />
          ) : (
            <div className="profile-avatar-fallback">
              <span className="text-24 font-semibold">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
        </div>
        {canUploadAvatar && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={isUploading}
              className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
              onClick={() => avatarInputRef.current?.click()}
            >
              {t("profile.changeAvatar")}
            </Button>
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              disabled={isUploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleAvatarUpload(file);
                e.target.value = "";
              }}
            />
            {user?.avatar_url && (
              <Button
                variant="danger"
                size="sm"
                onClick={handleAvatarDelete}
                disabled={isUploading}
                className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
              >
                {t("profile.deleteAvatar")}
              </Button>
            )}
          </div>
        )}
        {canUploadAvatar && states.avatar && (
          <div className="basis-full">
            <CatalogStatus
              label={t("profile.avatar")}
              loading={isUploading}
              error={states.avatar === "error"}
              loadingText={t(
                avatarOperation === "upload"
                  ? "fileUpload.uploading"
                  : "common.saving",
              )}
              errorText={t(
                avatarOperation === "upload"
                  ? "profile.uploadFailed"
                  : "profile.deleteFailed",
              )}
              onRetry={() => retry("avatar")}
              focusTargetRef={avatarRef}
            />
          </div>
        )}
      </div>

      {/* User Info */}
      <div className="space-y-0">
        {/* Username - editable */}
        <div
          ref={infoRef}
          className="py-3.5 border-b border-theme-border-subtle dark:border-stone-700/60"
        >
          {isEditingUsername ? (
            <form
              ref={usernameFormRef}
              tabIndex={-1}
              className="space-y-2"
              aria-busy={isUpdatingUsername}
              onSubmit={(event) => {
                event.preventDefault();
                void handleUsernameUpdate();
              }}
              onKeyDown={(event) => {
                if (event.key !== "Escape") return;
                event.stopPropagation();
                if (event.nativeEvent.isComposing || event.keyCode === 229)
                  return;
                event.preventDefault();
                cancelUsername();
              }}
            >
              <label
                className="block text-14 text-theme-text-secondary"
                htmlFor={`${usernameErrorId}-input`}
              >
                {t("profile.username")}
              </label>
              <Input
                id={`${usernameErrorId}-input`}
                type="text"
                value={newUsername}
                disabled={isUpdatingUsername}
                onChange={(e) => {
                  setNewUsername(e.target.value);
                  setUsernameError("");
                }}
                minLength={3}
                maxLength={50}
                placeholder={t("profile.usernamePlaceholder")}
                error={!!usernameError}
                aria-describedby={usernameError ? usernameErrorId : undefined}
                autoFocus
              />
              {usernameError && (
                <p
                  id={usernameErrorId}
                  role="alert"
                  className="text-12 text-theme-error [overflow-wrap:anywhere]"
                >
                  {usernameError}
                </p>
              )}
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  type="submit"
                  disabled={
                    isUpdatingUsername || newUsername === user?.username
                  }
                  loading={isUpdatingUsername}
                  leftIcon={<Check size={14} />}
                  className="flex-1 sm:flex-none max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
                >
                  {t(
                    isUpdatingUsername
                      ? "common.saving"
                      : usernameError
                        ? "common.retry"
                        : "common.save",
                  )}
                </Button>
                <Button
                  onClick={cancelUsername}
                  disabled={isUpdatingUsername}
                  className="flex-1 sm:flex-none max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
                >
                  {t("common.cancel")}
                </Button>
              </div>
            </form>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <span className="text-14 text-theme-text-secondary dark:text-stone-400 shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-14 font-medium text-theme-text dark:text-stone-100 text-right [overflow-wrap:anywhere]">
                  {user?.username || "-"}
                </span>
                <IconButton
                  aria-label={t("common.edit")}
                  onClick={() => {
                    setNewUsername(user?.username || "");
                    setIsEditingUsername(true);
                  }}
                  icon={<Pencil size={13} />}
                  size="sm"
                  className="shrink-0 text-theme-primary max-sm:!size-11 [@media(pointer:coarse)]:!size-11"
                  title={t("common.edit")}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle dark:border-stone-700/60 gap-3">
          <span className="text-14 text-theme-text-secondary dark:text-stone-400 shrink-0">
            {t("profile.email")}
          </span>
          <span className="min-w-0 text-14 font-medium text-theme-text dark:text-stone-100 text-right [overflow-wrap:anywhere]">
            {user?.email || "-"}
          </span>
        </div>
        {user?.roles && user.roles.length > 0 && (
          <div className="flex items-center justify-between py-3.5 gap-3">
            <span className="text-14 text-theme-text-secondary dark:text-stone-400 shrink-0">
              {t("profile.roles")}
            </span>
            <div className="flex flex-wrap justify-end gap-1.5">
              {user.roles.map((role) => (
                <span
                  key={role}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-12 font-medium bg-theme-bg-subtle dark:bg-stone-700 text-theme-text-secondary dark:text-stone-300"
                >
                  {role}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Contact Info */}
        {(adminEmail || adminUrl) && (
          <div className="mt-5 pt-5 border-t border-theme-border-subtle dark:border-stone-700/60 space-y-0">
            <p className="text-12 text-theme-text-tertiary dark:text-stone-500 mb-1">
              {t("about.contactTitle", "Contact")}
            </p>
            {adminEmail && (
              <a
                href={`mailto:${adminEmail}`}
                className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle dark:border-stone-700/60 gap-3 group"
              >
                <span className="flex items-center gap-2 text-14 text-theme-text-secondary dark:text-stone-400 shrink-0">
                  <Mail size={14} />
                  {t("profile.email", "Email")}
                </span>
                <span className="min-w-0 text-right [overflow-wrap:anywhere] text-14 font-medium text-theme-text dark:text-stone-100 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
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
                <span className="flex items-center gap-2 text-14 text-theme-text-secondary dark:text-stone-400 shrink-0">
                  <ExternalLink size={14} />
                  {t("about.contactSupport", "Support")}
                </span>
                <span className="text-14 font-medium text-theme-text-tertiary dark:text-stone-500 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
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
