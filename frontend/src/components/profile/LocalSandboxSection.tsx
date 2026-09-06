import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "react-hot-toast";
import {
  Monitor,
  FolderOpen,
  Link2Off,
  RotateCw,
  Download,
} from "lucide-react";
import { sandboxApi } from "../../services/api/sandbox";
import { getAccessToken } from "../../services/api/token";
import { effectiveApiBase } from "../../services/api/serverConfig";
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
  clearPairing,
  readPairingPat,
  writeConfirmPolicy,
} from "../../services/tauri/sandboxShell";
import { SkeletonLine } from "../skeletons";
import { SelectRow } from "./SelectRow";
import { SandboxMachinesCard } from "./SandboxMachinesCard";

const PROCESS_POLL_INTERVAL_MS = 10 * 1000;

const CONFIRM_POLICY_OPTIONS = [
  { key: "all", labelKey: "profile.localSandbox.policyOptions.all" },
  { key: "commands", labelKey: "profile.localSandbox.policyOptions.commands" },
  { key: "none", labelKey: "profile.localSandbox.policyOptions.none" },
] as const;

type ConfirmPolicy = (typeof CONFIRM_POLICY_OPTIONS)[number]["key"];

/** daemon 连接的服务端地址：运行时配置（打包壳首启设置）优先，构建期
 * API_BASE 次之；同源部署回退 origin。 */
function resolveServerUrl(): string {
  return (
    effectiveApiBase() ||
    (typeof window !== "undefined" ? window.location.origin : "")
  );
}

/**
 * 设置页"本地沙箱"分区。
 *
 * 动态适配：纯 web 在 daemon 在线（桌面端已配对连接）时渲染状态行 +
 * 机器列表（会话里可选本地档与执行机器），离线时渲染配对引导提示；
 * 壳内按配对态渲染状态行 + 配对表单（无副作用 login → 铸 PAT →
 * savePairing → restartDaemon）或策略/目录/重启/取消配对控制行。
 *
 * ``embedded``：嵌入"沙箱"合并卡渲染——去掉自带卡片壳，只留分区头与
 * 内容（分区之间用 hairline 分隔，不叠 tile 夹层）；独立渲染（默认）
 * 保持原卡片形态供测试直接引用。
 *
 * 凭据纪律（M4 T7）：配对登录直连 fetch（不 setTokens、不派发 auth:login，
 * 换账号配对不切换壳会话身份）；策略切换只写配置不重铸 PAT；取消配对用
 * 落盘 PAT 调服务端自删端点精准吊销后清理本地凭据。
 */
