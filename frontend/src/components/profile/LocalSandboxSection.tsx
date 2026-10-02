import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
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
import { sandboxApi, sandboxApiMachines } from "../../services/api/sandbox";
import { getValidAccessToken } from "../../services/api/tokenManager";
import { effectiveApiBase } from "../../services/api/serverConfig";
import { usePreferenceWrites } from "../../hooks/usePreferenceWrites";
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
  subscribeDaemonStatus,
  writeConfirmPolicy,
} from "../../services/tauri/sandboxShell";
import { CatalogStatus } from "../common/CatalogStatus";
import { Button } from "../common/ui/Button";
import { Input } from "../common/ui/Input";
import { FormField } from "../common/ui/FormField";
import { SelectRow } from "./SelectRow";
import { SandboxMachinesCard } from "./SandboxMachinesCard";
import { SandboxDataLocationCard } from "./SandboxDataLocationCard";

const PROCESS_POLL_INTERVAL_MS = 10 * 1000;

const CONFIRM_POLICY_OPTIONS = [
  { key: "all", labelKey: "profile.localSandbox.policyOptions.all" },
  { key: "commands", labelKey: "profile.localSandbox.policyOptions.commands" },
  { key: "none", labelKey: "profile.localSandbox.policyOptions.none" },
] as const;

