import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Monitor, FolderOpen, RotateCw } from "lucide-react";
import { authApi } from "../../services/api/auth";
import {
  DESKTOP_SHELL_PAT_NAME,
  sandboxApi,
} from "../../services/api/sandbox";
import { API_BASE } from "../../services/api/config";
import {
  SANDBOX_STATUS_REFRESH_EVENT,
  notifySandboxStatusRefresh,
  useSandboxStatus,
} from "../../hooks/useSandboxStatus";
import {
  daemonProcessStatus,
  isShellAvailable,
  openLocalPath,
  restartDaemon,
  savePairing,
} from "../../services/tauri/sandboxShell";
import { SkeletonLine } from "../skeletons";
import { SelectRow } from "./SelectRow";

const PROCESS_POLL_INTERVAL_MS = 10 * 1000;

const CONFIRM_POLICY_OPTIONS = [
  { key: "all", labelKey: "profile.localSandbox.policyOptions.all" },
  { key: "commands", labelKey: "profile.localSandbox.policyOptions.commands" },
  { key: "none", labelKey: "profile.localSandbox.policyOptions.none" },
] as const;

type ConfirmPolicy = (typeof CONFIRM_POLICY_OPTIONS)[number]["key"];

/** daemon 连接的服务端地址：打包壳内 API_BASE 固定注入；同源部署回退 origin。 */
function resolveServerUrl(): string {
  return API_BASE || (typeof window !== "undefined" ? window.location.origin : "");
}

/**
 * 设置页"本地沙箱"分区。
 *
 * 动态适配：纯 web 只渲染"需要桌面端"提示；壳内按配对态渲染
 * 状态行 + 配对表单（login → PAT → savePairing → restartDaemon）
 * 或策略/目录/重启控制行。
 */
