/** 会话右侧工作区：按需浏览本地/云端文件，复用文档预览。 */

import {
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useId,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Cloud,
  Copy,
  FolderClosed,
  FolderOpen,
  HardDrive,
  Loader2,
  RefreshCw,
  MoreHorizontal,
  Search,
  FolderTree,
} from "lucide-react";
import clsx from "clsx";
import { ToolbarIconButton } from "../common/ui/ToolbarIconButton";
import { Button } from "../common/ui/Button";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Tooltip } from "../common/Tooltip";
import { RightPanelActiveContext } from "../common/useRightPanelEntry";
import { LazyDocumentPreview } from "../documents/LazyDocumentPreview";
import type { DocumentPreviewProps } from "../documents/useDocumentPreviewState";
import "./workspacePanel.css";
import { getFileTypeInfo } from "../documents/utils";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import {
  useWorkspaceTree,
  type WorkspaceTreeNode,
} from "../../hooks/useWorkspaceTree";
import {
  sandboxCloudFsApi,
  sandboxFsApi,
  sandboxFsCloudStatusApi,
  type SandboxCloudStatus,
} from "../../services/api/sandboxFs";
import {
  isShellAvailable,
  revealWorkspacePath,
} from "../../services/tauri/sandboxShell";
import { parseWorkspaceSelection } from "../chat/workspaceSelection";
import { useClipboardCopy } from "../../hooks/useClipboardCopy";
import { ResourceCardMenu } from "../common/ResourceCardMenu";

interface WorkspacePanelProps {
  sessionId: string | null;
  /** 会话沙箱模式（agent_options.sandbox，"local" | "cloud"）。 */
  sandboxMode?: string | null;
  /** 会话 sandbox_machine_id（未显式选机器时空）。 */
  machineId?: string | null;
  /** 会话 sandbox_workspace 的原样 JSON（reveal 用，Rust 侧与绑定文件比对）。 */
  workspaceSelection?: string | null;
  /** Render controls beside the shell title; undefined retains the standalone toolbar. */
  headerActionsTarget?: HTMLElement | null;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
}

