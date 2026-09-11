/**
 * 本地沙箱机器管理卡（多机 daemon）：机器列表（含离线机置灰保留）+
 * 默认机/重命名/忘记管理 + 当前连接的服务器地址展示。
 *
 * 离线机由服务端记忆层保留（online=False + last_seen）：灰点置灰展示 +
 * 相对最近在线时间 + 忘记按钮（在线机不可忘记，先断连）；在线机绿点。
 * 默认机是无会话级选择时的执行目标（服务端 resolve：默认机 → 唯一在线
 * → legacy）。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Check, Laptop, Link2, Pencil, Star, Trash2, X } from "lucide-react";
import { useSandboxStatus, notifySandboxStatusRefresh } from "../../hooks/useSandboxStatus";
import {
  machinePlatformLabel,
  sandboxApiMachines,
  type SandboxMachine,
} from "../../services/api/sandbox";
import { effectiveApiBase } from "../../services/api/serverConfig";

/** 相对最近在线时间：分钟/小时/天三档（i18n key 后缀分档）。 */
function relativeLastSeenKey(lastSeen: number | null | undefined): string {
  if (!lastSeen) return "";
  const elapsed = Math.max(0, Date.now() / 1000 - lastSeen);
  if (elapsed < 3600) return "minutes";
  if (elapsed < 86400) return "hours";
  return "days";
}

