import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { HardDrive, RotateCw } from "lucide-react";

import {
  clearSandboxDataLocation,
  pickSandboxDirectory,
  readSandboxDataLocation,
  setSandboxDataLocation,
  type SandboxDataLocation,
} from "../../services/tauri/sandboxShell";

/**
 * 设置页"沙箱数据位置"行（仅壳内渲染）：展示当前生效根（LAMBCHAT_HOME
 * 或缺省 ~/.lambchat）与自定义徽标；"更改位置"走原生目录选择 → 确认面板
 * （可选迁移现有数据）→ 保存壳级覆盖文件并停 daemon → 引导重启壳彻底
 * 生效（PBS 播种等启动期逻辑 relaunch 后才换根）。"恢复默认"删覆盖文件，
 * 数据留在原处不搬回。读取失败静默不渲染（不破坏设置页其余分区）。
 */
export function SandboxDataLocationCard() {
  const { t } = useTranslation();
  const [location, setLocation] = useState<SandboxDataLocation | null>(null);
  const [readable, setReadable] = useState(false);
  const [picking, setPicking] = useState(false);
  /** 待确认的新根（目录选择返回非空即进入确认面板） */
  const [confirming, setConfirming] = useState<string | null>(null);
  const [migrate, setMigrate] = useState(true);
  const [applying, setApplying] = useState(false);
  /** 已保存待重启："set" 更改 / "reset" 恢复默认 */
  const [pendingRestart, setPendingRestart] = useState<"set" | "reset" | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    readSandboxDataLocation()
      .then((next) => {
        if (cancelled) return;
        setLocation(next);
        setReadable(true);
      })
      .catch((err) => {
        console.warn("[SandboxDataLocationCard] read failed:", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePick = useCallback(async () => {
    if (picking) return;
    setPicking(true);
    try {
      const picked = await pickSandboxDirectory();
      if (picked) {
        setConfirming(picked);
        setMigrate(true);
      }
    } catch (err) {
      console.warn("[SandboxDataLocationCard] pick failed:", err);
    } finally {
      setPicking(false);
    }
  }, [picking]);

  const handleApply = useCallback(async () => {
    if (!confirming || applying) return;
    setApplying(true);
    try {
      await setSandboxDataLocation(confirming, migrate);
      setPendingRestart("set");
      setConfirming(null);
      toast.success(t("profile.localSandbox.dataLocation.savedRestartPending"));
    } catch (err) {
      console.warn("[SandboxDataLocationCard] set failed:", err);
      toast.error(String(err));
    } finally {
      setApplying(false);
    }
  }, [confirming, applying, migrate, t]);

  const handleReset = useCallback(async () => {
    if (applying || pendingRestart) return;
    setApplying(true);
    try {
      await clearSandboxDataLocation();
      setPendingRestart("reset");
      toast.success(
        t("profile.localSandbox.dataLocation.resetRestartPending"),
      );
    } catch (err) {
      console.warn("[SandboxDataLocationCard] reset failed:", err);
      toast.error(String(err));
    } finally {
      setApplying(false);
    }
  }, [applying, pendingRestart, t]);

  const handleRelaunch = useCallback(async () => {
    try {
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (err) {
      console.warn("[SandboxDataLocationCard] relaunch failed:", err);
      toast.error(t("common.operationFailed"));
    }
  }, [t]);

  if (!readable || !location) return null;

  const busy = applying || pendingRestart !== null;

  return (
    <div
      className="border-t border-theme-border dark:border-stone-600/50 pt-2.5 mt-2.5"
      data-sandbox-data-location
    >
      <div className="flex w-full items-center justify-between gap-2 text-left">
        <span className="flex min-w-0 items-center gap-2 text-14 text-theme-text dark:text-stone-200">
          <HardDrive
            size={13}
            className="shrink-0 text-theme-text-tertiary dark:text-stone-500"
          />
          {t("profile.localSandbox.dataLocation.title")}
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-10 font-medium ${
              location.customized
                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "bg-stone-500/10 dark:bg-stone-500/20 text-theme-text-secondary dark:text-stone-400"
            }`}
          >
            {location.customized
              ? t("profile.localSandbox.dataLocation.customizedBadge")
              : t("profile.localSandbox.dataLocation.defaultBadge")}
          </span>
        </span>
        <span
          className="shrink-0 max-w-[45%] truncate text-12 text-theme-text-secondary dark:text-stone-400"
          title={location.root}
        >
          {location.root}
        </span>
      </div>

      <p className="mt-1 text-12 text-theme-text-tertiary dark:text-stone-500 leading-relaxed">
        {t("profile.localSandbox.dataLocation.desc")}
      </p>

      {pendingRestart ? (
        <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-amber-500/5 border border-amber-500/20 px-3 py-2">
          <p className="min-w-0 text-12 text-theme-text-secondary dark:text-stone-400">
            {pendingRestart === "set"
              ? t("profile.localSandbox.dataLocation.savedRestartPending")
              : t("profile.localSandbox.dataLocation.resetRestartPending")}
          </p>
          <button
            type="button"
            onClick={handleRelaunch}
            data-sandbox-location-relaunch
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-amber-500 px-3 py-1.5 text-12 font-medium text-white transition-colors hover:bg-amber-600"
          >
            <RotateCw size={12} />
            {t("profile.localSandbox.dataLocation.relaunchNow")}
          </button>
        </div>
      ) : confirming ? (
        <div className="mt-2 space-y-2 rounded-xl border border-theme-border dark:border-stone-600/50 p-2.5">
          <p
            className="text-12 text-theme-text dark:text-stone-200 break-all"
            data-sandbox-location-selected
          >
            {t("profile.localSandbox.dataLocation.selected", {
              path: confirming,
            })}
          </p>
          <label className="flex items-center gap-2 text-12 text-theme-text-secondary dark:text-stone-400 cursor-pointer">
            <input
              type="checkbox"
              checked={migrate}
              onChange={(e) => setMigrate(e.target.checked)}
              data-sandbox-location-migrate
              className="accent-amber-500"
            />
            {t("profile.localSandbox.dataLocation.migrateLabel")}
          </label>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirming(null)}
              className="rounded-xl px-3 py-1.5 text-12 font-medium text-theme-text-secondary dark:text-stone-400 transition-colors hover:text-theme-text dark:hover:text-stone-200"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={handleApply}
              disabled={applying}
              data-sandbox-location-apply
              className="rounded-xl bg-amber-500 disabled:opacity-50 px-3 py-1.5 text-12 font-medium text-white transition-colors hover:bg-amber-600"
            >
              {applying
                ? t("common.loading")
                : migrate
                  ? t("profile.localSandbox.dataLocation.confirmChange")
                  : t("profile.localSandbox.dataLocation.confirmChangeNoMigrate")}
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex items-center justify-end gap-2">
          {location.overrideConfigured && (
            <button
              type="button"
              onClick={handleReset}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-12 text-theme-text-tertiary dark:text-stone-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-50"
            >
              {t("profile.localSandbox.dataLocation.reset")}
            </button>
          )}
          <button
            type="button"
            onClick={handlePick}
            disabled={busy || picking}
            data-sandbox-location-change
            className="flex items-center justify-center gap-1.5 rounded-xl border border-theme-border dark:border-stone-500/70 disabled:opacity-50 px-2.5 py-1.5 text-12 font-medium text-theme-text-secondary dark:text-stone-300 transition-colors hover:border-theme-border-hover dark:hover:border-stone-400/70 hover:bg-theme-bg-card dark:hover:bg-stone-800/70"
          >
            {picking
              ? t("common.loading")
              : t("profile.localSandbox.dataLocation.change")}
          </button>
        </div>
      )}
    </div>
  );
}

// React.lazy 消费的默认导出（设置页懒加载预算）；
// 具名导出保留给测试直接引用（同 LocalSandboxSection 约定）。
export default SandboxDataLocationCard;
