import { BrandLogo } from "../common/BrandLogo";
import { BrandWordmark } from "../common/BrandWordmark";
import { APP_NAME } from "../../constants";
import {
  OPEN_NOTIFICATIONS_EVENT,
  DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT,
  NOTIFICATION_COUNT_EVENT,
} from "../layout/DesktopSidebarShell/desktopShellPlatform";
import { ChatHeaderFrame } from "../layout/AppContent/ChatHeaderFrame";
import { lazy, Suspense, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Bell,
  Search,
  ArrowLeft,
  Archive,
  Brain,
  CalendarClock,
  ChartNoAxesCombined,
  ListTodo,
  MessageSquare,
  MessagesSquare,
  MoreHorizontal,
  Pencil,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Users,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import { AgentAvatar } from "../common/AgentAvatar";
import { personaPresetApi } from "../../services/api/personaPreset";
import { teamApi } from "../../services/api/team";
import { getTeamFallbackAvatar } from "../team/teamAvatarUtils";
import { assistantApi } from "../../services/api/assistant";
import {
  assistantConfiguration,
  assistantActivityPath,
  type Assistant,
  type AssistantStatus,
} from "../../types/assistant";
import { observePanelWidths } from "../common/panelWidths";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { EmptyState } from "../common/EmptyState";
import { SidebarToggleIcon } from "../common/SidebarToggleIcon";
import { ResourceCardMenu } from "../common/ResourceCardMenu";
import { Button } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { AssistantActivitySummary } from "./AssistantActivitySummary";
import { AssistantDataPage } from "./AssistantDataPage";
import { EditorSidebar } from "../common/EditorSidebar";
import { AssistantGroupEditor } from "./AssistantGroupEditor";
import { AssistantGroupContext } from "./AssistantGroupContext";
import { AssistantEditor } from "./AssistantEditor";
import { AssistantDiscussionsDialog } from "./AssistantDiscussionsDialog";
import { AssistantRulesDialog } from "./AssistantRulesDialog";
import { AssistantTasksDialog } from "./AssistantTasksDialog";
import { EmbeddedHeaderActionsContext } from "../layout/AppContent/EmbeddedHeaderActionsContext";
import "../../styles/assistant-workspace.css";

const ChatAppContent = lazy(() =>
  import("../layout/AppContent/ChatAppContent").then((module) => ({
    default: module.ChatAppContent,
  })),
);
const PAGE_SIZE = 20;
const noop = () => {};
const profileKey = (assistant: Assistant) =>
  assistant.team_id
    ? `team:${assistant.team_id}`
    : assistant.persona_preset_id
      ? `persona:${assistant.persona_preset_id}`
      : "";
type AssistantProfile = { name: string; avatar?: string | null; seed: string };

export function AssistantsPanel() {
  const workspaceHeader = useContext(EmbeddedHeaderActionsContext);
  const [notificationCount, setNotificationCount] = useState(0);
  useEffect(() => {
    const update = (event: Event) =>
      setNotificationCount((event as CustomEvent<number>).detail);
    window.addEventListener(NOTIFICATION_COUNT_EVENT, update);
    return () => window.removeEventListener(NOTIFICATION_COUNT_EVENT, update);
  }, []);
  const { assistantId, sessionId, view: routeView } = useParams();
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(Permission.CHAT_WRITE);
  const view = sessionId
    ? "chat"
    : routeView ||
      (pathname.endsWith("/memory")
        ? "memory"
        : pathname.endsWith("/usage")
          ? "usage"
          : "chat");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [archived, setArchived] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<Assistant[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [selected, setSelected] = useState<Assistant | null>(null);
  const [selectionError, setSelectionError] = useState("");
  const [verifiedSession, setVerifiedSession] = useState<{
    key: string;
    kind: Assistant["context_kind"];
    taskId?: string | null;
  } | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState("");
  const [editor, setEditor] = useState<Assistant | "new" | "group" | null>(
    null,
  );
  const [profiles, setProfiles] = useState<Record<string, AssistantProfile>>(
    {},
  );
  const canReadPersonas = hasPermission(Permission.PERSONA_PRESET_READ);
  const canReadTeams = hasPermission(Permission.TEAM_READ);
  const [collapsed, setCollapsed] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [detailsView, setDetailsView] = useState<string | null>(null);
  useEffect(() => {
    setTasksOpen(false);
    setDetailsView(null);
  }, [assistantId]);
  const [headerActionsTarget, setHeaderActionsTarget] =
    useState<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const addAnchor = useRef<HTMLButtonElement>(null);
  const [addMenuPosition, setAddMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const menuAnchor = useRef<HTMLButtonElement>(null);
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const assistant = selected?.id === assistantId ? selected : null;
  const base = assistant
    ? `/assistants/${encodeURIComponent(assistant.id)}`
    : "/assistants";

  useEffect(() => {
    if (panelRef.current) return observePanelWidths(panelRef.current);
  }, []);

  // Resolve only visible identities; never fetch a role or team without its read permission.
  const profileKeys = JSON.stringify(
    [
      ...new Set(
        [...(data ?? []), ...(assistant ? [assistant] : [])]
          .map(profileKey)
          .filter((key) =>
            key.startsWith("team:")
              ? canReadTeams
              : key.startsWith("persona:") && canReadPersonas,
          ),
      ),
    ].sort(),
  );
  useEffect(() => {
    let active = true;
    setProfiles({});
    void Promise.all(
      (JSON.parse(profileKeys) as string[]).map(async (key) => {
        try {
          const id = key.slice(key.indexOf(":") + 1);
          const profile = key.startsWith("team:")
            ? await teamApi.get(id).then((team) => ({
                name: team.name,
                avatar: team.avatar || getTeamFallbackAvatar(team),
              }))
            : await personaPresetApi.get(id);
          return [
            key,
            { name: profile.name, avatar: profile.avatar, seed: id },
          ] as const;
        } catch {
          // Deleted or inaccessible profiles retain the assistant's own generated identity.
          return [key, null] as const;
        }
      }),
    ).then((entries) => {
      if (active)
        setProfiles(
          Object.fromEntries(
            entries.filter((entry) => entry[1] !== null),
          ) as Record<string, AssistantProfile>,
        );
    });
    return () => {
      active = false;
    };
  }, [profileKeys, refresh]);
  const chief = data?.find((item) => item.kind === "chief");
  const openChief = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError("");
    try {
      const value = chief ?? (await assistantApi.chief());
      navigate(assistantActivityPath(value));
      setRefresh((x) => x + 1);
    } catch (failure) {
      setActionError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };
  const profileFor = (item: Assistant) =>
    (item.team_id ? canReadTeams : canReadPersonas)
      ? profiles[profileKey(item)]
      : undefined;

  useEffect(() => {
    let active = true;
    let pending = false;
    setLoading(true);
    setListError("");
    const update = async () => {
      if (pending || document.visibilityState === "hidden") return;
      pending = true;
      try {
        const result = await assistantApi.list(
          (page - 1) * PAGE_SIZE,
          PAGE_SIZE,
          archived,
        );
        if (active) {
          setData(result.assistants);
          setTotal(result.total);
          setListError("");
        }
      } catch (failure) {
        if (active) {
          setListError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
          // Keep navigation usable without presenting stale runtime state as current.
          setData(
            (previous) =>
              previous?.map((item) => ({ ...item, activity: null })) ?? null,
          );
        }
      } finally {
        pending = false;
        if (active) setLoading(false);
      }
    };
    void update();
    const timer = window.setInterval(() => void update(), 5000);
    window.addEventListener("assistants:changed", update);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("assistants:changed", update);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [page, archived, refresh, t]);

  useEffect(() => {
    let active = true;
    let sequence = 0;
    setSelected(null);
    setSelectionError("");
    setActionError("");
    setMenuPosition(null);
    if (!assistantId) return;
    const load = () => {
      const request = ++sequence;
      void assistantApi
        .get(assistantId)
        .then((value) => {
          if (active && request === sequence) {
            setSelected(value);
            setSelectionError("");
          }
        })
        .catch((failure: unknown) => {
          if (active && request === sequence) {
            setSelected(null);
            setSelectionError(
              failure instanceof Error
                ? failure.message
                : t("common.loadFailed"),
            );
          }
        });
    };
    load();
    window.addEventListener("focus", load);
    window.addEventListener("assistants:changed", load);
    return () => {
      active = false;
      window.removeEventListener("focus", load);
      window.removeEventListener("assistants:changed", load);
    };
  }, [assistantId, refresh, t]);

  useEffect(() => {
    let active = true;
    if (!assistant || sessionId || view !== "chat") return;
    const open = async () => {
      try {
        const id =
          canWrite && assistant.status === "active"
            ? (await assistantApi.openConversation(assistant.id)).id
            : assistant.session_id;
        if (active)
          navigate(`${base}/chat/${encodeURIComponent(id)}`, { replace: true });
      } catch (failure) {
        if (active)
          setSelectionError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      }
    };
    void open();
    return () => {
      active = false;
    };
  }, [assistant, base, canWrite, sessionId, view, navigate, t]);

  useEffect(() => {
    let active = true;
    setVerifiedSession(null);
    setSessionError("");
    if (!assistant || !sessionId || sessionId === assistant.session_id) return;
    void assistantApi
      .forConversation(sessionId)
      .then((context) => {
        if (!active) return;
        if (context?.id === assistant.id)
          setVerifiedSession({
            key: `${assistant.id}:${sessionId}`,
            kind: context.context_kind,
            taskId: context.context_task_id,
          });
        else setSessionError(t("assistants.conversationMismatch"));
      })
      .catch((failure: unknown) => {
        if (active)
          setSessionError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      });
    return () => {
      active = false;
    };
  }, [assistant, sessionId, t]);

  const act = async (status: AssistantStatus) => {
    if (!assistant || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError("");
    try {
      await assistantApi.update(assistant.id, {
        ...assistantConfiguration(assistant),
        revision: assistant.revision,
        status,
      });
      setRefresh((old) => old + 1);
    } catch (failure) {
      setActionError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const navigation = [
    { id: "chat", label: "conversation", icon: MessageSquare },
    { id: "tasks", label: "workRecords", icon: ListTodo },
    { id: "discussions", label: "discussions", icon: MessagesSquare },
    ...(hasPermission(Permission.SCHEDULED_TASK_READ)
      ? [{ id: "rules", label: "rules", icon: CalendarClock }]
      : []),
    ...(hasPermission(Permission.MEMORY_READ)
      ? [{ id: "memory", label: "memory", icon: Brain }]
      : []),
    ...(hasPermission(Permission.USAGE_READ)
      ? [{ id: "usage", label: "usage", icon: ChartNoAxesCombined }]
      : []),
  ];
  const openView = (id: string) =>
    navigate(id === "chat" ? base : `${base}/${id}`);
  const retry = () => setRefresh((old) => old + 1);
  const workspaceActions = (
    <>
      <div
        className="assistant-workspace-brand"
        role="img"
        aria-label={APP_NAME}
      >
        <BrandLogo alt="" className="relative -top-0.5 size-7 shrink-0" />
        <BrandWordmark decorative className="h-6 w-auto min-w-0" />
      </div>

      <Button
        className="assistant-workspace-desktop-toggle"
        variant="ghost"
        aria-label={t("assistants.toggleNavigation")}
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((value) => !value)}
      >
        <SidebarToggleIcon className="size-4" />
      </Button>
      <Button
        variant="ghost"
        className="assistant-workspace-global-action relative"
        aria-label={
          t("nav.notifications") +
          (notificationCount > 0 ? ` (${notificationCount})` : "")
        }
        title={t("nav.notifications")}
        onClick={() =>
          window.dispatchEvent(new Event(OPEN_NOTIFICATIONS_EVENT))
        }
      >
        <Bell size={16} />
        {notificationCount > 0 && (
          <span className="count-badge count-badge--overlay" aria-hidden="true">
            {Math.min(notificationCount, 99)}
          </span>
        )}
      </Button>
      <Button
        variant="ghost"
        className="assistant-workspace-global-action"
        aria-label={t("sidebar.searchSessions")}
        title={t("sidebar.searchSessions")}
        onClick={() =>
          window.dispatchEvent(new Event(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT))
        }
      >
        <Search size={16} />
      </Button>
      {assistantId && (
        <Button
          className="assistant-workspace-mobile-back"
          variant="ghost"
          aria-label={t("assistants.title")}
          onClick={() => navigate("/assistants")}
        >
          <ArrowLeft size={16} />
        </Button>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <h2 className="assistant-workspace-title min-w-0 truncate text-14 font-medium sm:sr-only">
          {assistant?.name || t("assistants.title")}
        </h2>
        {!assistantId && !canWrite && (
          <span className="truncate text-14 font-medium">
            {t("assistants.title")}
          </span>
        )}
        {assistant && view !== "chat" && (
          <Button
            variant="ghost"
            className="shrink-0"
            leftIcon={<ArrowLeft size={16} />}
            onClick={() => openView("chat")}
          >
            {t("assistants.backToChat")}
          </Button>
        )}
        {assistant &&
          (assistant.status !== "active" ||
            !["chat", "tasks"].includes(view)) && (
            <p className="assistant-workspace-role truncate">
              {t(
                `assistants.${
                  assistant.status !== "active"
                    ? assistant.status
                    : navigation.find((item) => item.id === view)?.label ||
                      "conversation"
                }`,
              )}
            </p>
          )}
      </div>
      {assistant && (
        <>
          <button
            ref={menuAnchor}
            type="button"
            className="assistant-workspace-menu-trigger"
            aria-label={t("common.moreOptions")}
            aria-haspopup="menu"
            aria-expanded={!!menuPosition}
            aria-controls="assistant-workspace-menu"
            onClick={() => {
              const rect = menuAnchor.current!.getBoundingClientRect();
              setMenuPosition(
                menuPosition ? null : { x: rect.right, y: rect.bottom + 4 },
              );
            }}
          >
            <MoreHorizontal size={16} />
          </button>
          {menuPosition && (
            <ResourceCardMenu
              id="assistant-workspace-menu"
              title={assistant.name}
              position={menuPosition}
              anchorRef={menuAnchor}
              onClose={(restore = true) => {
                setMenuPosition(null);
                if (restore) menuAnchor.current?.focus();
              }}
              actions={[
                ...navigation.slice(1).map(({ id, label, icon: Icon }) => ({
                  label: t(`assistants.${label}`),
                  icon: <Icon size={14} />,
                  onClick: () =>
                    id === "tasks" ? setTasksOpen(true) : setDetailsView(id),
                })),
                ...(canWrite
                  ? [
                      {
                        label: t("assistants.edit"),
                        icon: <Pencil size={14} />,
                        separatorBefore: true,
                        onClick: () => setEditor(assistant),
                      },
                      {
                        label: t(
                          assistant.status === "active"
                            ? "assistants.pause"
                            : "assistants.resume",
                        ),
                        icon:
                          assistant.status === "active" ? (
                            <Pause size={14} />
                          ) : (
                            <Play size={14} />
                          ),
                        disabled: busy,
                        onClick: () =>
                          void act(
                            assistant.status === "active" ? "paused" : "active",
                          ),
                      },
                      ...(assistant.kind !== "chief" &&
                      assistant.status !== "archived"
                        ? [
                            {
                              label: t("assistants.archive"),
                              icon: <Archive size={14} />,
                              disabled: busy,
                              onClick: () => void act("archived"),
                            },
                          ]
                        : []),
                    ]
                  : []),
              ]}
            />
          )}
        </>
      )}

      <div
        ref={setHeaderActionsTarget}
        className="assistant-workspace-header-actions"
      />
      {assistant?.kind === "group" && (
        <Button
          variant="ghost"
          className="assistant-workspace-group-trigger"
          aria-label={t("assistants.groupDetails")}
          title={t("assistants.groupCount", {
            count: assistant.member_ids?.length ?? 0,
          })}
          onClick={() => setEditor(assistant)}
          disabled={!canWrite}
        >
          <Users size={16} />
        </Button>
      )}
    </>
  );

  return (
    <div
      data-workspace-ui=""
      data-assistant-workspace=""
      className={`assistant-workspace ${assistantId ? "has-selection" : ""} ${
        collapsed ? "is-collapsed" : ""
      }`}
    >
      <aside
        className="assistant-workspace-sidebar"
        aria-label={t("assistants.title")}
      >
        {canWrite && !archived && (
          <button
            type="button"
            className="assistant-workspace-assistant assistant-chief"
            aria-current={assistant?.kind === "chief" ? "page" : undefined}
            disabled={busy}
            onClick={() => void openChief()}
          >
            <AgentAvatar seed="Chief" size={32} />
            <span className="min-w-0 flex-1 text-left">
              <AssistantActivitySummary
                assistant={chief}
                fallback={t("assistants.chiefHint")}
              />
            </span>
          </button>
        )}
        {actionError && !assistant && (
          <ConfigPanelErrorCallout message={actionError} />
        )}
        <div className="assistant-workspace-sidebar-heading">
          <h1>{t(archived ? "assistants.archived" : "assistants.current")}</h1>
          {canWrite && (
            <Button
              className="assistant-workspace-add"
              variant="ghost"
              aria-label={t("assistants.addCompanion")}
              title={t("assistants.addCompanion")}
              aria-haspopup="menu"
              aria-expanded={!!addMenuPosition}
              aria-controls={addMenuPosition ? "assistant-add-menu" : undefined}
              onClick={(event) => {
                addAnchor.current = event.currentTarget;
                const rect = event.currentTarget.getBoundingClientRect();
                setAddMenuPosition(
                  addMenuPosition ? null : { x: rect.left, y: rect.bottom + 4 },
                );
              }}
            >
              <Plus size={16} />
            </Button>
          )}
          <Button
            variant="ghost"
            aria-label={t("common.refresh")}
            title={t("common.refresh")}
            disabled={loading}
            onClick={retry}
          >
            <RefreshCw size={16} />
          </Button>
          <Button
            variant="ghost"
            aria-label={t(
              archived ? "assistants.current" : "assistants.archived",
            )}
            aria-pressed={archived}
            title={t(archived ? "assistants.current" : "assistants.archived")}
            onClick={() => {
              setArchived((value) => !value);
              setTotal(0);
              setPage(1);
              setData(null);
            }}
          >
            <Archive size={14} />
          </Button>
        </div>
        <div className="assistant-workspace-assistant-list">
          {listError && <ConfigPanelErrorCallout message={listError} />}
          {loading && !data ? (
            <PanelLoadingState />
          ) : data?.length ? (
            <ul>
              {data
                .filter((item) => item.kind !== "chief")
                .map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="assistant-workspace-assistant"
                      aria-current={
                        item.id === assistantId ? "page" : undefined
                      }
                      onClick={() => navigate(assistantActivityPath(item))}
                      title={item.name}
                    >
                      <AgentAvatar
                        avatar={item.avatar || profileFor(item)?.avatar}
                        seed={profileFor(item)?.seed || item.name}
                        size={32}
                      />
                      <span className="min-w-0 flex-1 text-left">
                        <AssistantActivitySummary
                          assistant={item}
                          fallback={
                            (item.kind === "group"
                              ? t("assistants.groupCount", {
                                  count: item.member_ids?.length ?? 0,
                                })
                              : profileFor(item)?.name) ||
                            t(
                              item.team_id
                                ? "assistants.team"
                                : "assistants.channelBinding",
                            )
                          }
                        />
                      </span>
                    </button>
                  </li>
                ))}
            </ul>
          ) : !listError && !loading ? (
            <p className="px-3 py-4 text-12 text-theme-text-secondary">
              {t(archived ? "assistants.emptyArchived" : "assistants.empty")}
            </p>
          ) : null}
        </div>
        <div
          className="assistant-workspace-list-pagination"
          data-single-page={total <= PAGE_SIZE || undefined}
        >
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={(next) => {
              setPage(next);
              setData(null);
            }}
          />
        </div>
      </aside>
      <div
        ref={panelRef}
        className="assistant-workspace-main"
        data-panel="assistants"
        data-workspace-content=""
      >
        {workspaceHeader ? (
          createPortal(
            <div
              data-assistant-selected={assistantId ? "" : undefined}
              className="assistant-workspace-header assistant-workspace-header--embedded"
            >
              {workspaceActions}
            </div>,
            workspaceHeader,
          )
        ) : (
          <ChatHeaderFrame className="assistant-workspace-header">
            {workspaceActions}
          </ChatHeaderFrame>
        )}
        {tasksOpen && assistant && (
          <AssistantTasksDialog
            assistant={assistant}
            canWrite={canWrite}
            onClose={() => setTasksOpen(false)}
          />
        )}
        {assistant && detailsView === "discussions" && (
          <AssistantDiscussionsDialog
            assistant={assistant}
            onClose={() => setDetailsView(null)}
          />
        )}
        {assistant &&
          detailsView === "rules" &&
          hasPermission(Permission.SCHEDULED_TASK_READ) && (
            <AssistantRulesDialog
              assistant={assistant}
              canWrite={
                canWrite && hasPermission(Permission.SCHEDULED_TASK_WRITE)
              }
              onClose={() => setDetailsView(null)}
            />
          )}
        {assistant && (detailsView === "memory" || detailsView === "usage") && (
          <EditorSidebar
            open
            width="wide"
            title={t(`assistants.${detailsView}`)}
            onClose={() => setDetailsView(null)}
          >
            <div className="flex h-full min-h-0 flex-col">
              <AssistantDataPage
                assistantId={assistant.id}
                view={detailsView}
                embedded
              />
            </div>
          </EditorSidebar>
        )}
        {actionError && (
          <div className="panel-inset py-2">
            <ConfigPanelErrorCallout message={actionError} />
          </div>
        )}
        {selectionError || sessionError ? (
          <div className="panel-inset py-6">
            <ConfigPanelErrorCallout message={selectionError || sessionError} />
            <Button onClick={retry}>{t("common.refresh")}</Button>
          </div>
        ) : !assistantId ? (
          <div className="assistant-workspace-welcome">
            <EmptyState
              illustration="welcome"
              title={t("assistants.workspaceTitle")}
              description={t("assistants.workspaceWelcome")}
              action={
                canWrite && (
                  <Button
                    variant="primary"
                    leftIcon={<MessageSquare size={16} />}
                    disabled={busy}
                    onClick={() => void openChief()}
                  >
                    {t("assistants.startWithChief")}
                  </Button>
                )
              }
            />
          </div>
        ) : !assistant ? (
          <PanelLoadingState />
        ) : (
          <Suspense fallback={<PanelLoadingState />}>
            {view === "chat" ? (
              sessionId &&
              (sessionId === assistant.session_id ||
                verifiedSession?.key === `${assistant.id}:${sessionId}`) ? (
                <AssistantGroupContext assistant={assistant}>
                  <EmbeddedHeaderActionsContext.Provider
                    value={headerActionsTarget}
                  >
                    <ChatAppContent
                      key={`${assistant.id}:${sessionId}`}
                      embedded
                      showProfileModal={false}
                      onCloseProfileModal={noop}
                      sidebarCollapsed
                      setSidebarCollapsed={noop}
                      mobileSidebarOpen={false}
                      setMobileSidebarOpen={noop}
                      onShowProfile={noop}
                    />
                  </EmbeddedHeaderActionsContext.Provider>
                </AssistantGroupContext>
              ) : (
                <PanelLoadingState />
              )
            ) : view === "tasks" ? (
              <AssistantTasksDialog
                key={assistant.id}
                embedded
                assistant={assistant}
                canWrite={canWrite}
                onClose={noop}
              />
            ) : view === "discussions" ? (
              <AssistantDiscussionsDialog
                key={assistant.id}
                embedded
                assistant={assistant}
                onClose={noop}
              />
            ) : view === "rules" &&
              hasPermission(Permission.SCHEDULED_TASK_READ) ? (
              <AssistantRulesDialog
                key={assistant.id}
                embedded
                assistant={assistant}
                canWrite={
                  canWrite && hasPermission(Permission.SCHEDULED_TASK_WRITE)
                }
                onClose={noop}
              />
            ) : view === "memory" || view === "usage" ? (
              <AssistantDataPage
                key={`${assistant.id}:${view}`}
                assistantId={assistant.id}
                view={view}
                embedded
              />
            ) : (
              <div className="panel-inset py-6">
                <ConfigPanelErrorCallout
                  message={t("assistants.workspaceUnavailable")}
                />
              </div>
            )}
          </Suspense>
        )}
      </div>
      {canWrite && addMenuPosition && (
        <ResourceCardMenu
          id="assistant-add-menu"
          title={t("assistants.addCompanion")}
          position={addMenuPosition}
          anchorRef={addAnchor}
          onClose={(restore = true) => {
            setAddMenuPosition(null);
            if (restore) addAnchor.current?.focus();
          }}
          actions={[
            {
              label: t("assistants.create"),
              icon: <Plus size={16} />,
              onClick: () => setEditor("new"),
            },
            {
              label: t("assistants.createGroup"),
              icon: <Users size={16} />,
              onClick: () => setEditor("group"),
            },
          ]}
        />
      )}
      {(editor === "group" ||
        (typeof editor === "object" && editor?.kind === "group")) && (
        <AssistantGroupEditor
          key={typeof editor === "object" ? editor?.id : "new-group"}
          value={typeof editor === "object" ? editor ?? undefined : undefined}
          onClose={() => setEditor(null)}
          onSaved={(id) => {
            setEditor(null);
            setRefresh((x) => x + 1);
            navigate(`/assistants/${encodeURIComponent(id)}`);
          }}
        />
      )}
      {editor &&
        editor !== "group" &&
        (editor === "new" || editor.kind !== "group") && (
          <AssistantEditor
            key={editor === "new" ? "new-assistant" : editor.id}
            value={editor === "new" ? undefined : editor}
            onClose={() => setEditor(null)}
            onSaved={(id) => {
              setEditor(null);
              retry();
              navigate(`/assistants/${encodeURIComponent(id)}`);
            }}
          />
        )}
    </div>
  );
}
