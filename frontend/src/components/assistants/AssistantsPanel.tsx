import { ChatHeaderFrame } from "../layout/AppContent/ChatHeaderFrame";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
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
import { AssistantDataPage } from "./AssistantDataPage";
import { Dialog } from "../common/Dialog";
import { AssistantGroupEditor } from "./AssistantGroupEditor";
import { AssistantGroupContext } from "./AssistantGroupContext";
import { AssistantEditor } from "./AssistantEditor";
import { AssistantDiscussionsDialog } from "./AssistantDiscussionsDialog";
import { AssistantRulesDialog } from "./AssistantRulesDialog";
import { AssistantTaskContext } from "./AssistantTaskContext";
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
  const [editor, setEditor] = useState<
    Assistant | "new" | "group" | "choose" | null
  >(null);
  const [profiles, setProfiles] = useState<Record<string, AssistantProfile>>(
    {},
  );
  const canReadPersonas = hasPermission(Permission.PERSONA_PRESET_READ);
  const canReadTeams = hasPermission(Permission.TEAM_READ);
  const [collapsed, setCollapsed] = useState(false);
  const [headerActionsTarget, setHeaderActionsTarget] =
    useState<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
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
      navigate(`/assistants/${encodeURIComponent(value.id)}`);
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
  const currentProfile = assistant ? profileFor(assistant) : undefined;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setListError("");
    void assistantApi
      .list((page - 1) * PAGE_SIZE, PAGE_SIZE, archived)
      .then((result) => {
        if (active) {
          setData(result.assistants);
          setTotal(result.total);
        }
      })
      .catch((failure: unknown) => {
        if (active)
          setListError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, archived, refresh, t]);

  useEffect(() => {
    let active = true;
    const update = () => {
      void assistantApi
        .list((page - 1) * PAGE_SIZE, PAGE_SIZE, archived)
        .then((result) => {
          if (active) {
            setData(result.assistants);
            setTotal(result.total);
          }
        })
        .catch(() => {});
    };
    window.addEventListener("assistants:changed", update);
    return () => {
      active = false;
      window.removeEventListener("assistants:changed", update);
    };
  }, [page, archived]);

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
    return () => {
      active = false;
      window.removeEventListener("focus", load);
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
  const taskConversation =
    view === "chat" &&
    verifiedSession?.key === `${assistantId}:${sessionId}` &&
    verifiedSession.kind === "task";
  const openView = (id: string) =>
    navigate(id === "chat" ? base : `${base}/${id}`);
  const retry = () => setRefresh((old) => old + 1);

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
        <div className="assistant-workspace-sidebar-top">
          <Button
            variant="ghost"
            leftIcon={<ArrowLeft size={16} />}
            onClick={() => navigate("/chat")}
          >
            {t("assistants.backToChat")}
          </Button>
          <Button
            variant="ghost"
            aria-label={t("common.refresh")}
            title={t("common.refresh")}
            disabled={loading}
            onClick={retry}
          >
            <RefreshCw size={16} />
          </Button>
        </div>
        {canWrite && (
          <div className="px-3 pb-5">
            <Button
              className="assistant-workspace-create"
              variant="ghost"
              leftIcon={<Pencil size={16} />}
              onClick={() => setEditor("choose")}
            >
              {t("assistants.newChat")}
            </Button>
          </div>
        )}
        {canWrite && !archived && (
          <button
            type="button"
            className="assistant-chief"
            aria-current={assistant?.kind === "chief" ? "page" : undefined}
            disabled={busy}
            onClick={() => void openChief()}
          >
            <AgentAvatar seed="Chief" size={48} />
            <span>
              <strong>Chief</strong>
              <span>{t("assistants.chiefHint")}</span>
            </span>
          </button>
        )}
        {actionError && !assistant && (
          <ConfigPanelErrorCallout message={actionError} />
        )}
        <div className="assistant-workspace-sidebar-heading">
          <h1>{t(archived ? "assistants.archived" : "assistants.current")}</h1>
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
                      onClick={() =>
                        navigate(`/assistants/${encodeURIComponent(item.id)}`)
                      }
                      title={item.name}
                    >
                      <AgentAvatar
                        avatar={profileFor(item)?.avatar}
                        seed={profileFor(item)?.seed || item.name}
                        size={32}
                      />
                      <span className="min-w-0 flex-1 text-left">
                        <span className="block truncate font-medium">
                          {item.name}
                        </span>
                        <span className="assistant-workspace-role block truncate">
                          {(item.kind === "group"
                            ? t("assistants.groupCount", {
                                count: item.member_ids?.length ?? 0,
                              })
                            : profileFor(item)?.name) ||
                            t(
                              item.team_id
                                ? "assistants.team"
                                : "assistants.title",
                            )}
                        </span>
                      </span>
                      {item.status !== "active" && (
                        <span className="text-11 text-theme-text-secondary">
                          {t(`assistants.${item.status}`)}
                        </span>
                      )}
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
        <ChatHeaderFrame className="assistant-workspace-header">
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
            className="assistant-workspace-mobile-back"
            variant="ghost"
            aria-label={t("assistants.title")}
            onClick={() => navigate("/assistants")}
          >
            <SidebarToggleIcon className="size-4" />
          </Button>
          {assistant && (
            <AgentAvatar
              avatar={currentProfile?.avatar}
              seed={currentProfile?.seed || assistant.name}
              size={32}
            />
          )}
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <h2 className="min-w-0 truncate text-14 font-medium">
              {assistant ? (
                <button
                  type="button"
                  className="max-w-full truncate rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary"
                  aria-label={t("assistants.chatWith", {
                    name: assistant.name,
                  })}
                  onClick={() => openView("chat")}
                >
                  {assistant.name}
                </button>
              ) : (
                t("assistants.title")
              )}
            </h2>
            {assistant && (
              <p className="assistant-workspace-role hidden max-w-[40%] truncate sm:block">
                {assistant.status === "active" &&
                ["chat", "tasks"].includes(view)
                  ? currentProfile?.name
                  : t(
                      `assistants.${
                        assistant.status !== "active"
                          ? assistant.status
                          : navigation.find((item) => item.id === view)
                              ?.label || "conversation"
                      }`,
                    )}
              </p>
            )}
          </div>
          <div
            ref={setHeaderActionsTarget}
            className="assistant-workspace-header-actions"
          />
          {assistant?.kind === "group" && (
            <Button
              variant="ghost"
              aria-label={t("assistants.groupDetails")}
              onClick={() => setEditor(assistant)}
              disabled={!canWrite}
              leftIcon={<Users size={16} />}
            >
              <span className="hidden sm:inline">
                {t("assistants.groupCount", {
                  count: assistant.member_ids?.length ?? 0,
                })}
              </span>
            </Button>
          )}
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
                      onClick: () => openView(id),
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
                            disabled: busy,
                            onClick: () =>
                              void act(
                                assistant.status === "active"
                                  ? "paused"
                                  : "active",
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
        </ChatHeaderFrame>
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
                    leftIcon={<Plus size={16} />}
                    onClick={() => setEditor("choose")}
                  >
                    {t("assistants.create")}
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
                  {taskConversation && verifiedSession?.taskId && (
                    <AssistantTaskContext
                      key={`${assistant.id}:${sessionId}`}
                      assistantId={assistant.id}
                      taskId={verifiedSession.taskId}
                      sessionId={sessionId}
                      canWrite={canWrite}
                    />
                  )}
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
      {editor === "choose" && (
        <Dialog
          open
          onClose={() => setEditor(null)}
          title={t("assistants.newChat")}
        >
          <div className="space-y-2">
            <Button
              className="w-full justify-start"
              variant="ghost"
              leftIcon={<Plus size={16} />}
              onClick={() => setEditor("new")}
            >
              {t("assistants.create")}
            </Button>
            <Button
              className="w-full justify-start"
              variant="ghost"
              leftIcon={<Users size={16} />}
              onClick={() => setEditor("group")}
            >
              {t("assistants.createGroup")}
            </Button>
          </div>
        </Dialog>
      )}
      {(editor === "group" ||
        (typeof editor === "object" && editor?.kind === "group")) && (
        <AssistantGroupEditor
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
        editor !== "choose" &&
        editor !== "group" &&
        (editor === "new" || editor.kind !== "group") && (
          <AssistantEditor
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