export function LocalSandboxSection() {
  const { t } = useTranslation();
  const shell = isShellAvailable();
  const { status, statusError, online, refresh } = useSandboxStatus();
  const [processStatus, setProcessStatus] = useState("");
  const [policy, setPolicy] = useState<ConfirmPolicy>("all");
  const [policyOpen, setPolicyOpen] = useState(false);
  const [pairing, setPairing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const refreshProcessStatus = useCallback(() => {
    daemonProcessStatus()
      .then((next) => setProcessStatus(next))
      .catch(() => setProcessStatus("stopped"));
  }, []);

  useEffect(() => {
    if (!shell) return;
    refreshProcessStatus();
    const timer = setInterval(refreshProcessStatus, PROCESS_POLL_INTERVAL_MS);
    window.addEventListener(SANDBOX_STATUS_REFRESH_EVENT, refreshProcessStatus);
    return () => {
      clearInterval(timer);
      window.removeEventListener(
        SANDBOX_STATUS_REFRESH_EVENT,
        refreshProcessStatus,
      );
    };
  }, [shell, refreshProcessStatus]);

  if (!shell) {
    return (
      <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
        <div className="flex items-center gap-2 mb-2">
          <Monitor size={15} className="text-amber-500 dark:text-amber-400" />
          <h3 className="font-semibold font-serif uppercase tracking-wide text-stone-400 dark:text-stone-500">
            {t("profile.localSandbox.title")}
          </h3>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400">
          {t("profile.localSandbox.needDesktop")}
        </p>
      </div>
    );
  }

  // 未配对判定：daemon 进程退出/不可用（未配对时 daemon 启动即退），
  // 或会话已失效（status 401）——两者都回到配对表单
  const unpaired =
    processStatus === "stopped" ||
    processStatus === "unsupported" ||
    statusError === "unauthorized";
  const loading = processStatus === "";

  const applyPatAndRestart = async (pat: string, confirmPolicy: ConfirmPolicy) => {
    await savePairing({
      serverUrl: resolveServerUrl(),
      pat,
      confirmPolicy,
    });
    await restartDaemon();
    notifySandboxStatusRefresh();
    refresh();
    refreshProcessStatus();
  };

  const handlePair = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pairing || !username.trim() || !password) return;
    setPairing(true);
    try {
      await authApi.login({ username: username.trim(), password });
      const pat = await sandboxApi.createPat(DESKTOP_SHELL_PAT_NAME);
      await applyPatAndRestart(pat.token, policy);
      toast.success(t("profile.localSandbox.paired"));
      setPassword("");
    } catch (err) {
      console.warn("[LocalSandboxSection] pairing failed:", err);
      toast.error(t("profile.localSandbox.pairFailed"));
    } finally {
      setPairing(false);
    }
  };

  const handlePolicyChange = async (next: ConfirmPolicy) => {
    setPolicy(next);
    setPolicyOpen(false);
    if (applying) return;
    setApplying(true);
    try {
      // savePairing 需要完整凭据：每次覆写配一枚新 PAT（旧 PAT 可在 PAT 列表吊销）
      const pat = await sandboxApi.createPat(DESKTOP_SHELL_PAT_NAME);
      await applyPatAndRestart(pat.token, next);
    } catch (err) {
      console.warn("[LocalSandboxSection] policy change failed:", err);
      toast.error(t("common.operationFailed"));
    } finally {
      setApplying(false);
    }
  };

  const handleRestart = async () => {
    try {
      await restartDaemon();
      notifySandboxStatusRefresh();
      refresh();
      refreshProcessStatus();
    } catch (err) {
      console.warn("[LocalSandboxSection] restart failed:", err);
      toast.error(t("common.operationFailed"));
    }
  };

  const handleOpenLocalPath = (logicalName: "workspaces" | "audit") => {
    openLocalPath(logicalName).catch((err) => {
      console.warn("[LocalSandboxSection] open path failed:", err);
      toast.error(t("common.operationFailed"));
    });
  };

  return (
    <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Monitor size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="font-semibold font-serif uppercase tracking-wide text-stone-400 dark:text-stone-500">
          {t("profile.localSandbox.title")}
        </h3>
      </div>

      <div className="space-y-0">
        {/* 状态行：在线圆点 + daemon 版本 + 进程状态 */}
        {loading ? (
          <SkeletonLine width="w-full" />
        ) : (
          <div className="flex w-full items-center justify-between py-3 first:pt-0 last:pb-0 text-left">
            <span className="flex items-center gap-2 text-sm text-stone-700 dark:text-stone-200">
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${
                  online ? "bg-green-500" : "bg-stone-400 dark:bg-stone-500"
                }`}
                data-sandbox-online={online}
              />
              {online
                ? t("profile.localSandbox.statusOnline")
                : t("profile.localSandbox.statusOffline")}
              {status?.daemon_version && (
                <span className="text-xs text-stone-500 dark:text-stone-400">
                  {t("profile.localSandbox.version", {
                    version: status.daemon_version,
                  })}
                </span>
              )}
            </span>
            <span className="text-xs text-stone-500 dark:text-stone-400">
              {processStatus === "running"
                ? t("profile.localSandbox.processRunning")
                : t("profile.localSandbox.processStopped")}
            </span>
          </div>
        )}

        {unpaired ? (
          <form onSubmit={handlePair} className="space-y-2 pt-2">
            <p className="text-xs text-stone-500 dark:text-stone-400">
              {t("profile.localSandbox.pairTitle")}
            </p>
            <input
              type="text"
              autoComplete="username"
              placeholder={t("auth.usernamePlaceholder")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-xl border border-stone-200 dark:border-stone-600 bg-theme-bg-card dark:bg-stone-800 px-3 py-2 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <input
              type="password"
              autoComplete="current-password"
              placeholder={t("auth.passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-stone-200 dark:border-stone-600 bg-theme-bg-card dark:bg-stone-800 px-3 py-2 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <button
              type="submit"
              disabled={pairing || !username.trim() || !password}
              className="w-full rounded-xl bg-amber-500 disabled:opacity-50 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600"
            >
              {pairing ? t("common.loading") : t("profile.localSandbox.pairButton")}
            </button>
          </form>
        ) : (
          <>
            {/* 确认策略：savePairing 覆写配置后重启 daemon 生效 */}
            <SelectRow
              label={t("profile.localSandbox.policy")}
              value={policy}
              options={CONFIRM_POLICY_OPTIONS}
              open={policyOpen}
              onToggle={() => setPolicyOpen((v) => !v)}
              onSelect={handlePolicyChange}
              loading={applying}
            />

            <div className="flex flex-wrap gap-2 pt-3">
              <button
                type="button"
                onClick={() => handleOpenLocalPath("workspaces")}
                className="flex items-center gap-1.5 rounded-xl border border-stone-200 dark:border-stone-600 px-3 py-1.5 text-xs text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
              >
                <FolderOpen size={12} className="opacity-50" />
                {t("profile.localSandbox.openWorkspaces")}
              </button>
              <button
                type="button"
                onClick={() => handleOpenLocalPath("audit")}
                className="flex items-center gap-1.5 rounded-xl border border-stone-200 dark:border-stone-600 px-3 py-1.5 text-xs text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
              >
                <FolderOpen size={12} className="opacity-50" />
                {t("profile.localSandbox.openAudit")}
              </button>
              <button
                type="button"
                onClick={handleRestart}
                className="flex items-center gap-1.5 rounded-xl border border-stone-200 dark:border-stone-600 px-3 py-1.5 text-xs text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
              >
                <RotateCw size={12} className="opacity-50" />
                {t("profile.localSandbox.restartDaemon")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
