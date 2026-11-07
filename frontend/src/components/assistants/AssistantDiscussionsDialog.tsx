import { PanelHeader } from "../common/PanelHeader";
import { EmptyState } from "../common/EmptyState";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import { assistantApi } from "../../services/api/assistant";
import type { Assistant, AssistantDiscussion } from "../../types/assistant";
import { AssistantSurface } from "./AssistantSurface";
import { Pagination } from "../common/Pagination";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { Button } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

const PAGE_SIZE = 10;

export function AssistantDiscussionsDialog({
  assistant,
  onClose,
  embedded = false,
}: {
  assistant: Assistant;
  onClose: () => void;
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{
    discussions: AssistantDiscussion[];
    total: number;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    void assistantApi
      .discussions(assistant.id, (page - 1) * PAGE_SIZE, PAGE_SIZE)
      .then((value) => {
        if (active) {
          setData(value);
          setTotal(value.total);
        }
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error ? failure.message : t("common.loadFailed"),
          );
      });
    return () => {
      active = false;
    };
  }, [assistant.id, page, refresh, t]);
  const open = (path: string) => {
    onClose();
    navigate(path);
  };
  return (
    <AssistantSurface
      embedded={embedded}
      open
      onClose={onClose}
      title={t("assistants.discussionsTitle", { name: assistant.name })}
      size="lg"
      footer={
        <>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={(next) => {
              setData(null);
              setPage(next);
            }}
          />
          <Button onClick={() => setRefresh((value) => value + 1)}>
            {t("common.refresh")}
          </Button>
        </>
      }
    >
      {embedded && (
        <PanelHeader
          className="!px-0"
          title={t("assistants.discussions")}
          count={total}
        />
      )}
      {error && <ConfigPanelErrorCallout message={error} />}
      {!data && !error ? (
        <PanelLoadingState />
      ) : data?.discussions.length === 0 ? (
        <EmptyState
          illustration="panel-channels"
          title={t("assistants.discussions")}
          description={t("assistants.noDiscussions")}
          action={
            <Button
              onClick={() =>
                open(`/assistants/${encodeURIComponent(assistant.id)}`)
              }
            >
              {t("assistants.openConversation")}
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-theme-border">
          {data?.discussions.map((discussion) => (
            <li key={discussion.session_id} className="space-y-2 py-3">
              <p className="break-words font-medium">{discussion.chat_id}</p>
              <p className="text-12 text-theme-text-secondary">
                {discussion.channel_type}
              </p>
              {!discussion.available && (
                <p className="text-12 text-theme-text-secondary">
                  {t("assistants.discussionUnavailable")}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() =>
                    open(
                      `/assistants/${encodeURIComponent(
                        assistant.id,
                      )}/chat/${encodeURIComponent(discussion.session_id)}`,
                    )
                  }
                >
                  {t("assistants.history")}
                </Button>
                {hasPermission(Permission.MEMORY_READ) && (
                  <Button
                    disabled={!discussion.available}
                    onClick={() =>
                      open(
                        `/assistants/${encodeURIComponent(
                          assistant.id,
                        )}/memory?discussion=${encodeURIComponent(
                          discussion.session_id,
                        )}`,
                      )
                    }
                  >
                    {t("assistants.memory")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-12 text-theme-text-secondary">
        {t("assistants.discussionHint")}
      </p>
    </AssistantSurface>
  );
}
