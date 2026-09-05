/**
 * 本地沙箱机器管理卡（多机 daemon）：在线机器列表 + 默认机/重命名管理 +
 * 当前连接的服务器地址展示。
 *
 * 机器列表只含在线机（注册表 TTL 判活，离线机自然消失；rename 覆盖层在
 * 机器重连时自动恢复展示）。默认机是无会话级选择时的执行目标（服务端
 * resolve：默认机 → 唯一在线 → legacy）。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Check, Laptop, Link2, Pencil, Star, X } from "lucide-react";
import { useSandboxStatus, notifySandboxStatusRefresh } from "../../hooks/useSandboxStatus";
import {
  machinePlatformLabel,
  sandboxApiMachines,
  type SandboxMachine,
} from "../../services/api/sandbox";
import { effectiveApiBase } from "../../services/api/serverConfig";

export function SandboxMachinesCard() {
  const { t } = useTranslation();
  const { machines, defaultMachineId, online } = useSandboxStatus();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [busy, setBusy] = useState(false);

  const serverUrl = effectiveApiBase() || window.location.origin;

  const handleSetDefault = async (machineId: string) => {
    if (busy || machineId === defaultMachineId) return;
    setBusy(true);
    try {
      await sandboxApiMachines.setDefaultMachine(machineId);
      notifySandboxStatusRefresh();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startRename = (machine: SandboxMachine) => {
    setRenamingId(machine.machine_id);
    setRenameValue(machine.name);
  };

  const submitRename = async () => {
    if (!renamingId || busy) return;
    const name = renameValue.trim();
    if (!name) return;
    setBusy(true);
    try {
      await sandboxApiMachines.renameMachine(renamingId, name);
      setRenamingId(null);
      notifySandboxStatusRefresh();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 border-t border-stone-200/70 dark:border-stone-600/50 pt-3">
      <div className="flex items-center gap-1.5">
        <Laptop size={13} className="text-stone-400 dark:text-stone-500 shrink-0" />
        <span className="font-medium font-serif text-sm text-stone-900 dark:text-stone-100">
          {t("profile.localSandbox.machines")}
        </span>
      </div>
      <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 leading-relaxed">
        {t("profile.localSandbox.machinesDesc")}
      </p>

      {/* 当前服务器：配对/登录目标一目了然（运行时配置优先，构建期烘焙兜底） */}
      <div className="mt-2 flex items-center gap-1.5 text-xs text-stone-500 dark:text-stone-400">
        <Link2 size={12} className="opacity-50 shrink-0" />
        <span>{t("profile.localSandbox.currentServer")}</span>
        <span className="font-mono truncate" data-sandbox-server-url>
          {serverUrl}
        </span>
      </div>

      <div className="mt-1.5 space-y-0.5" data-sandbox-machines-count={machines.length}>
        {online && machines.length === 0 && (
          <p className="text-xs text-stone-400 dark:text-stone-500 py-1.5">
            {t("profile.localSandbox.machinesEmpty")}
          </p>
        )}
        {machines.map((machine) => {
          const isDefault = machine.machine_id === defaultMachineId;
          const renaming = renamingId === machine.machine_id;
          return (
            <div
              key={machine.machine_id}
              className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 transition-colors hover:bg-stone-100/70 dark:hover:bg-stone-700/40"
              data-sandbox-machine={machine.machine_id}
            >
              <span className="h-2 w-2 rounded-full bg-green-500 shrink-0" />
              {renaming ? (
                <span className="flex min-w-0 flex-1 items-center gap-1.5">
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submitRename();
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    className="min-w-0 flex-1 rounded-md border border-amber-300 dark:border-amber-500/60 bg-theme-bg-card dark:bg-stone-800 px-2 py-1 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
                  />
                  <button
                    type="button"
                    onClick={() => void submitRename()}
                    disabled={busy || !renameValue.trim()}
                    className="rounded-md p-1 text-stone-500 hover:text-amber-500 disabled:opacity-40"
                    title={t("profile.localSandbox.renameSave")}
                  >
                    <Check size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setRenamingId(null)}
                    className="rounded-md p-1 text-stone-500 hover:text-stone-700 dark:hover:text-stone-300"
                    title={t("profile.localSandbox.renameCancel")}
                  >
                    <X size={13} />
                  </button>
                </span>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate text-sm text-stone-800 dark:text-stone-100">
                    {machine.name}
                    {isDefault && (
                      <span className="ml-1.5 rounded-full bg-amber-100 dark:bg-amber-500/15 px-1.5 py-0.5 text-10 font-medium text-amber-700 dark:text-amber-400">
                        {t("profile.localSandbox.defaultBadge")}
                      </span>
                    )}
                    <span className="ml-1.5 text-xs text-stone-500 dark:text-stone-400">
                      {machinePlatformLabel(machine.platform, t)}
                      {machine.version ? ` · v${machine.version}` : ""}
                    </span>
                  </span>
                  {!isDefault && (
                    <button
                      type="button"
                      onClick={() => void handleSetDefault(machine.machine_id)}
                      disabled={busy}
                      className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-stone-500 dark:text-stone-400 transition-colors hover:text-amber-600 dark:hover:text-amber-400 disabled:opacity-50"
                      title={t("profile.localSandbox.setDefault")}
                    >
                      <Star size={12} className="opacity-70" />
                      {t("profile.localSandbox.setDefault")}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => startRename(machine)}
                    disabled={busy}
                    className="rounded-md p-1 text-stone-500 dark:text-stone-400 transition-colors hover:text-stone-700 dark:hover:text-stone-300 disabled:opacity-50"
                    title={t("profile.localSandbox.rename")}
                  >
                    <Pencil size={12} className="opacity-70" />
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
