import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import type { Assistant } from "../../types/assistant";
import { assistantApi } from "../../services/api/assistant";
import { Button } from "../common/ui";
import { Tooltip } from "../common/Tooltip";
import { AssistantGroupEditor } from "./AssistantGroupEditor";
import { AssistantEditor } from "./AssistantEditor";
import { AssistantTasksDialog } from "./AssistantTasksDialog";

export function AssistantConversationBar({
  sessionId,
  onResolved,
}: {
  sessionId: string;
  onResolved?: (sessionId: string, assistant: Assistant | null) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(Permission.CHAT_WRITE);
  const [loaded, setLoaded] = useState<{
    sessionId: string;
    assistant: Assistant | null;
    error?: string;
  } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState<"edit" | "tasks" | null>(null);
  const current = loaded?.sessionId === sessionId ? loaded : null;
  useEffect(() => {
    let active = true;
    let sequence = 0;
    const load = () => {
      const request = ++sequence;
      void assistantApi
        .forConversation(sessionId)
        .then((assistant) => {
          if (active && request === sequence) {
            setLoaded({ sessionId, assistant });
            onResolved?.(sessionId, assistant);
          }
        })
        .catch((failure: unknown) => {
          if (active && request === sequence)
            setLoaded({
              sessionId,
              assistant: null,
              error:
                failure instanceof Error
                  ? failure.message
                  : t("common.loadFailed"),
            });
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
  }, [sessionId, refresh, t, onResolved]);
  if (current?.error)
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-2 px-4 py-2 text-12 text-theme-error"
      >
        {current.error}
        <Button onClick={() => setRefresh((value) => value + 1)}>
          {t("common.refresh")}
        </Button>
      </div>
    );
  const assistant = current?.assistant;
  if (!assistant) return null;
  // The dedicated workspace already provides assistant navigation and settings.
  if (pathname.startsWith("/assistants/")) return null;
  const contextSessionId = assistant.context_session_id || sessionId;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-theme-border px-4 py-1.5">
      <Tooltip
        placement="bottom"
        align="start"
        content={t(
          assistant.context_kind === "task"
            ? "assistants.taskConfigurationHint"
            : assistant.session_id === contextSessionId
              ? "assistants.configurationHint"
              : "assistants.discussionHint",
        )}
      >
        <div
          tabIndex={0}
          className="flex min-w-0 max-w-full items-center gap-2 rounded-md py-1 text-14 outline-none focus-visible:ring-2 focus-visible:ring-theme-primary"
        >
          <Bot size={16} className="shrink-0 text-theme-text-secondary" />
          <strong
            className="min-w-0 truncate font-medium"
            title={assistant.name}
          >
            {assistant.name}
          </strong>
          <span className="shrink-0 text-12 text-theme-text-secondary">
            {t(`assistants.${assistant.status}`)}
          </span>
        </div>
      </Tooltip>
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        <Button variant="ghost" size="sm" onClick={() => setDialog("tasks")}>
          {t("assistants.tasks")}
        </Button>
        {hasPermission(Permission.MEMORY_READ) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              navigate(
                `/assistants/${encodeURIComponent(assistant.id)}/memory${
                  assistant.session_id === contextSessionId
                    ? ""
                    : `?discussion=${encodeURIComponent(contextSessionId)}`
                }`,
              )
            }
          >
            {t("assistants.memory")}
          </Button>
        )}
        {canWrite && (
          <Button variant="ghost" size="sm" onClick={() => setDialog("edit")}>
            {t("assistants.edit")}
          </Button>
        )}
      </div>
      {dialog === "tasks" && (
        <AssistantTasksDialog
          key={assistant.id}
          assistant={assistant}
          canWrite={canWrite}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "edit" && assistant.kind === "group" && (
        <AssistantGroupEditor
          key={assistant.id}
          value={assistant}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            setRefresh((value) => value + 1);
          }}
        />
      )}
      {dialog === "edit" && assistant.kind !== "group" && (
        <AssistantEditor
          key={assistant.id}
          value={assistant}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            setRefresh((value) => value + 1);
          }}
        />
      )}
    </div>
  );
}
