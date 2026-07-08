import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  ArrowLeft,
  Bot,
  ChevronRight,
  MessageSquare,
} from "lucide-react";
import { PanelHeader } from "../../common/PanelHeader";
import { Pagination } from "../../common/Pagination";
import { TaskSessionListSkeleton } from "../../skeletons";
import { scheduledTaskApi } from "../../../services/api/scheduledTask";
import { agentApi } from "../../../services/api/agent";
import type { TaskSession } from "../../../types/scheduledTask";
import type { AgentInfo } from "../../../types/agent";
import { formatDateTimeShort } from "../../../utils/datetime";

export function TaskSessionList({
  taskId,
  taskName,
  onBack,
}: {
  taskId: string;
  taskName: string;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TaskSession[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const limit = 20;

  useEffect(() => {
    agentApi
      .list()
      .then((res) => setAgents(res.agents))
      .catch(() => {});
  }, []);

  const fetchSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      const sessionResponse = await scheduledTaskApi.getSessions(
        taskId,
        skip,
        limit,
      );
      setSessions(sessionResponse.items);
      setTotal(sessionResponse.total);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [taskId, skip, t]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleSessionClick = (sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  };

  if (isLoading && sessions.length === 0) {
    return <TaskSessionListSkeleton />;
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      <PanelHeader
        title={taskName}
        subtitle={t("scheduledTask.sessionsSubtitle")}
        icon={
          <MessageSquare
            size={20}
            className="text-stone-600 dark:text-stone-400"
          />
        }
        actions={
          <button
            onClick={onBack}
            className="scheduled-task-button scheduled-task-button--secondary"
          >
            <ArrowLeft size={16} />
            {t("scheduledTask.backToTasks")}
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-3 sm:p-6">
        {sessions.length === 0 ? (
          <div className="scheduled-task-empty-state">
            <div className="scheduled-task-empty-state__icon">
              <MessageSquare size={32} />
            </div>
            <p className="scheduled-task-empty-state__title">
              {t("scheduledTask.noSessions")}
            </p>
            <p className="scheduled-task-empty-state__body">
              {t("scheduledTask.noSessionsDesc")}
            </p>
          </div>
        ) : (
          <div className="scheduled-task-list">
            {sessions.map((session) => {
              const agentName =
                agents.find((agent) => agent.id === session.agent_id)?.name ??
                session.agent_id;

              return (
                <button
                  key={session.id}
                  onClick={() => handleSessionClick(session.id)}
                  className="glass-card scheduled-task-session-card w-full text-left"
                >
                  <div
                    className={`scheduled-task-session-card__indicator ${
                      session.is_active
                        ? "scheduled-task-session-card__indicator--active"
                        : ""
                    }`}
                  >
                    <MessageSquare size={16} />
                  </div>

                  <div className="scheduled-task-session-card__body">
                    <p className="scheduled-task-session-card__title">
                      {session.name || t("scheduledTask.untitledSession")}
                    </p>
                    <div className="scheduled-task-session-card__meta">
                      {agentName && (
                        <>
                          <span className="inline-flex items-center gap-1">
                            <Bot size={10} />
                            {t(agentName)}
                          </span>
                          {session.created_at && (
                            <>
                              <span className="scheduled-task-session-card__meta-separator">
                                /
                              </span>
                              <span>
                                {formatDateTimeShort(session.created_at)}
                              </span>
                            </>
                          )}
                        </>
                      )}
                      {!agentName && session.created_at && (
                        <span>{formatDateTimeShort(session.created_at)}</span>
                      )}
                    </div>
                  </div>

                  <div className="scheduled-task-session-card__trail">
                    {session.unread_count > 0 && (
                      <span className="scheduled-task-session-card__unread">
                        {session.unread_count > 99
                          ? "99+"
                          : session.unread_count}
                      </span>
                    )}
                    <ChevronRight
                      size={16}
                      className="text-stone-300 dark:text-stone-600"
                    />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {total > limit && (
        <div className="glass-divider bg-transparent px-4 py-4 sm:px-6">
          <Pagination
            page={Math.floor(skip / limit) + 1}
            pageSize={limit}
            total={total}
            onChange={(page) => setSkip((page - 1) * limit)}
          />
        </div>
      )}
    </div>
  );
}
