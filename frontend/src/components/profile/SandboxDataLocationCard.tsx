import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { HardDrive, RotateCw } from "lucide-react";
import { relaunch } from "@tauri-apps/plugin-process";
import { usePreferenceWrites } from "../../hooks/usePreferenceWrites";
import { CatalogStatus } from "../common/CatalogStatus";
import { Button } from "../common/ui/Button";
import {
  clearSandboxDataLocation,
  pickSandboxDirectory,
  readSandboxDataLocation,
  setSandboxDataLocation,
  type SandboxDataLocation,
} from "../../services/tauri/sandboxShell";

/** Native data location: pick, confirm migration, then restart to fully apply. */
export function SandboxDataLocationCard() {
  const { t } = useTranslation();
  const sectionRef = useRef<HTMLDivElement>(null);
  const locationError = useRef("");
  const [location, setLocation] = useState<SandboxDataLocation | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [migrate, setMigrate] = useState(true);
  const [pendingRestart, setPendingRestart] = useState<"set" | "reset" | null>(
    null,
  );
  const { states, save, retry, discard } = usePreferenceWrites(
    "sandbox-data-location",
  );
  const applying = states.location === "saving";
  const picking = states.pick === "saving";
  const restarting = states.relaunch === "saving";

  useEffect(() => {
    let next: SandboxDataLocation;
    save(
      "read",
      async () => {
        next = await readSandboxDataLocation();
      },
      () => setLocation(next),
    );
  }, [save]);

  const focusSection = () => {
    if (sectionRef.current?.contains(document.activeElement)) {
      sectionRef.current.focus({ preventScroll: true });
    }
  };
  const handlePick = () => {
    if (applying || pendingRestart || !discard("location")) return;
    let picked: string | null;
    if (
      save(
        "pick",
        async () => {
          picked = await pickSandboxDirectory();
        },
        () => {
          if (picked) {
            discard("location");
            setConfirming(picked);
            setMigrate(true);
          }
        },
      )
    )
      focusSection();
  };
  const handleApply = () => {
    if (!confirming || pendingRestart) return;
    const path = confirming;
    if (
      save(
        "location",
        async () => {
          locationError.current = "";
          try {
            await setSandboxDataLocation(path, migrate);
          } catch (error) {
            locationError.current = String(error);
            throw error;
          }
        },
        () => {
          setPendingRestart("set");
          setConfirming(null);
          toast.success(
            t("profile.localSandbox.dataLocation.savedRestartPending"),
          );
        },
      )
    )
      focusSection();
  };
  const handleReset = () => {
    if (picking || pendingRestart || !discard("pick")) return;
    if (
      save(
        "location",
        async () => {
          locationError.current = "";
          try {
            await clearSandboxDataLocation();
          } catch (error) {
            locationError.current = String(error);
            throw error;
          }
        },
        () => {
          setPendingRestart("reset");
          toast.success(
            t("profile.localSandbox.dataLocation.resetRestartPending"),
          );
        },
      )
    )
      focusSection();
  };

  return (
    <div
      ref={sectionRef}
      tabIndex={-1}
      aria-busy={applying || picking || restarting || states.read === "saving"}
      className="profile-data-location border-t border-theme-border pt-3 mt-3 outline-none"
      data-sandbox-data-location
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-14 text-theme-text">
        <HardDrive
          size={14}
          className="shrink-0 text-theme-text-tertiary"
          aria-hidden="true"
        />
        <span>{t("profile.localSandbox.dataLocation.title")}</span>
        {location && (
          <span className="text-12 text-theme-text-secondary">
            {location.customized
              ? t("profile.localSandbox.dataLocation.customizedBadge")
              : t("profile.localSandbox.dataLocation.defaultBadge")}
          </span>
        )}
      </div>
      {location && (
        <p
          className="mt-1 text-12 text-theme-text-secondary [overflow-wrap:anywhere]"
          title={location.root}
        >
          {location.root}
        </p>
      )}
      <p className="mt-1 text-12 text-theme-text-secondary leading-relaxed">
        {t("profile.localSandbox.dataLocation.desc")}
      </p>

      {!location ? (
        <div className="mt-2">
          <CatalogStatus
            label={t("profile.localSandbox.dataLocation.title")}
            loading={states.read !== "error"}
            error={states.read === "error"}
            onRetry={() => retry("read")}
            focusTargetRef={sectionRef}
          />
        </div>
      ) : pendingRestart ? (
        <div className="mt-3 space-y-2">
          <p
            role="status"
            className="text-12 leading-relaxed text-theme-text-secondary"
          >
            {pendingRestart === "set"
              ? t("profile.localSandbox.dataLocation.savedRestartPending")
              : t("profile.localSandbox.dataLocation.resetRestartPending")}
          </p>
          <CatalogStatus
            label={t("profile.localSandbox.dataLocation.relaunchNow")}
            error={states.relaunch === "error"}
            errorText={t("common.operationFailed")}
            onRetry={() => retry("relaunch")}
            focusTargetRef={sectionRef}
          />
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={restarting}
              leftIcon={<RotateCw size={14} />}
              onClick={() => {
                if (save("relaunch", relaunch)) focusSection();
              }}
              data-sandbox-location-relaunch
            >
              {t("profile.localSandbox.dataLocation.relaunchNow")}
            </Button>
          </div>
        </div>
      ) : confirming ? (
        <div className="mt-3 space-y-2">
          <p
            className="text-12 text-theme-text [overflow-wrap:anywhere]"
            data-sandbox-location-selected
          >
            {t("profile.localSandbox.dataLocation.selected", {
              path: confirming,
            })}
          </p>
          <label className="flex min-h-11 items-center gap-2 text-12 text-theme-text-secondary cursor-pointer has-[:disabled]:cursor-default">
            <input
              type="checkbox"
              checked={migrate}
              disabled={applying}
              onChange={(e) => {
                if (discard("location")) setMigrate(e.target.checked);
              }}
              data-sandbox-location-migrate
              className="shrink-0 accent-[var(--theme-primary)]"
            />
            {t("profile.localSandbox.dataLocation.migrateLabel")}
          </label>
          <CatalogStatus
            label={t("profile.localSandbox.dataLocation.title")}
            error={states.location === "error"}
            errorText={`${t("common.operationFailed")} · ${locationError.current}`}
            onRetry={() => retry("location")}
            focusTargetRef={sectionRef}
          />
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={applying}
              onClick={() => {
                if (discard("location")) {
                  focusSection();
                  setConfirming(null);
                }
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={applying}
              onClick={handleApply}
              data-sandbox-location-apply
            >
              {migrate
                ? t("profile.localSandbox.dataLocation.confirmChange")
                : t("profile.localSandbox.dataLocation.confirmChangeNoMigrate")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <CatalogStatus
            label={t("profile.localSandbox.dataLocation.change")}
            error={states.pick === "error"}
            errorText={t("common.operationFailed")}
            onRetry={() => retry("pick")}
            focusTargetRef={sectionRef}
          />
          <CatalogStatus
            label={t("profile.localSandbox.dataLocation.reset")}
            error={states.location === "error"}
            errorText={`${t("common.operationFailed")} · ${locationError.current}`}
            onRetry={() => retry("location")}
            focusTargetRef={sectionRef}
          />
          <div className="flex flex-wrap items-center justify-end gap-2">
            {location.overrideConfigured && (
              <Button
                variant="ghost"
                size="sm"
                disabled={applying || picking}
                onClick={handleReset}
              >
                {t("profile.localSandbox.dataLocation.reset")}
              </Button>
            )}
            <Button
              size="sm"
              loading={picking}
              disabled={applying}
              onClick={handlePick}
              data-sandbox-location-change
            >
              {t("profile.localSandbox.dataLocation.change")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default SandboxDataLocationCard;
