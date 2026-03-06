import { useRef, useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  Routes,
  Route,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
import { Toaster, toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  MessageSquare,
  Package,
  LogOut,
  Users,
  Shield,
  Menu,
  Settings,
  Server,
  Eye,
  EyeOff,
  Loader2,
  X,
  Pencil,
  User,
  Star,
} from "lucide-react";
import { ChatMessage } from "./components/chat/ChatMessage";
import { ChatInput } from "./components/chat/ChatInput";
import { ApprovalPanel } from "./components/panels/ApprovalPanel";
import { SkillsPanel } from "./components/panels/SkillsPanel";
import { SessionSidebar } from "./components/panels/SessionSidebar";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { UsersPanel } from "./components/panels/UsersPanel";
import { RolesPanel } from "./components/panels/RolesPanel";
import { SettingsPanel } from "./components/panels/SettingsPanel";
import { MCPPanel } from "./components/panels/MCPPanel";
import { FeedbackPanel } from "./components/panels/FeedbackPanel";
import { ThemeToggle } from "./components/common/ThemeToggle";
import { LanguageToggle } from "./components/common/LanguageToggle";
import { AgentSelector } from "./components/agent/AgentSelector";
import { SharedPage } from "./components/share/SharedPage";
import { ThemeProvider } from "./contexts/ThemeContext";
import { useSettingsContext } from "./contexts/SettingsContext";
import { useAgent } from "./hooks/useAgent";
import { useApprovals } from "./hooks/useApprovals";
import { useAuth } from "./hooks/useAuth";
import { useTools } from "./hooks/useTools";
import { useSkills } from "./hooks/useSkills";
import { useVersion } from "./hooks/useVersion";
import { usePageTitle } from "./hooks/usePageTitle";
import { Permission, User as UserType } from "./types";
import { authApi, uploadApi, sessionApi } from "./services/api";

type TabType =
  | "chat"
  | "skills"
  | "users"
  | "roles"
  | "settings"
  | "mcp"
  | "feedback";

// Profile Modal Component - renders at document body level via portal
function ProfileModal({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
}: {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: ReturnType<typeof useVersion>["versionInfo"];
}) {
  const { t } = useTranslation();
  const { user, refreshUser, hasPermission } = useAuth();
  const [userData, setUserData] = useState<UserType | null>(null);
  const [activeTab, setActiveTab] = useState<"info" | "password">("info");
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

  // Compress image file to target size (default100KB)
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
      // Compress image to under100KB before uploading
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
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {activeTab === "info" ? (
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
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center border-4 border-white dark:border-stone-700 shadow-md">
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
          ) : (
            /* Password Change Tab */
            <div className="space-y-4">
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
        </div>

        {/* Modal Footer */}
        <div className="px-4 py-3 bg-gray-50 dark:bg-stone-700/50 flex items-center justify-end">
          <div className="text-xs text-gray-400 dark:text-stone-500">
            <span className="font-semibold text-gray-500 dark:text-stone-400">
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

// 用户菜单组件
function UserMenu({ onShowProfile }: { onShowProfile: () => void }) {
  const { t } = useTranslation();
  const { logout, hasAnyPermission, user } = useAuth();
  const { enableMcp, enableSkills } = useSettingsContext();
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, right: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  const canReadSkills =
    hasAnyPermission([Permission.SKILL_READ]) && enableSkills;
  const canManageUsers = hasAnyPermission([
    Permission.USER_READ,
    Permission.USER_WRITE,
  ]);
  const canManageRoles = hasAnyPermission([Permission.ROLE_MANAGE]);
  const canManageSettings = hasAnyPermission([Permission.SETTINGS_MANAGE]);
  const canReadMCP = hasAnyPermission([Permission.MCP_READ]) && enableMcp;
  const canViewFeedback = hasAnyPermission([Permission.FEEDBACK_READ]);

  // 更新菜单位置
  const updateMenuPosition = useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 8, // 8px = mt-2
        right: window.innerWidth - rect.right,
      });
    }
  }, []);

  useEffect(() => {
    const handleClickOutside = () => setShowMenu(false);
    if (showMenu) {
      updateMenuPosition();
      document.addEventListener("click", handleClickOutside);
      window.addEventListener("resize", updateMenuPosition);
      window.addEventListener("scroll", updateMenuPosition, true);
      return () => {
        document.removeEventListener("click", handleClickOutside);
        window.removeEventListener("resize", updateMenuPosition);
        window.removeEventListener("scroll", updateMenuPosition, true);
      };
    }
  }, [showMenu, updateMenuPosition]);

  const handleNavigate = (path: string) => {
    navigate(path);
    setShowMenu(false);
  };

  const navItems = [
    { path: "/chat", label: t("nav.chat"), icon: MessageSquare, show: true },
    {
      path: "/skills",
      label: t("nav.skills"),
      icon: Package,
      show: canReadSkills,
    },
    { path: "/mcp", label: t("nav.mcp"), icon: Server, show: canReadMCP },
    {
      path: "/users",
      label: t("nav.users"),
      icon: Users,
      show: canManageUsers,
    },
    {
      path: "/roles",
      label: t("nav.roles"),
      icon: Shield,
      show: canManageRoles,
    },
    {
      path: "/feedback",
      label: t("nav.feedback"),
      icon: Star,
      show: canViewFeedback,
    },
    {
      path: "/settings",
      label: t("nav.settings"),
      icon: Settings,
      show: canManageSettings,
    },
  ];

  return (
    <>
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <button
          ref={buttonRef}
          onClick={() => setShowMenu(!showMenu)}
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors overflow-hidden"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-5 object-cover rounded-full"
            />
          ) : (
            <div className="flex size-5 items-center justify-center bg-gradient-to-br from-violet-500 to-purple-600 rounded-full">
              <span className="text-sm font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
        </button>

        {showMenu &&
          createPortal(
            <div
              className="fixed z-[100] w-48 sm:w-52 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 overflow-hidden animate-scale-in"
              style={{
                top: `${menuPosition.top}px`,
                right: `${menuPosition.right}px`,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => {
                  onShowProfile();
                  setShowMenu(false);
                }}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50 transition-colors"
              >
                <User size={18} />
                {t("users.user")}
              </button>

              {/* Navigation */}
              <div>
                {navItems
                  .filter((item) => item.show)
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.path}
                        onClick={() => handleNavigate(item.path)}
                        className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50"
                      >
                        <Icon size={18} />
                        {item.label}
                      </button>
                    );
                  })}
              </div>

              {/* Logout */}
              <div className="border-t border-gray-100 dark:border-stone-700">
                <button
                  onClick={() => {
                    logout();
                    setShowMenu(false);
                  }}
                  className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50 transition-colors"
                >
                  <LogOut size={18} />
                  {t("auth.logout")}
                </button>
              </div>
            </div>,
            document.body,
          )}
      </div>
    </>
  );
}

