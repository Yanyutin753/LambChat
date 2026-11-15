import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { LocalDevice } from "../../services/capacitor/localDevice";
import { Button } from "../common/ui/Button";

export function LocalDeviceOverlaySettings() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    setError(false);
    try {
      const state = await LocalDevice.overlayStatus();
      setEnabled(state.enabled && state.granted);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const change = async (value: boolean) => {
    setBusy(true);
    setError(false);
    try {
      const state = await LocalDevice.setOverlayEnabled({ enabled: value });
      setEnabled(state.enabled && state.granted);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-3 space-y-2" aria-busy={busy}>
      <label className="flex min-h-11 cursor-pointer items-center gap-2 text-13 text-theme-text">
        <input
          type="checkbox"
          checked={enabled}
          disabled={busy || error}
          onChange={(event) => void change(event.target.checked)}
        />
        {t("profile.localSandbox.overlay")}
      </label>
      <p className="text-12 text-theme-text-secondary">
        {t("profile.localSandbox.overlayHint")}
      </p>
      {error && (
        <div role="alert" className="text-12 text-theme-text-secondary">
          {t("common.operationFailed")}
          <Button size="sm" onClick={() => void refresh()}>
            {t("common.retry")}
          </Button>
        </div>
      )}
    </div>
  );
}
