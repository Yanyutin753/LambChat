import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import type { Assistant } from "../../types/assistant";
import { assistantApi } from "../../services/api/assistant";
import { Button } from "../common/ui";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { UsagePanel } from "../panels/UsagePanel";
import { MemoryPanel } from "../panels/MemoryPanel";

export function AssistantDataPage({
  assistantId,
  view,
  embedded = false,
}: {
  assistantId: string;
  view: "memory" | "usage";
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const discussionId = searchParams.get("discussion") || undefined;
  const { hasPermission } = useAuth();
  const [assistant, setAssistant] = useState<Assistant | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    let sequence = 0;
    const load = () => {
      const request = ++sequence;
      void assistantApi
        .get(assistantId)
        .then((value) => {
          if (active && request === sequence) {
            setAssistant(value);
            setError("");
          }
        })
        .catch((failure: unknown) => {
          if (active && request === sequence) {
            setAssistant(null);
            setError(
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
  return (
    <div
      data-panel="assistant-data"
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      {!embedded && (
        <div className="panel-inset flex flex-wrap items-center gap-3 py-3">
          <Button onClick={() => navigate("/assistants")}>
            {t("common.back")}
          </Button>
          {assistant && (
            <div className="min-w-0">
              <strong className="break-words font-medium">
                {assistant.name}
              </strong>
              <p className="text-12 text-theme-text-secondary">
                {t(
                  view === "usage"
                    ? "assistants.usageHint"
                    : discussionId
                      ? "assistants.discussionMemory"
                      : assistant.memory_mode === "project"
                        ? "assistants.projectMemory"
                        : "assistants.privateMemory",
                )}
              </p>
            </div>
          )}
        </div>
      )}
      {embedded && assistant && view === "memory" && (
        <p className="panel-inset pt-3 text-12 text-theme-text-secondary">
          {t(
            discussionId
              ? "assistants.discussionMemory"
              : assistant.memory_mode === "project"
                ? "assistants.projectMemory"
                : "assistants.privateMemory",
          )}
        </p>
      )}
      {error ? (
        <div className="panel-inset">
          <ConfigPanelErrorCallout message={error} />
          <Button onClick={() => setRefresh((value) => value + 1)}>
            {t("common.refresh")}
          </Button>
        </div>
      ) : !assistant ? (
        <PanelLoadingState />
      ) : hasPermission(
          view === "usage" ? Permission.USAGE_READ : Permission.MEMORY_READ,
        ) ? (
        view === "usage" ? (
          <UsagePanel key={assistant.id} assistantId={assistant.id} />
        ) : (
          <MemoryPanel
            key={`${assistant.id}:${assistant.memory_mode}:${
              assistant.project_id
            }:${discussionId ?? ""}`}
            assistantId={assistant.id}
            discussionId={discussionId}
          />
        )
      ) : (
        <div className="panel-inset">
          <ConfigPanelErrorCallout
            message={t(
              view === "usage"
                ? "assistants.usagePermissionRequired"
                : "assistants.memoryPermissionRequired",
            )}
          />
        </div>
      )}
    </div>
  );
}
