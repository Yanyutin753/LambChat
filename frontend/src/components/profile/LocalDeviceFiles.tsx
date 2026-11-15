import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Upload, RotateCw } from "lucide-react";
import { LocalDevice } from "../../services/capacitor/localDevice";
import { Button } from "../common/ui/Button";
import { CatalogStatus } from "../common/CatalogStatus";

/** Shared phone files use the same /workspace/.shared path as desktop tasks. */
export function LocalDeviceFiles() {
  const { t } = useTranslation();
  const section = useRef<HTMLDivElement>(null);
  const [files, setFiles] = useState<{ name: string; size: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    setError(false);
    try {
      setFiles((await LocalDevice.listFiles()).files);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const transfer = async (name?: string) => {
    setBusy(true);
    setError(false);
    try {
      if (name) await LocalDevice.exportFile({ name });
      else await LocalDevice.importFile();
      setFiles((await LocalDevice.listFiles()).files);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div
      ref={section}
      tabIndex={-1}
      className="mt-3 space-y-2"
      aria-busy={busy}
    >
      <p className="text-12 text-theme-text-secondary">
        {t("profile.localSandbox.phoneFilesHint")}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          leftIcon={<Upload size={14} />}
          disabled={busy}
          onClick={() => void transfer()}
        >
          {t("profile.localSandbox.importPhoneFile")}
        </Button>
        <Button
          size="sm"
          leftIcon={<RotateCw size={14} />}
          disabled={busy}
          onClick={() => void refresh()}
        >
          {t("common.refresh")}
        </Button>
      </div>
      {(busy || error) && (
        <CatalogStatus
          focusTargetRef={section}
          label={t("profile.localSandbox.phoneFiles")}
          loading={busy}
          error={error}
          errorText={t("common.operationFailed")}
          onRetry={() => void refresh()}
        />
      )}
      {!busy && !error && files.length === 0 && (
        <p className="text-12 text-theme-text-secondary">
          {t("profile.localSandbox.phoneFilesEmpty")}
        </p>
      )}
      <ul className="max-h-48 overflow-y-auto">
        {files.map((file) => (
          <li key={file.name} className="flex min-w-0 items-center gap-2 py-1">
            <span className="min-w-0 flex-1 break-all text-12 text-theme-text">
              {file.name}
            </span>
            <Button
              size="sm"
              leftIcon={<Download size={14} />}
              disabled={busy}
              onClick={() => void transfer(file.name)}
              aria-label={`${t("common.download")} ${file.name}`}
            >
              {t("common.download")}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
