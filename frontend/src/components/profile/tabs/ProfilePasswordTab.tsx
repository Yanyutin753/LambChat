import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, Check, AlertCircle } from "lucide-react";
import { authApi } from "../../../services/api";
import { Button, IconButton, Input } from "../../common";

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

  const passwordType = showPassword ? "text" : "password";
  const visibilityToggle = (
    <IconButton
      aria-label={t("profile.togglePasswordVisibility", "Toggle visibility")}
      icon={showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
      size="sm"
      onClick={() => setShowPassword(!showPassword)}
      className="text-theme-text-tertiary hover:text-theme-text-secondary dark:hover:text-stone-300"
    />
  );

  return (
    <div className="space-y-4">
      {passwordSuccess && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--theme-success)_10%,transparent)] dark:bg-green-900/30 text-theme-success dark:text-green-400 text-14">
          <Check size={16} className="shrink-0" />
          {t("profile.passwordChanged")}
        </div>
      )}

      {passwordError && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--theme-error)_10%,transparent)] dark:bg-red-900/30 text-theme-error dark:text-red-400 text-14">
          <AlertCircle size={16} className="shrink-0" />
          {passwordError}
        </div>
      )}

      {/* Old Password */}
      <div>
        <label className="block text-14 font-medium text-theme-text dark:text-stone-300 mb-1.5">
          {t("profile.oldPassword")}
        </label>
        <Input
          type={passwordType}
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
          placeholder={t("profile.oldPassword")}
          trailingSlot={visibilityToggle}
        />
      </div>

      {/* New Password */}
      <div>
        <label className="block text-14 font-medium text-theme-text dark:text-stone-300 mb-1.5">
          {t("profile.newPassword")}
        </label>
        <Input
          type={passwordType}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder={t("profile.newPassword")}
          trailingSlot={visibilityToggle}
        />
      </div>

      {/* Confirm Password */}
      <div>
        <label className="block text-14 font-medium text-theme-text dark:text-stone-300 mb-1.5">
          {t("profile.confirmPassword")}
        </label>
        <Input
          type={passwordType}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder={t("profile.confirmPassword")}
          trailingSlot={visibilityToggle}
        />
      </div>

      {/* Submit Button */}
      <Button
        variant="primary"
        onClick={handlePasswordChange}
        loading={isLoading}
        className="w-full"
      >
        {t("profile.changePassword")}
      </Button>
    </div>
  );
}
