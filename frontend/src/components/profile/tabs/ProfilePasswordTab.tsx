import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Loader2, Check, AlertCircle } from "lucide-react";
import { authApi } from "../../../services/api";

export function ProfilePasswordTab() {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

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

  return (
    <div className="space-y-4">
      {passwordSuccess && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 text-sm">
          <Check size={16} className="shrink-0" />
          {t("profile.passwordChanged")}
        </div>
      )}

      {passwordError && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-sm">
          <AlertCircle size={16} className="shrink-0" />
          {passwordError}
        </div>
      )}

      {/* Old Password */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1.5">
          {t("profile.oldPassword")}
        </label>
        <div className="relative">
          <input
            type={showPassword ? "text" : "password"}
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            className="w-full px-3.5 py-2.5 pr-10 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-sm"
            placeholder={t("profile.oldPassword")}
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-stone-300 transition-colors"
          >
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        </div>
      </div>

      {/* New Password */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1.5">
          {t("profile.newPassword")}
        </label>
        <input
          type={showPassword ? "text" : "password"}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-sm"
          placeholder={t("profile.newPassword")}
        />
      </div>

      {/* Confirm Password */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1.5">
          {t("profile.confirmPassword")}
        </label>
        <input
          type={showPassword ? "text" : "password"}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 dark:border-stone-600 bg-white dark:bg-stone-700 text-gray-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-sm"
          placeholder={t("profile.confirmPassword")}
        />
      </div>

      {/* Submit Button */}
      <button
        onClick={handlePasswordChange}
        disabled={isLoading}
        className="w-full py-2.5 px-4 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 dark:disabled:bg-amber-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"
      >
        {isLoading ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            {t("common.loading")}
          </>
        ) : (
          t("profile.changePassword")
        )}
      </button>
    </div>
  );
}
