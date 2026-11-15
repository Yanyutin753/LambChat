import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  LocalDevice,
  type PhoneControlState,
} from "../../services/capacitor/localDevice";
import { Button } from "../common/ui/Button";

export function PhoneControlSettings() {
  const { t } = useTranslation();
  const [state, setState] = useState<PhoneControlState>();
  const [pairPort, setPairPort] = useState("");
  const [connectPort, setConnectPort] = useState("");
  const [code, setCode] = useState("");
  const [background, setBackground] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setState(await LocalDevice.phoneState());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const visible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", visible);
    return () => document.removeEventListener("visibilitychange", visible);
  }, [refresh]);
  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError(false);
    try {
      await operation();
      await refresh();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  const port = (value: string) =>
    /^\d{1,5}$/.test(value) && Number(value) > 0 && Number(value) <= 65535;
  const inputClass =
    "w-full rounded-lg border border-theme-border bg-theme-bg px-3 py-2 text-13 text-theme-text";
  return (
    <section className="mt-4 space-y-3" aria-busy={busy}>
      <h4 className="text-13 font-medium text-theme-text">
        {t("profile.localSandbox.phoneControl")}
      </h4>
      <p className="text-12 text-theme-text-secondary">
        {t("profile.localSandbox.phoneControlHint")}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            void run(() => LocalDevice.phoneAction({ action: "accessibility" }))
          }
        >
          {t("profile.localSandbox.phoneAccessibility")}
        </Button>
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            void run(() => LocalDevice.phoneAction({ action: "debugging" }))
          }
        >
          {t("profile.localSandbox.phoneDebugging")}
        </Button>
        <Button size="sm" disabled={busy} onClick={() => void refresh()}>
          {t("common.refresh")}
        </Button>
      </div>
      <p role="status" className="text-12 text-theme-text-secondary">
        {t(
          state?.connected
            ? state.paused
              ? "profile.localSandbox.phonePaused"
              : "profile.localSandbox.phoneConnected"
            : "profile.localSandbox.phoneDisconnected",
        )}
        {state &&
          !state.accessibility &&
          ` · ${t("profile.localSandbox.phoneNeedsAccessibility")}`}
      </p>
      {!state?.connected && (
        <>
          <p className="text-12 text-theme-text-secondary">
            {t("profile.localSandbox.phonePairHint")}
          </p>
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const ports = await LocalDevice.phoneDiscover();
                if (ports.pairing.length === 1)
                  setPairPort(String(ports.pairing[0]));
                if (ports.connect.length === 1)
                  setConnectPort(String(ports.connect[0]));
              })
            }
          >
            {t("profile.localSandbox.phoneDiscover")}
          </Button>
          <label className="block text-12 text-theme-text-secondary">
            {t("profile.localSandbox.phonePairPort")}
            <input
              className={inputClass}
              inputMode="numeric"
              value={pairPort}
              maxLength={5}
              onChange={(event) => setPairPort(event.target.value)}
            />
          </label>
          <label className="block text-12 text-theme-text-secondary">
            {t("profile.localSandbox.phonePairCode")}
            <input
              className={inputClass}
              inputMode="numeric"
              autoComplete="off"
              type="password"
              value={code}
              maxLength={6}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <Button
            size="sm"
            disabled={busy || !port(pairPort) || !/^\d{6}$/.test(code)}
            onClick={() =>
              void run(async () => {
                const value = code;
                setCode("");
                await LocalDevice.phonePair({
                  port: Number(pairPort),
                  code: value,
                });
              })
            }
          >
            {t("profile.localSandbox.phonePair")}
          </Button>
          <label className="block text-12 text-theme-text-secondary">
            {t("profile.localSandbox.phoneConnectPort")}
            <input
              className={inputClass}
              inputMode="numeric"
              value={connectPort}
              maxLength={5}
              onChange={(event) => setConnectPort(event.target.value)}
            />
          </label>
          <label className="flex min-h-11 items-center gap-2 text-13 text-theme-text">
            <input
              type="checkbox"
              checked={background && state?.backgroundSupported !== false}
              disabled={state?.backgroundSupported === false}
              onChange={(event) => setBackground(event.target.checked)}
            />
            {t("profile.localSandbox.phoneBackground")}
          </label>
          <Button
            size="sm"
            disabled={busy || !port(connectPort) || !state?.accessibility}
            onClick={() =>
              void run(() =>
                LocalDevice.phoneConnect({
                  port: Number(connectPort),
                  background:
                    background && state?.backgroundSupported !== false,
                }),
              )
            }
          >
            {t("profile.localSandbox.phoneConnect")}
          </Button>
        </>
      )}
      {state?.connected && (
        <div className="flex flex-wrap gap-2">
          {(
            [
              state.paused ? "resume" : "pause",
              "takeover",
              "disconnect",
            ] as const
          ).map((action) => (
            <Button
              key={action}
              size="sm"
              disabled={busy}
              onClick={() =>
                void run(() => LocalDevice.phoneAction({ action }))
              }
            >
              {t(
                `profile.localSandbox.phone${action[0].toUpperCase()}${action.slice(
                  1,
                )}`,
              )}
            </Button>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="text-12 text-theme-text-secondary">
          {t("profile.localSandbox.phoneError")}
        </p>
      )}
    </section>
  );
}
