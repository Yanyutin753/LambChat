import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import QRCode from "qrcode";
import { useAuth } from "../../../hooks/useAuth";
import { authApi } from "../../../services/api";
import { copyToClipboard } from "../../../utils/clipboard";
import { Button, Input } from "../../common";

type Action = "setup" | "enable" | "disable" | "recovery-codes";

export function ProfileTwoFactorSection() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const id = useId();
  const [action, setAction] = useState<Action | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(
    null,
  );
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const operation = useRef(0);
  useEffect(
    () => () => {
      operation.current += 1;
    },
    [],
  );

  const reset = () => {
    operation.current += 1;
    setAction(null);
    setPassword("");
    setCode("");
    setSetup(null);
    setError("");
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !action) return;
    const current = ++operation.current;
    setBusy(true);
    setError("");
    try {
      if (action === "setup") {
        const result = await authApi.setupTwoFactor(password);
        const qr = await QRCode.toDataURL(result.otpauth_uri, {
          width: 240,
          margin: 2,
        });
        if (current !== operation.current) return;
        setSetup({ secret: result.secret, qr });
        setAction("enable");
      } else {
        const result = await authApi.updateTwoFactor(
          action,
          password,
          code.trim(),
        );
        if (current !== operation.current) return;
        reset();
        setCodes(result.recovery_codes);
        setCopied(false);
        await refreshUser();
      }
    } catch (err) {
      if (current === operation.current) {
        setError((err as Error).message);
        setCode("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="profile-section space-y-4 text-theme-text"
      aria-labelledby={`${id}-title`}
    >
      <div className="flex flex-wrap justify-between gap-2">
        <h3 id={`${id}-title`} className="profile-section-heading">
          {t("twoFactor.title")}
        </h3>
        <span className="text-14 text-theme-text-secondary">
          {t(
            user?.two_factor_enabled
              ? "twoFactor.enabled"
              : "twoFactor.disabled",
          )}
        </span>
      </div>
      <p className="text-14 text-theme-text-secondary">
        {t("twoFactor.description")}
      </p>
      <p className="text-12 text-theme-text-tertiary">
        {t("twoFactor.tokenNotice")}
      </p>
      {codes.length > 0 ? (
        <div className="space-y-3" role="status">
          <p className="text-14 font-medium">{t("twoFactor.saveCodes")}</p>
          <p className="text-12 text-theme-text-secondary">
            {t("twoFactor.saveCodesHint")}
          </p>
          <pre className="select-text whitespace-pre-wrap break-all rounded-lg bg-theme-bg-subtle p-3 text-14">
            {codes.join("\n")}
          </pre>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={async () => {
                try {
                  await copyToClipboard(codes.join("\n"));
                  setCopied(true);
                } catch {
                  setError(t("chat.message.copyFailed"));
                }
              }}
            >
              {t(copied ? "chat.message.copied" : "chat.message.copy")}
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setCodes([]);
                setCopied(false);
                setError("");
              }}
            >
              {t("twoFactor.savedCodes")}
            </Button>
          </div>
        </div>
      ) : action ? (
        <form className="space-y-3" aria-busy={busy} onSubmit={handleSubmit}>
          <p className="text-14 font-medium">
            {t(
              action === "disable"
                ? "twoFactor.disable"
                : action === "recovery-codes"
                  ? "twoFactor.regenerate"
                  : "twoFactor.pair",
            )}
          </p>
          {setup && (
            <div className="space-y-3">
              <p className="text-14 text-theme-text-secondary">
                {t("twoFactor.scanHint")}
              </p>
              <img
                src={setup.qr}
                alt={t("twoFactor.qrAlt")}
                width={240}
                height={240}
                className="max-w-full rounded-lg"
              />
              <p className="text-12 text-theme-text-secondary">
                {t("twoFactor.manualKey")}
              </p>
              <code className="block select-text break-all text-14">
                {setup.secret}
              </code>
            </div>
          )}
          <div className="space-y-1.5">
            <label htmlFor={`${id}-password`} className="block text-14">
              {t("auth.password")}
            </label>
            <Input
              id={`${id}-password`}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
              maxLength={1024}
            />
          </div>
          {action === "setup" && (
            <p className="text-12 text-theme-text-secondary">
              {t("twoFactor.passwordHint")}
            </p>
          )}
          {action !== "setup" && (
            <div className="space-y-1.5">
              <label htmlFor={`${id}-code`} className="block text-14">
                {t(
                  action === "enable"
                    ? "twoFactor.code"
                    : "twoFactor.codeOrRecovery",
                )}
              </label>
              <Input
                id={`${id}-code`}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                inputMode={action === "enable" ? "numeric" : "text"}
                required
                disabled={busy}
                maxLength={action === "enable" ? 6 : 64}
              />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant={action === "disable" ? "danger" : "primary"}
              loading={busy}
            >
              {t(
                action === "setup"
                  ? "twoFactor.pair"
                  : action === "enable"
                    ? "twoFactor.confirmEnable"
                    : action === "disable"
                      ? "twoFactor.confirmDisable"
                      : "twoFactor.confirmRegenerate",
              )}
            </Button>
            <Button disabled={busy} onClick={reset}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-2">
          {user?.two_factor_enabled ? (
            <>
              <Button
                onClick={() => {
                  reset();
                  setAction("recovery-codes");
                }}
              >
                {t("twoFactor.regenerate")}
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  reset();
                  setAction("disable");
                }}
              >
                {t("twoFactor.disable")}
              </Button>
            </>
          ) : (
            <Button
              onClick={() => {
                reset();
                setAction("setup");
              }}
            >
              {t("twoFactor.pair")}
            </Button>
          )}
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="text-14 text-theme-error [overflow-wrap:anywhere]"
        >
          {error}
        </p>
      )}
    </section>
  );
}