function isMachineOnline(machine: SandboxMachine): boolean {
  return machine.online !== false;
}

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

  const handleForget = async (machine: SandboxMachine) => {
    if (busy) return;
    if (!window.confirm(t("profile.localSandbox.forgetMachineConfirm", { name: machine.name }))) {
      return;
    }
    setBusy(true);
    try {
      await sandboxApiMachines.forgetMachine(machine.machine_id);
      notifySandboxStatusRefresh();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 border-t border-theme-border dark:border-stone-600/50 pt-3.5">
      <div className="flex items-center gap-1.5">
        <Laptop
          size={13}
          className="text-theme-text-tertiary dark:text-stone-500 shrink-0"
        />
        <span className="font-medium font-serif text-14 text-theme-text dark:text-stone-100">
          {t("profile.localSandbox.machines")}
        </span>
      </div>
      <p className="text-12 text-theme-text-secondary dark:text-stone-400 mt-1 leading-relaxed">
        {t("profile.localSandbox.machinesDesc")}
      </p>

      {/* 当前服务器：label-value 行（同设置行语言，mono 值右对齐截断）；
          运行时配置优先，构建期烘焙兜底 */}
      <div className="flex items-center justify-between gap-3 py-2.5">
        <span className="flex shrink-0 items-center gap-1.5 text-14 text-theme-text dark:text-stone-200">
          <Link2 size={13} className="opacity-50" />
          {t("profile.localSandbox.currentServer")}
        </span>
        <span
          className="min-w-0 truncate font-mono text-12 text-theme-text-secondary dark:text-stone-400"
          data-sandbox-server-url
        >
          {serverUrl}
        </span>
      </div>

      <div data-sandbox-machines-count={machines.length}>
        {online && machines.length === 0 && (
          <p className="py-1.5 text-12 text-theme-text-tertiary dark:text-stone-500">
            {t("profile.localSandbox.machinesEmpty")}
          </p>
        )}
        {machines.map((machine) => {
          const isDefault = machine.machine_id === defaultMachineId;
          const machineOnline = isMachineOnline(machine);
          const renaming = renamingId === machine.machine_id;
          const lastSeenKey = relativeLastSeenKey(machine.last_seen);
          return (
            <div
              key={machine.machine_id}
              className={`flex items-center gap-2 rounded-lg px-1.5 py-2 transition-colors hover:bg-theme-bg-subtle dark:hover:bg-stone-700/40 ${
                machineOnline ? "" : "opacity-60"
              }`}
              data-sandbox-machine={machine.machine_id}
            >
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${
                  machineOnline ? "bg-green-500" : "bg-theme-border-hover dark:bg-stone-600"
                }`}
              />
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
                    className="min-w-0 flex-1 rounded-md border border-amber-300 dark:border-amber-500/60 bg-theme-bg-card dark:bg-stone-800 px-2 py-1 text-14 text-theme-text dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
                  />
                  <button
                    type="button"
                    onClick={() => void submitRename()}
                    disabled={busy || !renameValue.trim()}
                    className="rounded-md p-1 text-theme-text-secondary hover:text-amber-500 disabled:opacity-40"
                    title={t("profile.localSandbox.renameSave")}
                  >
                    <Check size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setRenamingId(null)}
                    className="rounded-md p-1 text-theme-text-secondary hover:text-theme-text dark:hover:text-stone-300"
                    title={t("profile.localSandbox.renameCancel")}
                  >
                    <X size={13} />
                  </button>
                </span>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate text-14 font-medium text-theme-text dark:text-stone-100">
                    {machine.name}
                    {isDefault && (
                      <span className="ml-1.5 whitespace-nowrap rounded-full bg-amber-100 dark:bg-amber-500/15 px-1.5 py-0.5 text-10 font-medium text-amber-700 dark:text-amber-400">
                        {t("profile.localSandbox.defaultBadge")}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 whitespace-nowrap text-12 text-theme-text-secondary dark:text-stone-400">
                    {machinePlatformLabel(machine.platform, t)}
                    {machine.version ? ` · v${machine.version}` : ""}
                    {!machineOnline && (
                      <span className="ml-1.5 rounded-full bg-theme-border dark:bg-stone-700 px-1.5 py-0.5 text-10 font-medium text-theme-text-secondary dark:text-stone-400">
                        {t("profile.localSandbox.offlineBadge")}
                      </span>
                    )}
                    {!machineOnline && lastSeenKey && (
                      <span
                        className="ml-1.5 text-11 text-theme-text-tertiary dark:text-stone-500"
                        data-testid={`last-seen-${machine.machine_id}`}
                      >
                        {t(`profile.localSandbox.lastSeen.${lastSeenKey}`, {
                          minutes: Math.max(
                            1,
                            Math.round(
                              (Date.now() / 1000 - (machine.last_seen ?? 0)) / 60,
                            ),
                          ),
                          hours: Math.max(
                            1,
                            Math.round(
                              (Date.now() / 1000 - (machine.last_seen ?? 0)) / 3600,
                            ),
                          ),
                          days: Math.max(
                            1,
                            Math.round(
                              (Date.now() / 1000 - (machine.last_seen ?? 0)) / 86400,
                            ),
                          ),
                        })}
                      </span>
                    )}
                  </span>
                  {!machineOnline && (
                    <button
                      type="button"
                      onClick={() => void handleForget(machine)}
                      disabled={busy}
                      className="rounded-md p-1 text-theme-text-tertiary dark:text-stone-500 transition-colors hover:text-red-500 dark:hover:text-red-400 disabled:opacity-50"
                      title={t("profile.localSandbox.forgetMachine")}
                      data-testid={`forget-${machine.machine_id}`}
                    >
                      <Trash2 size={12} className="opacity-70" />
                    </button>
                  )}
                  {machineOnline && !isDefault && (
                    <button
                      type="button"
                      onClick={() => void handleSetDefault(machine.machine_id)}
                      disabled={busy}
                      className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-12 text-theme-text-tertiary dark:text-stone-500 transition-colors hover:bg-amber-50 dark:hover:bg-amber-500/10 hover:text-amber-600 dark:hover:text-amber-400 disabled:opacity-50"
                      title={t("profile.localSandbox.setDefault")}
                    >
                      <Star size={11} />
                      {t("profile.localSandbox.setDefault")}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => startRename(machine)}
                    disabled={busy}
                    className="shrink-0 rounded-md p-1 text-theme-text-tertiary dark:text-stone-500 transition-colors hover:bg-theme-bg-subtle dark:hover:bg-stone-700/60 hover:text-theme-text dark:hover:text-stone-200 disabled:opacity-50"
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