export function LocalSandboxSection({
  embedded = false,
}: {
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const shell = isShellAvailable();
  const { status, statusError, online, refresh } = useSandboxStatus();
  const [processStatus, setProcessStatus] = useState("");
  const [policy, setPolicy] = useState<ConfirmPolicy>("all");
  const [policyOpen, setPolicyOpen] = useState(false);
  const [pairing, setPairing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [unpairing, setUnpairing] = useState(false);
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

  // 策略显示跟随 daemon 上报值（写配置→重启→新 hello 上报→status 刷新闭环）；
  // 用户正在切换（policyOpen/applying）时不回写，避免覆盖在途选择
  const reportedPolicy = status?.daemon_confirm_policy;
  useEffect(() => {
    if (
      reportedPolicy &&
      !policyOpen &&
      !applying &&
      reportedPolicy !== policy &&
      CONFIRM_POLICY_OPTIONS.some((o) => o.key === reportedPolicy)
    ) {
      setPolicy(reportedPolicy as ConfirmPolicy);
    }
  }, [reportedPolicy, policyOpen, applying, policy]);

  // 未配对判定：daemon 进程退出/不可用（未配对时 daemon 启动即退），
  // 或会话已失效（status 401）——两者都回到配对表单
  const unpaired =
    processStatus === "stopped" ||
    processStatus === "unsupported" ||
    statusError === "unauthorized";
  const loading = processStatus === "";

  // 登录即配对（自动，每挂载一次）：未配对且 daemon 停止时——
  // - 已有落盘 PAT：直接拉起 daemon（配对数据还在，只是进程没起来——
  //   例如壳启动时 sidecar 缺失/版本门拒连后的恢复）；
  // - 无 PAT：用壳会话 JWT 铸 PAT 自动配对（同账号；换账号配对仍走表单）。
  // 任何失败静默回落配对表单，不循环重试。
  const autoPairHandled = useRef(false);
  useEffect(() => {
    if (
      !shell ||
      loading ||
      !unpaired ||
      unpairing ||
      autoPairHandled.current
    ) {
      return;
    }
    autoPairHandled.current = true;
    (async () => {
      try {
        const existingPat = await readPairingPat().catch(() => null);
        if (existingPat) {
          await restartDaemon();
          notifySandboxStatusRefresh();
          refresh();
          refreshProcessStatus();
          return;
        }
        const sessionJwt = getAccessToken();
        if (!sessionJwt) return;
        const pat = await sandboxApi.createPairingPat(sessionJwt);
        await applyPatAndRestart(pat.token, pat.pat_id, policy);
      } catch (err) {
        console.warn("[LocalSandboxSection] auto pair failed:", err);
      }
    })();
    // applyPatAndRestart/refresh/refreshProcessStatus 每渲染重建；
    // autoPairHandled 保证只执行一次，依赖收窄不会漏触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell, loading, unpaired, unpairing]);

  // 分区头：独立形态是卡片大标题（同其他卡）；嵌入形态是 tile 内的软标题
  // （同通知页 h4 语言），带一句说明文案
  const header = embedded ? (
    <>
      <div className="flex items-center gap-1.5">
        <Monitor
          size={13}
          className="text-stone-400 dark:text-stone-500 shrink-0"
        />
        <span className="font-medium font-serif text-sm text-stone-900 dark:text-stone-100">
          {t("profile.localSandbox.title")}
        </span>
      </div>
      <p className="text-xs text-stone-500 dark:text-stone-400 mt-1 leading-relaxed">
        {t("profile.localSandbox.desc")}
      </p>
    </>
  ) : (
    <div className="flex items-center gap-2 mb-3">
      <Monitor size={13} className="text-amber-500 dark:text-amber-400" />
      <h3 className="text-12 font-semibold font-serif uppercase tracking-wider text-stone-400 dark:text-stone-500">
        {t("profile.localSandbox.title")}
      </h3>
    </div>
  );

  if (!shell) {
    // 纯 web：daemon 在线（桌面端/CLI 已配对连接）→ 状态行 + 机器列表；
    // 离线 → 配对引导；首帧状态未回 → 骨架（不闪现引导提示）
    const statusLoading = status === null && statusError === null;
    const webBody = (
      <>
        {header}
        <div className={embedded ? "mt-2 space-y-0" : "space-y-0"}>
          {statusLoading ? (
            <SkeletonLine width="w-full" />
          ) : online ? (
            <>
              <div className="flex w-full items-center justify-between gap-2 py-3 first:pt-2 last:pb-0 text-left">
                <span className="flex min-w-0 items-center gap-2 text-sm text-stone-700 dark:text-stone-200">
                  <span
                    className="h-2 w-2 rounded-full shrink-0 bg-green-500"
                    data-sandbox-online={online}
                  />
                  {t("profile.localSandbox.statusOnline")}
                  {status?.daemon_version && (
                    <span className="truncate text-xs text-stone-500 dark:text-stone-400">
                      {t("profile.localSandbox.version", {
                        version: status.daemon_version,
                      })}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-stone-500 dark:text-stone-400">
                  {t("profile.localSandbox.webManaged")}
                </span>
              </div>
              {/* 多机管理在 web 同样可用（纯 API：列表/默认机/重命名） */}
              <SandboxMachinesCard />
            </>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-stone-500 dark:text-stone-400">
                {t("profile.localSandbox.needDesktop")}
              </p>
              {/* 离线引导：跳站内下载页（桌面端/daemon 安装包 + 配对教程） */}
              <button
                type="button"
                onClick={() => navigate("/download")}
                data-sandbox-download-cta
                className="flex items-center justify-center gap-1.5 w-full rounded-xl bg-amber-500 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600"
              >
                <Download size={13} />
                {t("profile.localSandbox.downloadCta")}
              </button>
            </div>
          )}
        </div>
      </>
    );
    if (embedded) {
      return (
        <div className="mt-3 border-t border-stone-200/70 dark:border-stone-600/50 pt-3.5">
          {webBody}
        </div>
      );
    }
    return (
      <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
        {webBody}
      </div>
    );
  }

  const applyPatAndRestart = async (
    pat: string,
    patId: string,
    confirmPolicy: ConfirmPolicy,
  ) => {
    await savePairing({
      serverUrl: resolveServerUrl(),
      pat,
      patId,
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
      // 无副作用登录：直连 fetch 拿 access_token，不 setTokens、不派发
      // auth:login（换账号配对不得切换壳会话身份），JWT 只活在本次闭包里。
      const pairingJwt = await sandboxApi.pairingLogin({
        username: username.trim(),
        password,
      });
      // 用配对账号的 JWT（而非壳会话 token）铸 PAT，并保存配对回执 pat_id
      const pat = await sandboxApi.createPairingPat(pairingJwt);
      await applyPatAndRestart(pat.token, pat.pat_id, policy);
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
      // 只写配置：write_confirm_policy 仅覆写 confirm_policy（保留 pat 等其余
      // 字段），不重铸 PAT——旧实现每次切换铸一枚永久凭据，会无限累积。
      await writeConfirmPolicy(next);
      await restartDaemon();
      notifySandboxStatusRefresh();
      refresh();
      refreshProcessStatus();
    } catch (err) {
      console.warn("[LocalSandboxSection] policy change failed:", err);
      toast.error(t("common.operationFailed"));
    } finally {
      setApplying(false);
    }
  };

  const handleUnpair = async () => {
    if (unpairing) return;
    setUnpairing(true);
    try {
      // 服务端自撤销：用落盘 PAT 调 DELETE /api/auth/pat/current 删自己；
      // 失败（已吊销/离线）不阻塞本地清理——残留 PAT 可在网页端 PAT 管理页吊销。
      const storedPat = await readPairingPat();
      if (storedPat) {
        try {
          await sandboxApi.revokePairingPat(storedPat);
        } catch (err) {
          console.warn(
            "[LocalSandboxSection] server-side PAT revoke failed:",
            err,
          );
        }
      }
      await clearPairing();
      notifySandboxStatusRefresh();
      refresh();
      refreshProcessStatus();
      toast.success(t("profile.localSandbox.unpaired"));
    } catch (err) {
      console.warn("[LocalSandboxSection] unpair failed:", err);
      toast.error(t("common.operationFailed"));
    } finally {
      setUnpairing(false);
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

  const body = (
    <>
      {header}

      <div className={embedded ? "mt-2 space-y-0" : "space-y-0"}>
        {/* 状态行：在线圆点 + daemon 版本 + 进程状态徽标 */}
        {loading ? (
          <SkeletonLine width="w-full" />
        ) : (
          <div className="flex w-full items-center justify-between gap-2 py-3 first:pt-2 last:pb-0 text-left">
            <span className="flex min-w-0 items-center gap-2 text-sm text-stone-700 dark:text-stone-200">
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
                <span className="truncate text-xs text-stone-500 dark:text-stone-400">
                  {t("profile.localSandbox.version", {
                    version: status.daemon_version,
                  })}
                </span>
              )}
            </span>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-10 font-medium ${
                processStatus === "running"
                  ? "bg-green-500/10 text-green-600 dark:text-green-400"
                  : "bg-stone-500/10 dark:bg-stone-500/20 text-stone-500 dark:text-stone-400"
              }`}
            >
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
              {pairing
                ? t("common.loading")
                : t("profile.localSandbox.pairButton")}
            </button>
          </form>
        ) : (
          <>
            {/* 确认策略：writeConfirmPolicy 只写配置后重启 daemon 生效（不重铸 PAT） */}
            <SelectRow
              label={t("profile.localSandbox.policy")}
              value={policy}
              options={CONFIRM_POLICY_OPTIONS}
              open={policyOpen}
              onToggle={() => setPolicyOpen((v) => !v)}
              onSelect={handlePolicyChange}
              loading={applying}
            />

            {/* 快捷操作：等宽三列，居中对齐（destructive 操作单独降级到下一行） */}
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => handleOpenLocalPath("workspaces")}
                className="flex items-center justify-center gap-1.5 rounded-xl border border-stone-200/80 dark:border-stone-500/70 px-2 py-2 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors hover:border-stone-300 dark:hover:border-stone-400/70 hover:bg-white dark:hover:bg-stone-800/70"
              >
                <FolderOpen size={12} className="shrink-0 opacity-60" />
                <span className="truncate">
                  {t("profile.localSandbox.openWorkspaces")}
                </span>
              </button>
              <button
                type="button"
                onClick={() => handleOpenLocalPath("audit")}
                className="flex items-center justify-center gap-1.5 rounded-xl border border-stone-200/80 dark:border-stone-500/70 px-2 py-2 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors hover:border-stone-300 dark:hover:border-stone-400/70 hover:bg-white dark:hover:bg-stone-800/70"
              >
                <FolderOpen size={12} className="shrink-0 opacity-60" />
                <span className="truncate">
                  {t("profile.localSandbox.openAudit")}
                </span>
              </button>
              <button
                type="button"
                onClick={handleRestart}
                className="flex items-center justify-center gap-1.5 rounded-xl border border-stone-200/80 dark:border-stone-500/70 px-2 py-2 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors hover:border-stone-300 dark:hover:border-stone-400/70 hover:bg-white dark:hover:bg-stone-800/70"
              >
                <RotateCw size={12} className="shrink-0 opacity-60" />
                <span className="truncate">
                  {t("profile.localSandbox.restartDaemon")}
                </span>
              </button>
            </div>

            {/* 取消配对：低强调 ghost，悬停才泛红——与日常操作组拉开间距，
                远离动线避免误触 */}
            <div className="mt-2.5 flex justify-end">
              <button
                type="button"
                onClick={handleUnpair}
                disabled={unpairing}
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-stone-400 dark:text-stone-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-50"
              >
                <Link2Off size={12} />
                {unpairing
                  ? t("common.loading")
                  : t("profile.localSandbox.unpair")}
              </button>
            </div>

            {/* 多机管理：在线机器列表 + 默认机/重命名 + 当前服务器地址 */}
            <SandboxMachinesCard />
          </>
        )}
      </div>
    </>
  );

  if (embedded) {
    return (
      <div className="mt-3 border-t border-stone-200/70 dark:border-stone-600/50 pt-3.5">
        {body}
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      {body}
    </div>
  );
}

// React.lazy 消费的默认导出（M4 T8 PWA 预算：设置页懒加载本分区）；
// 具名导出保留给既有测试直接引用。
export default LocalSandboxSection;
