import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import {
  authApi,
  getRedirectPath,
  clearRedirectPath,
} from "../../services/api";
import { Button, Input } from "../common";
import { AuthLayout } from "./AuthLayout";
import { resolvePostAuthRedirectPath } from "./authRedirectTransition";

interface TwoFactorLoginProps {
  challenge: string;
  onSuccess?: (path?: string | null) => void;
  onCancel: () => void;
}

export function TwoFactorLogin({
  challenge,
  onSuccess,
  onCancel,
}: TwoFactorLoginProps) {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();
  const navigate = useNavigate();
  const id = useId();
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || expired) return;
    setBusy(true);
    setError("");
    try {
      await authApi.verifyTwoFactor(challenge, code.trim());
      setCode("");
      await refreshUser();
      const path = resolvePostAuthRedirectPath(getRedirectPath());
      clearRedirectPath();
      if (onSuccess) onSuccess(path);
      else navigate(path, { replace: true });
    } catch (err) {
      setCode("");
      setError((err as Error).message);
      if ((err as { code?: string }).code === "two_factor_expired")
        setExpired(true);
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <form
        className="space-y-5 text-theme-text"
        aria-busy={busy}
        onSubmit={handleSubmit}
      >
        <h1 className="text-24 font-semibold">{t("twoFactor.title")}</h1>
        <p className="text-14 text-theme-text-secondary">
          {t(recovery ? "twoFactor.recoveryHint" : "twoFactor.loginHint")}
        </p>
        <div className="space-y-2">
          <label htmlFor={id} className="block text-14">
            {t(recovery ? "twoFactor.recoveryCode" : "twoFactor.code")}
          </label>
          <Input
            id={id}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode={recovery ? "text" : "numeric"}
            autoComplete="one-time-code"
            autoFocus
            maxLength={recovery ? 64 : 6}
            required
            disabled={busy || expired}
            aria-describedby={error ? `${id}-error` : undefined}
            error={!!error}
          />
        </div>
        {error && (
          <p
            id={`${id}-error`}
            role="alert"
            className="text-14 text-theme-error [overflow-wrap:anywhere]"
          >
            {error}
          </p>
        )}
        <Button
          type="submit"
          variant="primary"
          loading={busy}
          disabled={expired || !code.trim()}
          className="w-full"
        >
          {t("twoFactor.verify")}
        </Button>
        <Button
          variant="ghost"
          disabled={busy || expired}
          onClick={() => {
            setRecovery(!recovery);
            setCode("");
            setError("");
          }}
          className="w-full"
        >
          {t(recovery ? "twoFactor.useAuthenticator" : "twoFactor.useRecovery")}
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={onCancel}
          className="w-full"
        >
          {t("auth.backToLogin")}
        </Button>
      </form>
    </AuthLayout>
  );
}
