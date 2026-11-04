import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Archive, Bot, Pencil, Plus, RefreshCw } from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import { assistantApi } from "../../services/api/assistant";
import {
  assistantConfiguration,
  type Assistant,
  type AssistantStatus,
} from "../../types/assistant";
import { PanelHeader } from "../common/PanelHeader";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { EmptyState } from "../common/EmptyState";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { Button, Select } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { AssistantDataPage } from "./AssistantDataPage";
import { AssistantEditor } from "./AssistantEditor";
import { AssistantDiscussionsDialog } from "./AssistantDiscussionsDialog";
import { AssistantRulesDialog } from "./AssistantRulesDialog";
import { AssistantTasksDialog } from "./AssistantTasksDialog";

const PAGE_SIZE = 20;

export function AssistantsPanel() {
  const { assistantId } = useParams();
  const { pathname } = useLocation();
  const view = pathname.endsWith("/usage") ? "usage" : "memory";
  return assistantId ? (
    <AssistantDataPage
      key={`${assistantId}:${view}`}
      assistantId={assistantId}
      view={view}
    />
  ) : (
    <AssistantList />
  );
}

function AssistantList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(Permission.CHAT_WRITE);
  const [page, setPage] = useState(1);
  const [archived, setArchived] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{
    assistants: Assistant[];
    total: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState<Assistant | "new" | null>(null);
  const [discussions, setDiscussions] = useState<Assistant | null>(null);
  const [rules, setRules] = useState<Assistant | null>(null);
  const [tasks, setTasks] = useState<Assistant | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void assistantApi
      .list((page - 1) * PAGE_SIZE, PAGE_SIZE, archived)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
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

  const act = async (assistant: Assistant, status?: AssistantStatus) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(assistant.id);
    setError("");
    try {
      if (status) {
        await assistantApi.update(assistant.id, {
          ...assistantConfiguration(assistant),
          revision: assistant.revision,
          status,
        });
        setRefresh((old) => old + 1);
      } else {
        const session = await assistantApi.openConversation(assistant.id);
        navigate(`/chat/${encodeURIComponent(session.id)}`);
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  };

  return (
    <>
      <PanelHeader
        title={t("assistants.title")}
        subtitle={t("assistants.subtitle")}
        count={data?.total}
        icon={<Bot size={20} />}
        actions={
          <>
            <Select
              ariaLabel={t("assistants.filter")}
              value={archived ? "archived" : "current"}
              options={[
                { value: "current", label: t("assistants.current") },
                { value: "archived", label: t("assistants.archived") },
              ]}
              onChange={(value) => {
                setArchived(value === "archived");
                setPage(1);
                setData(null);
              }}
            />
            <Button
              leftIcon={<RefreshCw size={16} />}
              disabled={loading}
              onClick={() => setRefresh((old) => old + 1)}
            >
              {t("common.refresh")}
            </Button>
            {canWrite && (
              <Button
                variant="primary"
                leftIcon={<Plus size={16} />}
                onClick={() => setEditor("new")}
              >
                {t("assistants.create")}
              </Button>
            )}
          </>
        }
      />
      <div className="panel-body min-h-0 flex-1 overflow-y-auto">
        {error && <ConfigPanelErrorCallout message={error} className="mb-4" />}
        {loading && !data ? (
          <PanelLoadingState />
        ) : data?.assistants.length ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.assistants.map((assistant) => (
              <SkillBaseCard
                key={assistant.id}
                title={assistant.name}
                description={
                  assistant.instructions || t("assistants.noInstructions")
                }
                icon={<Bot size={24} />}
                muted={assistant.status !== "active"}
                meta={<span>{t(`assistants.${assistant.status}`)}</span>}
                actions={
                  canWrite
                    ? [
                        {
                          label: t("assistants.edit"),
                          icon: <Pencil size={14} />,
                          onClick: () => setEditor(assistant),
                          disabled: busy !== null,
                        },
                        {
                          label: t(
                            assistant.status === "active"
                              ? "assistants.pause"
                              : "assistants.resume",
                          ),
                          onClick: () =>
                            void act(
                              assistant,
                              assistant.status === "active"
                                ? "paused"
                                : "active",
                            ),
                          disabled: busy !== null,
                        },
                        ...(assistant.status !== "archived"
                          ? [
                              {
                                label: t("assistants.archive"),
                                icon: <Archive size={14} />,
                                onClick: () => void act(assistant, "archived"),
                                disabled: busy !== null,
                              },
                            ]
                          : []),
                      ]
                    : []
                }
                extraContent={
                  <div className="space-y-2">
                    <p className="text-12 text-theme-text-secondary">
                      {t("assistants.pauseHint")}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {canWrite && (
                        <Button
                          variant="primary"
                          loading={busy === assistant.id}
                          disabled={
                            busy !== null || assistant.status !== "active"
                          }
                          onClick={() => void act(assistant)}
                        >
                          {t("assistants.open")}
                        </Button>
                      )}
                      <Button
                        onClick={() =>
                          navigate(
                            `/chat/${encodeURIComponent(assistant.session_id)}`,
                          )
                        }
                      >
                        {t("assistants.history")}
                      </Button>
                      <Button onClick={() => setDiscussions(assistant)}>
                        {t("assistants.discussions")}
                      </Button>
                      {hasPermission(Permission.SCHEDULED_TASK_READ) && (
                        <Button onClick={() => setRules(assistant)}>
                          {t("assistants.rules")}
                        </Button>
                      )}
                      <Button onClick={() => setTasks(assistant)}>
                        {t("assistants.tasks")}
                      </Button>
                      {hasPermission(Permission.USAGE_READ) && (
                        <Button
                          onClick={() =>
                            navigate(
                              `/assistants/${encodeURIComponent(
                                assistant.id,
                              )}/usage`,
                            )
                          }
                        >
                          {t("assistants.usage")}
                        </Button>
                      )}
                      {hasPermission(Permission.MEMORY_READ) && (
                        <Button
                          onClick={() =>
                            navigate(
                              `/assistants/${encodeURIComponent(
                                assistant.id,
                              )}/memory`,
                            )
                          }
                        >
                          {t("assistants.memory")}
                        </Button>
                      )}
                    </div>
                  </div>
                }
              />
            ))}
          </div>
        ) : (
          !error &&
          !loading && (
            <EmptyState
              icon={<Bot size={20} />}
              title={t(
                archived ? "assistants.emptyArchived" : "assistants.empty",
              )}
              description={t("assistants.emptyHint")}
            />
          )
        )}
      </div>
      <div className="panel-pagination">
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={data?.total ?? 0}
          onChange={(next) => {
            setPage(next);
            setData(null);
          }}
        />
      </div>
      {editor && (
        <AssistantEditor
          value={editor === "new" ? undefined : editor}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            setRefresh((old) => old + 1);
          }}
        />
      )}
      {discussions && (
        <AssistantDiscussionsDialog
          key={discussions.id}
          assistant={discussions}
          onClose={() => setDiscussions(null)}
        />
      )}
      {rules && (
        <AssistantRulesDialog
          key={rules.id}
          assistant={rules}
          canWrite={canWrite && hasPermission(Permission.SCHEDULED_TASK_WRITE)}
          onClose={() => setRules(null)}
        />
      )}
      {tasks && (
        <AssistantTasksDialog
          assistant={tasks}
          canWrite={canWrite}
          onClose={() => setTasks(null)}
        />
      )}
    </>
  );
}
