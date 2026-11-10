import { useTranslation } from "react-i18next";
import { StartBackgroundTaskItem } from "./StartBackgroundTaskItem";
import type { ToolDetailProps } from "./ToolLivePanelContent";

export function DelegateAssistantTaskItem(
  props: ToolDetailProps & { id?: string },
) {
  const { t } = useTranslation();
  return (
    <StartBackgroundTaskItem
      {...props}
      title={t("assistants.tools.delegate_assistant_task")}
    />
  );
}