// 主应用内容（需要认证）
function AppContent({ activeTab }: { activeTab: TabType }) {
  const { t } = useTranslation();
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const navigate = useNavigate();
  const { enableMcp, enableSkills } = useSettingsContext();
  const { versionInfo } = useVersion();

  // 获取 approvals hook 的 addApproval 方法
  const {
    approvals,
    respondToApproval,
    addApproval,
    clearApprovals,
    isLoading: approvalLoading,
  } = useApprovals({ sessionId: null }); // 先用 null 初始化

  // 工具选择器 hook
  const {
    tools,
    isLoading: toolsLoading,
    enabledCount: enabledToolsCount,
    totalCount: totalToolsCount,
    toggleTool,
    toggleCategory,
    toggleAll,
    getDisabledToolNames,
  } = useTools({ enabled: enableMcp });

  // Skills 选择器 hook
  const {
    skills,
    isLoading: skillsLoading,
    enabledCount: enabledSkillsCount,
    totalCount: totalSkillsCount,
    toggleSkillWrapper,
    toggleCategory: toggleSkillCategory,
    toggleAll: toggleAllSkills,
    fetchSkills,
  } = useSkills({ enabled: enableSkills });

  const {
    messages,
    isLoading,
    sessionId,
    currentRunId,
    agents,
    currentAgent,
    agentsLoading,
    newlyCreatedSession,
    sendMessage,
    stopGeneration,
    clearMessages,
    selectAgent,
    loadHistory,
  } = useAgent({
    onApprovalRequired: (approval) => {
      // 当 SSE 收到 approval_required 事件时，直接添加到 approvals 列表
      // 无需轮询 /human/pending 接口
      addApproval({
        id: approval.id,
        message: approval.message,
        type: "form",
        fields: approval.fields || [],
        status: "pending",
        session_id: sessionId,
      });
    },
    onClearApprovals: () => {
      // 当对话失败时，清除所有 pending approvals
      clearApprovals();
    },
    getEnabledTools: getDisabledToolNames,
    onSkillAdded: (
      skillName: string,
      _description: string,
      filesCount: number,
    ) => {
      console.log(
        `[App] Skill added: ${skillName} (${filesCount} files), refreshing skills list`,
      );
      fetchSkills();
    },
  });

  // Session name state - needs to be after useAgent since it depends on sessionId
  const [sessionName, setSessionName] = useState<string | null>(null);

  // Fetch session name when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const fetchSessionName = async () => {
      try {
        const session = await sessionApi.get(sessionId);
        if (session?.name) {
          setSessionName(session.name);
        } else {
          setSessionName(null);
        }
      } catch (err) {
        console.warn("[AppContent] Failed to fetch session:", err);
        setSessionName(null);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  // Agent options state
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});

  // Get current agent's options
  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions = currentAgentInfo?.options || {};

  // Reset agent options when agent changes
  useEffect(() => {
    const options = agents.find((a) => a.id === currentAgent)?.options;
    if (options) {
      const defaultValues: Record<string, boolean | string | number> = {};
      Object.entries(options).forEach(([key, option]) => {
        defaultValues[key] = option.default;
      });
      setAgentOptionValues(defaultValues);
    } else {
      setAgentOptionValues({});
    }
  }, [currentAgent, agents]);

  // Handler for toggling agent options
  const handleToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      setAgentOptionValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const { settings } = useSettingsContext();
  const { hasPermission } = useAuth();
  const canSendMessage = hasPermission(Permission.CHAT_WRITE);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Flag to prevent sync loops between URL and state
  const isSyncingRef = useRef(false);
  const [isNearBottom, setIsNearBottom] = useState(true);

  // Check if user is near the bottom (within 100px)
  const checkIfNearBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;
    const threshold = 100;
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      threshold;
    setIsNearBottom(isAtBottom);
    return isAtBottom;
  }, []);

  // Auto-scroll to bottom only when user is already near bottom
  useEffect(() => {
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
    }
  }, [messages, isNearBottom]);

  // Track scroll position
  const handleScroll = useCallback(() => {
    checkIfNearBottom();
  }, [checkIfNearBottom]);

  // Sync from URL only on initial mount
  useEffect(() => {
    if (urlSessionId && !isSyncingRef.current) {
      isSyncingRef.current = true;
      loadHistory(urlSessionId).finally(() => {
        // Delay reset to allow state to settle
        setTimeout(() => {
          isSyncingRef.current = false;
        }, 100);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Sync URL with sessionId state (when sessionId changes from internal actions)
  useEffect(() => {
    if (isSyncingRef.current) return;

    if (sessionId && sessionId !== urlSessionId) {
      // New session created - update URL
      isSyncingRef.current = true;
      navigate(`/chat/${sessionId}`, { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    } else if (!sessionId && urlSessionId) {
      // Session cleared - clear URL
      isSyncingRef.current = true;
      navigate("/chat", { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    }
  }, [sessionId, urlSessionId, navigate]);

  // Handle session selection from sidebar
  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      // loadHistory has its own isLoadingHistoryRef guard, no need to check here
      try {
        await loadHistory(selectedSessionId);
        // Update URL
        navigate(`/chat/${selectedSessionId}`);
        // Scroll to top after loading history
        messagesContainerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        console.error("[handleSelectSession] Error:", err);
      }
    },
    [navigate, loadHistory],
  );

  // Handle new session
  const handleNewSession = useCallback(() => {
    clearMessages();
    // URL sync is handled by the useEffect above
  }, [clearMessages]);

  return (
    <>
      {/* Profile Modal - rendered at top level via portal */}
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={() => setShowProfileModal(false)}
        versionInfo={versionInfo}
      />

      <div className="flex h-[100dvh] w-full overflow-hidden bg-white dark:bg-stone-900">
        {/* Session Sidebar - only show on chat tab */}
        {activeTab === "chat" && (
          <SessionSidebar
            currentSessionId={sessionId}
            onSelectSession={(id) => {
              handleSelectSession(id);
              setMobileSidebarOpen(false);
            }}
            onNewSession={() => {
              handleNewSession();
              setMobileSidebarOpen(false);
            }}
            newSession={newlyCreatedSession}
            mobileOpen={mobileSidebarOpen}
            onMobileClose={() => setMobileSidebarOpen(false)}
            isCollapsed={sidebarCollapsed}
            onToggleCollapsed={setSidebarCollapsed}
            onShowProfile={() => setShowProfileModal(true)}
          />
        )}

        {/* Main Content */}
        <div className="relative z-0 flex flex-1 flex-col min-w-0 overflow-hidden">
          {/* Header */}
          <header className="relative z-50 flex items-center px-3 py-4 sm:px-4 mb-2">
            {/* Left: Expand Sidebar + Menu + Agent Selector / Page Title */}
            <div className="flex items-center gap-2 flex-shrink-0">
              {activeTab === "chat" ? (
                <>
                  {/* Expand sidebar button - when collapsed */}
                  {sidebarCollapsed && (
                    <button
                      onClick={() => setSidebarCollapsed(false)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-stone-800 transition-colors"
                      title={t("sidebar.expandSidebar")}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                        className="w-5 h-5 text-gray-600 dark:text-stone-400"
                      >
                        <path
                          fillRule="evenodd"
                          clipRule="evenodd"
                          d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.07354 19.4265 5.6146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.5523 5 12Z"
                          fill="currentColor"
                        />
                      </svg>
                    </button>
                  )}
                  {/* Mobile menu button - only when sidebar is not collapsed */}
                  {!sidebarCollapsed && (
                    <button
                      onClick={() => setMobileSidebarOpen(true)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-stone-800 sm:hidden transition-colors"
                    >
                      <Menu
                        size={20}
                        className="text-gray-600 dark:text-stone-400"
                      />
                    </button>
                  )}
                  {/* Agent Selector - Performance Optimized */}
                  <AgentSelector
                    agents={agents}
                    currentAgent={currentAgent}
                    agentsLoading={agentsLoading}
                    onSelectAgent={selectAgent}
                  />
                </>
              ) : (
                /* Page Title for non-chat pages */
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => navigate("/chat")}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
                    title={t("errors.backToHome")}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      className="size-5"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
                      />
                    </svg>
                  </button>
                  <div className="flex h-8 items-center gap-2">
                    <span className="text-base font-bold text-gray-700 dark:text-stone-200">
                      LambChat
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Right: New Chat (when sidebar collapsed) + Theme Toggle + User Menu */}
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {activeTab === "chat" && sidebarCollapsed && (
                <button
                  onClick={handleNewSession}
                  className="flex cursor-pointer px-2 py-2 rounded-xl text-gray-600 dark:text-gray-400 dark:text-stone-300 dark:hover:bg-stone-800 transition"
                  title={t("sidebar.newChat")}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    strokeWidth="0.1"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    className="w-5 h-5"
                  >
                    <path
                      d="M15.6729 3.91287C16.8918 2.69392 18.8682 2.69392 20.0871 3.91287C21.3061 5.13182 21.3061 7.10813 20.0871 8.32708L14.1499 14.2643C13.3849 15.0293 12.3925 15.5255 11.3215 15.6785L9.14142 15.9899C8.82983 16.0344 8.51546 15.9297 8.29289 15.7071C8.07033 15.4845 7.96554 15.1701 8.01005 14.8586L8.32149 12.6785C8.47449 11.6075 8.97072 10.615 9.7357 9.85006L15.6729 3.91287ZM18.6729 5.32708C18.235 4.88918 17.525 4.88918 17.0871 5.32708L11.1499 11.2643C10.6909 11.7233 10.3932 12.3187 10.3014 12.9613L10.1785 13.8215L11.0386 13.6986C11.6812 13.6068 12.2767 13.3091 12.7357 12.8501L18.6729 6.91287C19.1108 6.47497 19.1108 5.76499 18.6729 5.32708ZM11 3.99929C11.0004 4.55157 10.5531 4.99963 10.0008 5.00007C9.00227 5.00084 8.29769 5.00827 7.74651 5.06064C7.20685 5.11191 6.88488 5.20117 6.63803 5.32695C6.07354 5.61457 5.6146 6.07351 5.32698 6.63799C5.19279 6.90135 5.10062 7.24904 5.05118 7.8542C5.00078 8.47105 5 9.26336 5 10.4V13.6C5 14.7366 5.00078 15.5289 5.05118 16.1457C5.10062 16.7509 5.19279 17.0986 5.32698 17.3619C5.6146 17.9264 6.07354 18.3854 6.63803 18.673C6.90138 18.8072 7.24907 18.8993 7.85424 18.9488C8.47108 18.9992 9.26339 19 10.4 19H13.6C14.7366 19 15.5289 18.9992 16.1458 18.9488C16.7509 18.8993 17.0986 18.8072 17.362 18.673C17.9265 18.3854 18.3854 17.9264 18.673 17.3619C18.7988 17.1151 18.8881 16.7931 18.9393 16.2535C18.9917 15.7023 18.9991 14.9977 18.9999 13.9992C19.0003 13.4469 19.4484 12.9995 20.0007 13C20.553 13.0004 21.0003 13.4485 20.9999 14.0007C20.9991 14.9789 20.9932 15.7808 20.9304 16.4426C20.8664 17.116 20.7385 17.7136 20.455 18.2699C19.9757 19.2107 19.2108 19.9756 18.27 20.455C17.6777 20.7568 17.0375 20.8826 16.3086 20.9421C15.6008 21 14.7266 21 13.6428 21H10.3572C9.27339 21 8.39925 21 7.69138 20.9421C6.96253 20.8826 6.32234 20.7568 5.73005 20.455C4.78924 19.9756 4.02433 19.2107 3.54497 18.2699C3.24318 17.6776 3.11737 17.0374 3.05782 16.3086C2.99998 15.6007 2.99999 14.7266 3 13.6428V10.3572C2.99999 9.27337 2.99998 8.39922 3.05782 7.69134C3.11737 6.96249 3.24318 6.3223 3.54497 5.73001C4.02433 4.7892 4.78924 4.0243 5.73005 3.54493C6.28633 3.26149 6.88399 3.13358 7.55735 3.06961C8.21919 3.00673 9.02103 3.00083 9.99922 3.00007C10.5515 2.99964 10.9996 3.447 11 3.99929Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
              )}
              <LanguageToggle />
              <ThemeToggle />
              <UserMenu onShowProfile={() => setShowProfileModal(true)} />
            </div>
          </header>

          {/* Main Content */}
          {activeTab === "chat" ? (
            <>
              {/* Messages */}
              <main
                ref={messagesContainerRef}
                onScroll={handleScroll}
                className="relative flex-1 overflow-y-auto overflow-x-hidden min-h-0 overscroll-contain pb-5"
                style={{ WebkitOverflowScrolling: "touch" }}
              >
                {/* Session loading indicator - only show when switching sessions (no messages yet) */}
                {isLoading && messages.length === 0 && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm">
                    <div className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded-full bg-gray-400 dark:bg-stone-500 animate-[bounce_1s_ease-in-out_infinite]" />
                      <div className="h-2 w-2 rounded-full bg-gray-400 dark:bg-stone-500 animate-[bounce_1s_ease-in-out_0.1s_infinite]" />
                      <div className="h-2 w-2 rounded-full bg-gray-400 dark:bg-stone-500 animate-[bounce_1s_ease-in-out_0.2s_infinite]" />
                    </div>
                  </div>
                )}
                {messages.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center px-4 py-8">
                    {/* Title */}
                    <div className="flex items-center gap-3 mb-7 sm:mb-9">
                      <h1 className="text-3xl sm:text-4xl font-semibold text-gray-700 dark:text-stone-200">
                        LambChat
                      </h1>
                    </div>

                    {/* Suggestion Cards */}
                    <div className="w-full max-w-lg space-y-3 px-4">
                      {(
                        settings?.settings.frontend.find(
                          (s) => s.key === "WELCOME_SUGGESTIONS",
                        )?.value as
                          | Array<{ icon: string; text: string }>
                          | undefined
                      )?.map((suggestion) => (
                        <button
                          key={suggestion.text}
                          onClick={() => sendMessage(suggestion.text)}
                          className="w-full flex items-center gap-3 rounded-xl border border-gray-200 dark:border-stone-700 px-4 py-3 text-left text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-800 transition-colors"
                        >
                          <span className="text-lg">{suggestion.icon}</span>
                          <span>{suggestion.text}</span>
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 sm:mt-6 flex items-center gap-2 text-xs text-gray-400 dark:text-stone-500">
                      <span className="font-medium">LambChat</span>
                      {versionInfo?.app_version && (
                        <>
                          <span>·</span>
                          <span>v{versionInfo.app_version}</span>
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="dark:divide-stone-800">
                    {messages.map((message) => (
                      <ChatMessage
                        key={message.id}
                        message={message}
                        sessionId={sessionId ?? undefined}
                        sessionName={sessionName ?? undefined}
                        runId={currentRunId ?? undefined}
                      />
                    ))}
                    {/* Session feedback - using per-message ratings instead */}

                    <div ref={messagesEndRef} />
                  </div>
                )}
              </main>

              {/* Scroll to bottom button - Show when user is not at bottom and messages exist */}
              {messages.length > 0 && !isNearBottom && (
                <button
                  onClick={() => {
                    messagesEndRef.current?.scrollIntoView({
                      behavior: "smooth",
                    });
                    setTimeout(() => checkIfNearBottom(), 100);
                  }}
                  className="absolute left-1/2 -translate-x-1/2 z-50 flex items-center p-1.5 rounded-full bg-white/70 border border-gray-200 dark:border-none dark:bg-white/10 shadow-md hover:shadow-lg transition-all hover:scale-105"
                  style={{
                    bottom: "9rem",
                    left: "50%",
                    transform: "translateX(-50%)",
                  }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-5 h-5 text-stone-600 dark:text-stone-200"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}

              {/* Approval Panel - positioned above input */}
              <ApprovalPanel
                approvals={approvals}
                onRespond={respondToApproval}
                isLoading={approvalLoading}
              />

              {/* Input */}
              <ChatInput
                onSend={sendMessage}
                onStop={stopGeneration}
                isLoading={isLoading}
                canSend={canSendMessage}
                tools={tools}
                onToggleTool={toggleTool}
                onToggleCategory={toggleCategory}
                onToggleAll={toggleAll}
                toolsLoading={toolsLoading}
                enabledToolsCount={enabledToolsCount}
                totalToolsCount={totalToolsCount}
                enableMcp={enableMcp}
                skills={skills}
                onToggleSkill={toggleSkillWrapper}
                onToggleSkillCategory={toggleSkillCategory}
                onToggleAllSkills={toggleAllSkills}
                skillsLoading={skillsLoading}
                enabledSkillsCount={enabledSkillsCount}
                totalSkillsCount={totalSkillsCount}
                enableSkills={enableSkills}
                agentOptions={currentAgentOptions}
                agentOptionValues={agentOptionValues}
                onToggleAgentOption={handleToggleAgentOption}
              />
            </>
          ) : activeTab === "skills" ? (
            <main className="flex-1 overflow-hidden">
              <SkillsPanel />
            </main>
          ) : activeTab === "users" ? (
            <main className="flex-1 overflow-hidden">
              <UsersPanel />
            </main>
          ) : activeTab === "roles" ? (
            <main className="flex-1 overflow-hidden">
              <RolesPanel />
            </main>
          ) : activeTab === "settings" ? (
            <main className="flex-1 overflow-hidden">
              <SettingsPanel />
            </main>
          ) : activeTab === "mcp" ? (
            <main className="flex-1 overflow-hidden">
              <MCPPanel />
            </main>
          ) : activeTab === "feedback" ? (
            <main className="flex-1 overflow-hidden">
              <FeedbackPanel />
            </main>
          ) : null}
        </div>
      </div>
    </>
  );
}

// 404 Not Found Page
function NotFoundPage() {
  usePageTitle("404");
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-white dark:bg-stone-900 px-4">
      <div className="flex flex-col items-center max-w-md text-center">
        {/* Title */}
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-stone-100 mb-2">
          {t("errors.pageNotFound")}
        </h1>

        {/* Description */}
        <p className="text-gray-500 dark:text-stone-400 mb-8 leading-relaxed">
          {t("errors.pageNotFoundDesc")}
        </p>

        {/* Button */}
        <button
          onClick={() => navigate("/chat")}
          className="inline-flex items-center gap-2 px-6 py-4 bg-gray-900 dark:bg-stone-100 hover:bg-gray-800 dark:hover:bg-stone-200 text-white dark:text-stone-900 text-sm font-medium rounded-full transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
            className="size-5"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
            />
          </svg>
          {t("errors.backToHome")}
        </button>
      </div>
    </div>
  );
}

// Page Components
function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [sessionName, setSessionName] = useState<string | null>(null);

  // Fetch session name when sessionId changes
  useEffect(() => {
    if (!sessionId) {
      setSessionName(null);
      return;
    }

    const fetchSessionName = async () => {
      try {
        const session = await sessionApi.get(sessionId);
        if (session?.name) {
          setSessionName(session.name);
        } else {
          setSessionName(null);
        }
      } catch (err) {
        console.warn("[ChatPage] Failed to fetch session:", err);
        setSessionName(null);
      }
    };

    fetchSessionName();
  }, [sessionId]);

  // Use session name if available, otherwise use default "nav.chat"
  usePageTitle(sessionName || "nav.chat");

  return <AppContent activeTab="chat" />;
}

function SkillsPage() {
  usePageTitle("nav.skills");
  return <AppContent activeTab="skills" />;
}

function UsersPage() {
  usePageTitle("nav.users");
  return <AppContent activeTab="users" />;
}

function RolesPage() {
  usePageTitle("nav.roles");
  return <AppContent activeTab="roles" />;
}

function SettingsPage() {
  usePageTitle("nav.settings");
  return <AppContent activeTab="settings" />;
}

function MCPPage() {
  usePageTitle("nav.mcp");
  return <AppContent activeTab="mcp" />;
}

function FeedbackPage() {
  usePageTitle("nav.feedback");
  return <AppContent activeTab="feedback" />;
}

// App 入口 - 包含认证 Provider
function App() {
  const { t } = useTranslation();
  return (
    <ThemeProvider>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: "#333",
            color: "#fff",
          },
        }}
      />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route
          path="/chat/:sessionId?"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/skills"
          element={
            <ProtectedRoute
              permissions={[Permission.SKILL_READ]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <SkillsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/mcp"
          element={
            <ProtectedRoute
              permissions={[Permission.MCP_READ]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <MCPPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute
              permissions={[Permission.USER_READ]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/roles"
          element={
            <ProtectedRoute
              permissions={[Permission.ROLE_MANAGE]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <RolesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute
              permissions={[Permission.SETTINGS_MANAGE]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/feedback"
          element={
            <ProtectedRoute
              permissions={[Permission.FEEDBACK_READ]}
              redirectTo="/chat"
              showToast
              toastMessage={t("errors.noPermission")}
            >
              <FeedbackPage />
            </ProtectedRoute>
          }
        />
        {/* Public shared session page - no auth required */}
        <Route path="/shared/:shareId" element={<SharedPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ThemeProvider>
  );
}

export default App;