type ConfirmPolicy = (typeof CONFIRM_POLICY_OPTIONS)[number]["key"];
type SandboxAction = "current" | "other" | "policy" | "restart" | "unpair";

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
 * 壳内按配对态渲染状态行 + 配对表单（一键：当前会话 JWT 铸 PAT——
 * OAuth 账号唯一可用路径；换账号：无副作用 login → 铸 PAT →
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
  const { status, statusError, online, refresh, currentMachineId } =
    useSandboxStatus();
  const [processStatus, setProcessStatus] = useState("");
  const [policy, setPolicy] = useState<ConfirmPolicy>("all");
  const [policyOpen, setPolicyOpen] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);
  const pairFormRef = useRef<HTMLFormElement>(null);
  const processRequest = useRef(0);
  const operationGeneration = useRef(0);
  const operationError = useRef("");
  const { states, save, retry, discard } = usePreferenceWrites("local-sandbox");
  const [action, setAction] = useState<SandboxAction | null>(null);
  const [pairPrepared, setPairPrepared] = useState(false);
  const [policyDraft, setPolicyDraft] = useState(false);
  const busy = states.native === "saving";
  const pairing = action === "other" && busy;
  const pairingCurrent = action === "current" && busy;
  const pairBusy = busy || pairPrepared;
  const unpairing = action === "unpair" && busy;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  useLayoutEffect(() => {
    const invalidate = () => {
      operationGeneration.current++;
    };
    return invalidate;
  }, []);

  const refreshProcessStatus = useCallback(() => {
    const request = ++processRequest.current;
    setProcessStatus((previous) => (previous === "error" ? "" : previous));
    daemonProcessStatus().then(
      (next) => {
        if (request === processRequest.current) setProcessStatus(next);
      },
      () => {
        if (request === processRequest.current) setProcessStatus("error");
      },
    );
  }, []);

  useEffect(() => {
    if (!shell) return;
    // 初始 invoke 一次对账 + 订阅壳的 sandbox-daemon-status 事件（启动/停止/
    // 意外退出/重启即推，替代原 10s 轮询——非壳/订阅失败回退轮询兜底）
    refreshProcessStatus();
    let cancelSubscription: (() => void) | null = null;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;
    const invalidateProcessRequest = () => {
      processRequest.current++;
    };
    void subscribeDaemonStatus((event) => {
      if (cancelled) return;
      invalidateProcessRequest();
      setProcessStatus(
        event.unsupported
          ? "unsupported"
          : event.running
            ? "running"
            : "stopped",
      );
    }).then(
      (cancel) => {
        if (cancelled) {
          cancel?.();
          return;
        }
        if (!cancel) {
          fallbackTimer = setInterval(
            refreshProcessStatus,
            PROCESS_POLL_INTERVAL_MS,
          );
        }
        cancelSubscription = cancel;
      },
      () => {
        if (!cancelled)
          fallbackTimer = setInterval(
            refreshProcessStatus,
            PROCESS_POLL_INTERVAL_MS,
          );
      },
    );
    const onRefresh = () => refreshProcessStatus();
    window.addEventListener(SANDBOX_STATUS_REFRESH_EVENT, onRefresh);
    return () => {
      cancelled = true;
      invalidateProcessRequest();
      cancelSubscription?.();
      if (fallbackTimer) clearInterval(fallbackTimer);
      window.removeEventListener(SANDBOX_STATUS_REFRESH_EVENT, onRefresh);
    };
  }, [shell, refreshProcessStatus]);

  // 策略显示跟随 daemon 上报值（写配置→重启→新 hello 上报→status 刷新闭环）；
  // 用户正在切换（policyOpen/applying）时不回写，避免覆盖在途选择
  const reportedPolicy = status?.daemon_confirm_policy;
  useEffect(() => {
    if (reportedPolicy === policy && policyDraft) {
      setPolicyDraft(false);
      return;
    }
    if (
      reportedPolicy &&
      !policyOpen &&
      !busy &&
      !policyDraft &&
      reportedPolicy !== policy &&
      CONFIRM_POLICY_OPTIONS.some((o) => o.key === reportedPolicy)
    ) {
      setPolicy(reportedPolicy as ConfirmPolicy);
    }
  }, [reportedPolicy, policyOpen, busy, policy, policyDraft]);

  // 未配对判定：daemon 进程退出/不可用（未配对时 daemon 启动即退），
  // 或会话已失效（status 401）——两者都回到配对表单
  const unpaired =
    (processStatus === "stopped" ||
      processStatus === "unsupported" ||
      statusError === "unauthorized") &&
    !(states.native && action !== "current" && action !== "other");
  const loading = processStatus === "";

  // 分区头：独立形态是卡片大标题（同其他卡）；嵌入形态是 tile 内的软标题
  // （同通知页 h4 语言），带一句说明文案
  const header = embedded ? (
    <>
      <div className="flex items-center gap-1.5">
        <Monitor
          size={13}
          className="text-theme-text-tertiary dark:text-stone-500 shrink-0"
        />
        <span className="font-medium text-14 text-theme-text dark:text-stone-100">
          {t("profile.localSandbox.title")}
        </span>
      </div>
      <p className="text-12 text-theme-text-secondary dark:text-stone-400 mt-1 leading-relaxed">
        {t("profile.localSandbox.desc")}
      </p>
    </>
  ) : (
    <div className="flex items-center gap-2 mb-3">
      <Monitor size={13} className="text-amber-500 dark:text-amber-400" />
      <h3 className="profile-section-heading font-serif">
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
          {statusLoading || statusError ? (
            <CatalogStatus
              label={t("profile.localSandbox.title")}
              loading={statusLoading}
              error={Boolean(statusError)}
              onRetry={refresh}
              focusTargetRef={sectionRef}
            />
          ) : online ? (
            <>
              <div className="flex w-full items-center justify-between gap-2 py-3 first:pt-2 last:pb-0 text-left">
                <span className="flex min-w-0 items-center gap-2 text-14 text-theme-text dark:text-stone-200">
                  <span
                    className="h-2 w-2 rounded-full shrink-0 bg-theme-success"
                    data-sandbox-online={online}
                  />
                  {t("profile.localSandbox.statusOnline")}
                  {status?.daemon_version && (
                    <span className="truncate text-12 text-theme-text-secondary dark:text-stone-400">
                      {t("profile.localSandbox.version", {
                        version: status.daemon_version,
                      })}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-12 text-theme-text-secondary dark:text-stone-400">
                  {t("profile.localSandbox.webManaged")}
                </span>
              </div>
              {/* 多机管理在 web 同样可用（纯 API：列表/默认机/重命名） */}
              <SandboxMachinesCard />
            </>
          ) : (
            <div className="space-y-2">
              <p className="text-12 text-theme-text-secondary dark:text-stone-400">
                {t("profile.localSandbox.needDesktop")}
              </p>
              {/* 离线引导：跳站内下载页（桌面端/daemon 安装包 + 配对教程） */}
              <Button
                variant="primary"
                className="w-full"
                leftIcon={<Download size={14} />}
                onClick={() => navigate("/download")}
                data-sandbox-download-cta
              >
                {t("profile.localSandbox.downloadCta")}
              </Button>
            </div>
          )}
        </div>
      </>
    );
    if (embedded) {
      return (
        <div
          ref={sectionRef}
          tabIndex={-1}
          className="local-sandbox-section mt-3 border-t border-theme-border pt-3 outline-none"
        >
          {webBody}
        </div>
      );
    }
    return (
      <div
        ref={sectionRef}
        tabIndex={-1}
        className="local-sandbox-section profile-section outline-none"
      >
        {webBody}
      </div>
    );
  }

  const startOperation = (
    nextAction: SandboxAction,
    request: (isCurrent: () => boolean) => Promise<void>,
    onSaved?: () => void,
    errorText: () => string = () => t("common.operationFailed"),
  ) => {
    const generation = operationGeneration.current;
    const isCurrent = () => generation === operationGeneration.current;
    const accepted = save(
      "native",
      async () => {
        try {
          await request(isCurrent);
        } catch (error) {
          if (isCurrent()) {
            operationError.current = errorText();
            toast.error(operationError.current);
          }
          throw error;
        }
      },
      () => {
        notifySandboxStatusRefresh();
        refresh();
        refreshProcessStatus();
        onSaved?.();
      },
    );
    if (accepted) {
      setAction(nextAction);
      operationError.current = "";
      if (sectionRef.current?.contains(document.activeElement)) {
        const target =
          nextAction === "current" || nextAction === "other"
            ? pairFormRef.current
            : sectionRef.current;
        target?.focus({ preventScroll: true });
      }
    }
    return accepted;
  };

  const startPairing = (mode: "current" | "other") => {
    if (pairBusy || (mode === "other" && (!username.trim() || !password)))
      return;
    const credentials = { username: username.trim(), password };
    const confirmPolicy = policy;
    const serverUrl = resolveServerUrl();
    let receipt:
      Awaited<ReturnType<typeof sandboxApi.createPairingPat>> | undefined;
    let saved = false;
    let message = t("profile.localSandbox.pairFailed");
    startOperation(
      mode,
      async (isCurrent) => {
        if (!receipt) {
          const jwt =
            mode === "current"
              ? await getValidAccessToken()
              : await sandboxApi.pairingLogin(credentials);
          if (!isCurrent()) return;
          if (!jwt) {
            message = t("profile.localSandbox.pairNeedLogin");
            throw new Error("Pairing requires a signed-in account");
          }
          receipt = await sandboxApi.createPairingPat(jwt);
          if (!isCurrent()) return;
          if (pairFormRef.current?.contains(document.activeElement))
            sectionRef.current?.focus({ preventScroll: true });
          setPairPrepared(true);
          message = t("common.operationFailed");
        }
        if (!saved) {
          await savePairing({
            serverUrl,
            pat: receipt.token,
            patId: receipt.pat_id,
            confirmPolicy,
          });
          saved = true;
          if (!isCurrent()) return;
          message = t("profile.localSandbox.pairSavedRestartPending");
        }
        if (!isCurrent()) return;
        await restartDaemon();
      },
      () => {
        setPairPrepared(false);
        setPassword("");
        toast.success(t("profile.localSandbox.paired"));
      },
      () => message,
    );
  };

  const handlePair = (event: React.FormEvent) => {
    event.preventDefault();
    startPairing("other");
  };
  const handlePairWithCurrentAccount = () => startPairing("current");

  const handlePolicyChange = (next: ConfirmPolicy) => {
    if (busy || pairPrepared) return;
    const machineId = currentMachineId;
    let serverSaved = false;
    let localSaved = false;
    if (
      startOperation("policy", async (isCurrent) => {
        // Retry resumes the failed step, preserving the acknowledged server/local writes.
        if (!serverSaved && machineId) {
          await sandboxApiMachines.updateConfirmPolicy(machineId, next);
          serverSaved = true;
          if (!isCurrent()) return;
        }
        if (!localSaved) {
          await writeConfirmPolicy(next);
          localSaved = true;
          if (!isCurrent()) return;
        }
        await restartDaemon();
      })
    ) {
      setPolicy(next);
      setPolicyDraft(true);
      setPolicyOpen(false);
    }
  };

  const handleUnpair = () => {
    if (busy || pairPrepared) return;
    let revocationAttempted = false;
    startOperation(
      "unpair",
      async (isCurrent) => {
        if (!revocationAttempted) {
          const storedPat = await readPairingPat();
          if (!isCurrent()) return;
          if (storedPat) {
            try {
              await sandboxApi.revokePairingPat(storedPat);
            } catch {
              // Preserve offline cleanup; a leftover PAT can still be revoked in PAT settings.
            }
            if (!isCurrent()) return;
          }
          revocationAttempted = true;
        }
        await clearPairing();
      },
      () => toast.success(t("profile.localSandbox.unpaired")),
    );
  };

  const handleRestart = () => {
    if (busy || pairPrepared) return;
    if (states.native === "error" && action === "policy") {
      if (sectionRef.current?.contains(document.activeElement))
        sectionRef.current?.focus({ preventScroll: true });
      retry("native");
      return;
    }
    startOperation("restart", async () => {
      await restartDaemon();
    });
  };

  const handleOpenLocalPath = (
    logicalName: "workspaces" | "audit" | "logs",
  ) => {
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
        {loading || processStatus === "error" ? (
          <CatalogStatus
            label={t("profile.localSandbox.title")}
            loading={loading}
            error={processStatus === "error"}
            onRetry={refreshProcessStatus}
            focusTargetRef={sectionRef}
          />
        ) : (
          <div className="flex w-full items-center justify-between gap-2 py-3 first:pt-2 last:pb-0 text-left">
            <span className="flex min-w-0 items-center gap-2 text-14 text-theme-text dark:text-stone-200">
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${
                  online
                    ? "bg-theme-success"
                    : "bg-theme-text-tertiary dark:bg-stone-500"
                }`}
                data-sandbox-online={online}
              />
              {online
                ? t("profile.localSandbox.statusOnline")
                : t("profile.localSandbox.statusOffline")}
              {status?.daemon_version && (
                <span className="truncate text-12 text-theme-text-secondary dark:text-stone-400">
                  {t("profile.localSandbox.version", {
                    version: status.daemon_version,
                  })}
                </span>
              )}
            </span>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-10 font-medium ${
                processStatus === "running"
                  ? "bg-[color-mix(in_srgb,var(--theme-success)_10%,transparent)] text-theme-success dark:text-green-400"
                  : "bg-theme-text-secondary/10 dark:bg-stone-500/20 text-theme-text-secondary dark:text-stone-400"
              }`}
            >
              {processStatus === "running"
                ? t("profile.localSandbox.processRunning")
                : t("profile.localSandbox.processStopped")}
            </span>
          </div>
        )}

        {/* 数据位置（配对态无关）：当前根 + 更改/恢复默认 + 重启引导 */}
        <SandboxDataLocationCard />

        {states.native && (
          <div className="mt-2" aria-busy={busy}>
            <CatalogStatus
              label={t(
                action === "policy"
                  ? "profile.localSandbox.policy"
                  : action === "restart"
                    ? "profile.localSandbox.restartDaemon"
                    : action === "unpair"
                      ? "profile.localSandbox.unpair"
                      : "profile.localSandbox.pairButton",
              )}
              loading={busy}
              error={states.native === "error"}
              errorText={operationError.current}
              onRetry={() => retry("native")}
              focusTargetRef={sectionRef}
            />
          </div>
        )}

        {loading ||
        processStatus === "error" ||
        pairPrepared ? null : unpaired ? (
          <form
            ref={pairFormRef}
            tabIndex={-1}
            aria-busy={busy}
            onSubmit={handlePair}
            className="space-y-3 pt-3 outline-none"
          >
            <p className="text-12 text-theme-text-secondary dark:text-stone-400">
              {t("profile.localSandbox.pairTitle")}
            </p>
            {/* 一键配对：当前登录账号铸 PAT（OAuth 账号唯一可用的手动路径） */}
            <Button
              variant="primary"
              className="w-full"
              onClick={handlePairWithCurrentAccount}
              loading={pairingCurrent}
              disabled={pairBusy}
              data-pair-current-account
            >
              {t("profile.localSandbox.pairWithCurrent")}
            </Button>
            <p className="text-12 text-theme-text-secondary">
              {t("profile.localSandbox.pairOtherAccount")}
            </p>
            <FormField label={t("auth.username")}>
              <Input
                type="text"
                autoComplete="username"
                placeholder={t("auth.usernamePlaceholder")}
                value={username}
                disabled={pairBusy}
                onChange={(e) => {
                  discard("native");
                  setUsername(e.target.value);
                }}
              />
            </FormField>
            <FormField label={t("auth.password")}>
              <Input
                type="password"
                autoComplete="current-password"
                placeholder={t("auth.passwordPlaceholder")}
                value={password}
                disabled={pairBusy}
                onChange={(e) => {
                  discard("native");
                  setPassword(e.target.value);
                }}
              />
            </FormField>
            <Button
              type="submit"
              className="w-full"
              loading={pairing}
              disabled={pairBusy || !username.trim() || !password}
            >
              {t("profile.localSandbox.pairButton")}
            </Button>
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
              loading={busy || pairPrepared}
            />

            <div className="local-sandbox-actions">
              {(["workspaces", "audit", "logs"] as const).map((path) => (
                <Button
                  key={path}
                  size="sm"
                  leftIcon={
                    <FolderOpen size={14} className="shrink-0 opacity-60" />
                  }
                  onClick={() => handleOpenLocalPath(path)}
                  disabled={busy || pairPrepared}
                >
                  {t(
                    `profile.localSandbox.${path === "workspaces" ? "openWorkspaces" : path === "audit" ? "openAudit" : "openLogs"}`,
                  )}
                </Button>
              ))}
              <Button
                size="sm"
                leftIcon={
                  <RotateCw size={14} className="shrink-0 opacity-60" />
                }
                onClick={handleRestart}
                loading={action === "restart" && busy}
                disabled={busy || pairPrepared}
              >
                {t("profile.localSandbox.restartDaemon")}
              </Button>
            </div>
            <div className="mt-3 flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Link2Off size={14} />}
                loading={unpairing}
                disabled={busy || pairPrepared}
                onClick={handleUnpair}
              >
                {t("profile.localSandbox.unpair")}
              </Button>
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
      <div
        ref={sectionRef}
        tabIndex={-1}
        className="local-sandbox-section mt-3 border-t border-theme-border pt-3 outline-none"
      >
        {body}
      </div>
    );
  }
  return (
    <div
      ref={sectionRef}
      tabIndex={-1}
      className="local-sandbox-section profile-section outline-none"
    >
      {body}
    </div>
  );
}

// React.lazy 消费的默认导出（M4 T8 PWA 预算：设置页懒加载本分区）；
// 具名导出保留给既有测试直接引用。
export default LocalSandboxSection;