export function WorkspacePanel({
  sessionId,
  sandboxMode,
  machineId,
  workspaceSelection,
  headerActionsTarget,
}: WorkspacePanelProps) {
  const { t } = useTranslation();
  const active = useContext(RightPanelActiveContext);
  const { machines, currentMachineId, defaultMachineId, online } =
    useSandboxStatus();

  // Match the conversation default; a stale panel preference must not choose its backend.
  const view = sandboxMode === "local" ? "local" : "cloud";
  const isCloudView = view === "cloud";

  // ── 本地视图的目标机与 reveal 资格（对齐 SessionWorkspaceBar）──
  const onlineMachines = machines.filter((item) => item.online);
  const selection = parseWorkspaceSelection(workspaceSelection);
  const selectedMachineId =
    machineId ||
    defaultMachineId ||
    (onlineMachines.length === 1 ? onlineMachines[0].machine_id : "");
  const isLocalMachineWorkspace =
    !isCloudView &&
    online &&
    !!currentMachineId &&
    selectedMachineId === currentMachineId;

  // ── 云端视图状态徽标（零副作用速览，不唤醒沙箱）──
  const [cloudStatus, setCloudStatus] = useState<SandboxCloudStatus | null>(
    null,
  );
  const [cloudStatusLoading, setCloudStatusLoading] = useState(false);
  const cloudRequest = useRef(0);
  const refreshCloudStatus = useCallback(async () => {
    if (!sessionId) return;
    const request = ++cloudRequest.current;
    setCloudStatusLoading(true);
    try {
      const status = await sandboxFsCloudStatusApi.status(sessionId);
      if (request === cloudRequest.current) setCloudStatus(status);
    } catch {
      if (request === cloudRequest.current) setCloudStatus(null);
    } finally {
      if (request === cloudRequest.current) setCloudStatusLoading(false);
    }
  }, [sessionId]);
  useEffect(() => {
    if (!isCloudView || !sessionId) {
      setCloudStatus(null);
      return undefined;
    }
    if (!active) return;
    void refreshCloudStatus();
    // 30s 对账：暂停/回收后徽标及时转黄（status 零副作用，不唤醒沙箱）
    const timer = window.setInterval(() => void refreshCloudStatus(), 30_000);
    return () => {
      cloudRequest.current += 1;
      window.clearInterval(timer);
    };
  }, [active, isCloudView, sessionId, refreshCloudStatus]);

  // 云端可浏览：已创建（running/paused——浏览即唤醒）；未创建/未启用显示空态
  const cloudBrowsable =
    cloudStatus?.state === "running" ||
    cloudStatus?.state === "paused" ||
    // status 尚未返回时也放行（错误态兜底；404/410 由错误文案引导）
    cloudStatus === null;

  // ── 文件树：数据源随视图切换，重置键覆盖全部上下文 ──
  const source = isCloudView ? sandboxCloudFsApi : sandboxFsApi;
  const effectiveSessionId = isCloudView
    ? sessionId && cloudBrowsable
      ? sessionId
      : null
    : online && sandboxMode !== "cloud"
      ? sessionId
      : null;
  const resetKey = `${sessionId ?? ""}|${view}|${
    isCloudView
      ? "cloud"
      : `${sandboxMode ?? ""}|${selectedMachineId}|${selection?.id ?? ""}`
  }`;
  const { root, state, error, toggleDir, refresh, retryDir, expandedPaths } =
    useWorkspaceTree(effectiveSessionId, resetKey, source);

  const [preview, setPreview] = useState<Pick<
    DocumentPreviewProps,
    "path" | "content" | "signedUrl" | "footer"
  > | null>(null);
  const [query, setQuery] = useState("");
  const [showFiles, setShowFiles] = useState(true);
  const [rootExpanded, setRootExpanded] = useState(true);
  const [explorerCollapsed, setExplorerCollapsed] = useState(false);
  const selectedButtonRef = useRef<HTMLButtonElement>(null);
  const explorerRef = useRef<HTMLElement>(null);
  const previewRef = useRef<HTMLElement>(null);
  const previewPrefix = `workspace:${JSON.stringify([
    resetKey,
    workspaceSelection,
  ])}:`;
  const [openingPath, setOpeningPath] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<{
    path: string;
    message: string;
    action: "read" | "reveal";
  } | null>(null);
  const previewRequest = useRef(0);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const menuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const menuId = useId();
  const [copyPath, setCopyPath] = useState("");
  const { copying, copy } = useClipboardCopy(copyPath);
  const closeMenu = useCallback((restoreFocus = false) => {
    setContextMenu(null);
    if (restoreFocus) menuTriggerRef.current?.focus();
  }, []);

  useEffect(() => {
    previewRequest.current += 1;
    setPreview(null);
    setQuery("");
    setShowFiles(true);
    setRootExpanded(true);
    setPreviewError(null);
    setOpeningPath(null);
    setContextMenu(null);
    setCopyPath("");
    return () => {
      previewRequest.current += 1;
    };
  }, [previewPrefix]);

  useEffect(() => {
    const explorer = explorerRef.current;
    if (
      preview &&
      !showFiles &&
      explorer &&
      getComputedStyle(explorer).display === "none" &&
      (document.activeElement === document.body ||
        explorer.contains(document.activeElement))
    )
      previewRef.current?.focus({ preventScroll: true });
  }, [preview, showFiles]);

  const openFile = useCallback(
    async (path: string) => {
      if (!sessionId) return;
      const request = ++previewRequest.current;
      setOpeningPath(path);
      setPreviewError(null);
      try {
        const result = await source.read(sessionId, path, 0, 2000);
        if (request !== previewRequest.current) return;
        if (result.error) throw new Error(result.error);
        if (result.encoding !== "utf-8" && result.encoding !== "base64")
          throw new Error("Missing file content");
        setPreview({
          path,
          footer:
            result.next_offset != null ? (
              <p>
                {t("documents.fileTooLargeLines", {
                  count: result.next_offset,
                })}
              </p>
            ) : undefined,
          ...(result.encoding === "base64"
            ? {
                signedUrl: `data:application/octet-stream;base64,${result.content ?? ""}`,
              }
            : { content: result.content ?? "" }),
        });
        setShowFiles(false);
      } catch {
        if (request === previewRequest.current)
          setPreviewError({
            path,
            message: t("documents.error"),
            action: "read",
          });
      } finally {
        if (request === previewRequest.current) setOpeningPath(null);
      }
    },
    [sessionId, source, t],
  );

  const handleContextMenu = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>, path: string) => {
      event.preventDefault();
      event.stopPropagation();
      menuTriggerRef.current = event.currentTarget;
      setCopyPath(path);
      const rect = event.currentTarget.getBoundingClientRect();
      const pointer =
        event.type === "contextmenu" && (event.clientX || event.clientY);
      setContextMenu({
        x: pointer ? event.clientX : rect.left,
        y: pointer ? event.clientY : rect.bottom + 4,
        path,
      });
    },
    [],
  );

  const handleReveal = useCallback(
    async (relPath: string) => {
      if (!sessionId || isCloudView) return;
      const request = previewRequest.current;
      setPreviewError(null);
      try {
        await revealWorkspacePath(
          sessionId,
          relPath,
          workspaceSelection,
          selectedMachineId,
        );
      } catch {
        if (request === previewRequest.current)
          setPreviewError({
            path: relPath,
            message: t("sessionWorkspace.failed"),
            action: "reveal",
          });
      }
    },
    [sessionId, isCloudView, workspaceSelection, selectedMachineId, t],
  );

  const handleRefresh = useCallback(() => {
    if (isCloudView) {
      void refreshCloudStatus();
    }
    refresh();
  }, [isCloudView, refreshCloudStatus, refresh]);

  const backToFiles = () => {
    const opener = selectedButtonRef.current;
    const request = ++previewRequest.current;
    setOpeningPath(null);
    setShowFiles(true);
    requestAnimationFrame(() => {
      if (request !== previewRequest.current) return;
      if (opener?.isConnected) opener.focus();
      else explorerRef.current?.focus({ preventScroll: true });
    });
  };

  const renderNodes = (nodes: WorkspaceTreeNode[], depth: number) =>
    nodes
      .filter(
        (node) =>
          node.isDir ||
          node.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
      )
      .map((node) => {
        const padding = 12 + depth * 12;
        if (node.isDir) {
          const expanded = expandedPaths.has(node.path);
          return (
            <div key={node.path}>
              <button
                onClick={() => toggleDir(node.path)}
                aria-expanded={expanded}
                aria-busy={node.loading ?? false}
                title={node.path}
                className="workspace-file-row"
                style={{ paddingLeft: padding }}
              >
                <ChevronRight
                  size={13}
                  className={clsx(
                    "shrink-0 text-theme-text-muted transition-transform duration-150 motion-reduce:transition-none",
                    expanded && "rotate-90",
                  )}
                />
                {node.loading ? (
                  <Loader2
                    size={16}
                    className="shrink-0 animate-spin motion-reduce:animate-none text-theme-text-tertiary"
                  />
                ) : expanded ? (
                  <FolderOpen
                    size={16}
                    className="shrink-0 text-theme-text-secondary"
                  />
                ) : (
                  <FolderClosed
                    size={16}
                    className="shrink-0 text-theme-text-secondary"
                  />
                )}
                <span className="truncate text-13 text-left">{node.name}</span>
              </button>
              {expanded && node.error && (
                <div
                  className="flex min-w-0 items-center gap-2 pr-3 pb-1"
                  style={{ paddingLeft: padding + 21 }}
                >
                  <p
                    role="alert"
                    className="min-w-0 flex-1 text-12 text-theme-text-secondary [overflow-wrap:anywhere]"
                  >
                    {node.error}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`${t("workspacePanel.retry")}: ${node.name}`}
                    className="shrink-0 max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
                    onClick={(event) => {
                      const trigger =
                        event.currentTarget.parentElement
                          ?.previousElementSibling;
                      if (trigger instanceof HTMLElement) trigger.focus();
                      void retryDir(node.path);
                    }}
                  >
                    {t("workspacePanel.retry")}
                  </Button>
                </div>
              )}
              {expanded &&
                node.children &&
                renderNodes(node.children, depth + 1)}
            </div>
          );
        }
        const info = getFileTypeInfo(node.name);
        const Icon = info.icon;
        const isLoading = openingPath === node.path;
        return (
          <div
            className="workspace-file"
            key={node.path}
            data-selected={preview?.path === node.path}
          >
            <button
              ref={preview?.path === node.path ? selectedButtonRef : undefined}
              onClick={() => void openFile(node.path)}
              title={node.path}
              aria-label={node.name}
              aria-current={preview?.path === node.path ? "true" : undefined}
              aria-busy={isLoading}
              onContextMenu={(e) => handleContextMenu(e, node.path)}
              className="workspace-file-row"
              style={{ paddingLeft: padding + 21 }}
            >
              {isLoading ? (
                <Loader2
                  size={18}
                  className="shrink-0 animate-spin motion-reduce:animate-none"
                />
              ) : (
                <Icon
                  size={16}
                  className="shrink-0 text-theme-text-secondary"
                />
              )}
              <span className="workspace-file-name">{node.name}</span>
            </button>
            <button
              className="workspace-file-menu"
              aria-label={t("workspacePanel.fileActions", { name: node.name })}
              onClick={(event) =>
                contextMenu?.path === node.path
                  ? closeMenu(true)
                  : handleContextMenu(event, node.path)
              }
              aria-haspopup="menu"
              aria-expanded={contextMenu?.path === node.path}
              aria-controls={
                contextMenu?.path === node.path ? menuId : undefined
              }
            >
              <MoreHorizontal size={16} />
            </button>
          </div>
        );
      });

  // 云端状态徽标（云端视图头部）：running 绿 / paused 黄（打开时自动唤醒）
  const cloudStateBadge = useMemo(() => {
    if (!isCloudView || cloudStatusLoading) return null;
    const stateValue = cloudStatus?.state;
    if (stateValue === "running") {
      return (
        <Tooltip
          content={t("workspacePanel.cloudRunning", {
            defaultValue: "云端电脑 · 运行中",
          })}
        >
          <span className="size-1.5 rounded-full bg-theme-success" />
        </Tooltip>
      );
    }
    if (stateValue === "paused") {
      return (
        <Tooltip
          content={t("workspacePanel.cloudPaused", {
            defaultValue: "云端电脑 · 已暂停，打开时自动唤醒",
          })}
        >
          <span className="size-1.5 rounded-full bg-amber-500" />
        </Tooltip>
      );
    }
    return null;
  }, [isCloudView, cloudStatusLoading, cloudStatus, t]);

  // 云端视图空态文案
  const cloudEmptyHint = useMemo(() => {
    if (cloudStatus?.state === "not_created") {
      return t("workspacePanel.cloudNotCreated", {
        defaultValue: "云端电脑尚未创建；在云端会话中发送消息后会自动创建",
      });
    }
    if (cloudStatus?.state === "disabled") {
      return t("workspacePanel.cloudDisabled", {
        defaultValue: "云端沙箱未启用",
      });
    }
    return null;
  }, [cloudStatus, t]);

  const localViewBlocked = !isCloudView && (!online || !sessionId);
  const toolbar = (
    <div className="workspace-header-actions flex items-center">
      {cloudStateBadge && (
        <span
          className="workspace-cloud-status"
          role="status"
          aria-label={t(
            cloudStatus?.state === "paused"
              ? "workspacePanel.cloudPaused"
              : "workspacePanel.cloudRunning",
          )}
        >
          {cloudStateBadge}
        </span>
      )}
      <ToolbarIconButton
        variant="muted"
        className="workspace-explorer-toggle"
        aria-label={t("project.toggleExplorer")}
        title={t("project.toggleExplorer")}
        aria-expanded={!explorerCollapsed}
        onClick={() => {
          setExplorerCollapsed(!explorerCollapsed);
          setShowFiles(true);
        }}
        icon={<FolderTree size={16} />}
      />
      <ToolbarIconButton
        variant="muted"
        onClick={handleRefresh}
        disabled={state === "loading" || cloudStatusLoading}
        className="disabled:opacity-40"
        aria-label={t("workspacePanel.refresh", { defaultValue: "刷新" })}
        title={t("workspacePanel.refresh", { defaultValue: "刷新" })}
        icon={
          <RefreshCw
            size={16}
            className={
              state === "loading" || cloudStatusLoading
                ? "animate-spin motion-reduce:animate-none"
                : ""
            }
          />
        }
      />
    </div>
  );

  return (
    <div
      className="workspace-panel font-sans flex h-full min-h-0 flex-col bg-theme-bg text-theme-text"
      data-preview={!!preview}
      data-show-files={showFiles}
      data-explorer-collapsed={explorerCollapsed}
    >
      {headerActionsTarget
        ? createPortal(toolbar, headerActionsTarget)
        : headerActionsTarget === undefined && (
            <div className="flex shrink-0 justify-end border-b border-theme-border px-2 py-1">
              {toolbar}
            </div>
          )}

      <div className="workspace-browser">
        <section
          ref={explorerRef}
          tabIndex={-1}
          className="workspace-explorer focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-[var(--theme-ring)]"
          aria-label={t("workspacePanel.title")}
        >
          <div className="workspace-search">
            <Search size={16} aria-hidden="true" />
            <input
              aria-label={t("workspacePanel.searchFiles")}
              placeholder={t("workspacePanel.searchFiles")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <button
            className="workspace-root"
            aria-expanded={rootExpanded}
            onClick={() => setRootExpanded(!rootExpanded)}
          >
            <ChevronRight
              size={12}
              className={rootExpanded ? "rotate-90" : undefined}
            />
            {t("workspacePanel.root")}
          </button>
          {!isCloudView && selection && (
            <div
              className="shrink-0 truncate border-b border-theme-border px-3 py-2 text-12 text-theme-text-secondary"
              title={selection.path}
            >
              {selection.path}
            </div>
          )}
          {previewError && (
            <div className="flex min-w-0 shrink-0 items-center gap-2 px-3 py-2">
              <p
                role="alert"
                className="min-w-0 flex-1 text-12 text-theme-text-secondary [overflow-wrap:anywhere]"
              >
                <span className="block font-medium text-theme-text">
                  {previewError.path}
                </span>
                {previewError.message}
              </p>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`${t("workspacePanel.retry")}: ${previewError.path}`}
                className="shrink-0 max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
                onClick={() => {
                  explorerRef.current?.focus({ preventScroll: true });
                  if (previewError.action === "reveal")
                    void handleReveal(previewError.path);
                  else void openFile(previewError.path);
                }}
              >
                {t("workspacePanel.retry")}
              </Button>
            </div>
          )}

          {/* 本地视图状态区 */}
          {!isCloudView ? (
            !online ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
                <HardDrive size={22} className="text-theme-text-tertiary" />
                <p className="text-12 text-theme-text-secondary dark:text-stone-400">
                  {t("workspacePanel.daemonOffline", {
                    defaultValue: "本地沙箱未连接，无法浏览工作区文件",
                  })}
                </p>
              </div>
            ) : !sessionId ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
                <p className="text-12 text-theme-text-secondary dark:text-stone-400">
                  {t("workspacePanel.noSession", {
                    defaultValue: "打开一个会话后即可浏览其工作区文件",
                  })}
                </p>
              </div>
            ) : null
          ) : null}

          {/* 云端视图空态（未创建/未启用）；会话缺省提示两视图共用 */}
          {isCloudView && cloudEmptyHint ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
              <Cloud size={22} className="text-theme-text-tertiary" />
              <p className="text-12 text-theme-text-secondary dark:text-stone-400">
                {cloudEmptyHint}
              </p>
            </div>
          ) : isCloudView && !sessionId ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
              <p className="text-12 text-theme-text-secondary dark:text-stone-400">
                {t("workspacePanel.noSession", {
                  defaultValue: "打开一个会话后即可浏览其工作区文件",
                })}
              </p>
            </div>
          ) : null}

          {/* 文件树（本地/云端共用） */}
          {!localViewBlocked &&
          !(isCloudView && cloudEmptyHint) &&
          !(isCloudView && !sessionId) ? (
            state === "error" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
                <p
                  role="alert"
                  className="text-12 text-theme-text-secondary [overflow-wrap:anywhere]"
                >
                  {error}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    explorerRef.current?.focus({ preventScroll: true });
                    handleRefresh();
                  }}
                  className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
                >
                  {t("workspacePanel.retry", { defaultValue: "重试" })}
                </Button>
              </div>
            ) : (
              <div
                hidden={!rootExpanded}
                className="workspace-file-list min-h-0 flex-1 overflow-y-auto"
              >
                {state === "loading" && root.length === 0 ? (
                  <div
                    role="status"
                    className="flex items-center justify-center gap-2 pt-6 text-12 text-theme-text-secondary"
                  >
                    <LoadingSpinner size="sm" />
                    {t("common.loading")}
                  </div>
                ) : root.length === 0 ? (
                  state === "idle" ? null : (
                    <p className="pt-4 text-center text-12 text-theme-text-secondary dark:text-stone-400">
                      {t("workspacePanel.emptyDir", {
                        defaultValue: "空工作区",
                      })}
                    </p>
                  )
                ) : (
                  <div className="flex flex-col">{renderNodes(root, 0)}</div>
                )}
              </div>
            )
          ) : null}
        </section>
        <section
          ref={previewRef}
          tabIndex={-1}
          className="workspace-preview focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-[var(--theme-ring)]"
          aria-label={t("documents.preview")}
        >
          {preview ? (
            <LazyDocumentPreview
              key={preview.path}
              {...preview}
              embedded
              onBack={backToFiles}
              onClose={() => {
                setPreview(null);
                backToFiles();
              }}
            />
          ) : (
            <div className="workspace-preview-empty">
              <FolderOpen size={28} strokeWidth={1.5} aria-hidden="true" />
              <p>{t("workspacePanel.selectFile")}</p>
            </div>
          )}
        </section>
      </div>

      {contextMenu && (
        <ResourceCardMenu
          id={menuId}
          title={t("workspacePanel.fileActions", { name: contextMenu.path })}
          position={contextMenu}
          onClose={closeMenu}
          actions={[
            {
              label: t("workspacePanel.copyPath"),
              icon: <Copy size={14} />,
              disabled: copying,
              onClick: copy,
            },
            ...(isShellAvailable() && isLocalMachineWorkspace
              ? [
                  {
                    label: t("workspacePanel.revealInFileManager"),
                    icon: <FolderOpen size={14} />,
                    onClick: () => {
                      void handleReveal(contextMenu.path);
                    },
                  },
                ]
              : []),
          ]}
        />
      )}
    </div>
  );
}
