import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../common/ui";
import { assistantApi } from "../../services/api/assistant";
import type { Assistant } from "../../types/assistant";
export type GroupMember = {
  id: string;
  name: string;
  status: string;
  avatar?: string | null;
};
const Context = createContext<GroupMember[] | null>(null);
// eslint-disable-next-line react-refresh/only-export-components
export const useAssistantGroupMembers = () => useContext(Context);
export function AssistantGroupContext({
  assistant,
  children,
}: {
  assistant: Assistant;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [retry, setRetry] = useState(0);
  const [loaded, setLoaded] = useState<{
    id: string;
    revision: number;
    members: GroupMember[];
    failed?: boolean;
  } | null>(null);
  useEffect(() => {
    let active = true;
    if (assistant.kind !== "group") return;
    void assistantApi
      .members(assistant.id)
      .then((result) => {
        if (active)
          setLoaded({
            id: assistant.id,
            revision: assistant.revision,
            members: result.members,
          });
      })
      .catch(() => {
        if (active)
          setLoaded({
            id: assistant.id,
            revision: assistant.revision,
            members: [],
            failed: true,
          });
      });
    return () => {
      active = false;
    };
  }, [assistant.id, assistant.kind, assistant.revision, retry]);
  return (
    <Context.Provider
      value={
        assistant.kind === "group"
          ? loaded?.id === assistant.id &&
            loaded.revision === assistant.revision
            ? loaded.members
            : []
          : null
      }
    >
      {assistant.kind === "group" &&
        loaded?.id === assistant.id &&
        loaded.failed && (
          <div
            role="alert"
            className="flex items-center gap-2 px-4 py-2 text-13 text-theme-error"
          >
            {t("common.loadFailed")}
            <Button onClick={() => setRetry((value) => value + 1)}>
              {t("common.refresh")}
            </Button>
          </div>
        )}
      {children}
    </Context.Provider>
  );
}
