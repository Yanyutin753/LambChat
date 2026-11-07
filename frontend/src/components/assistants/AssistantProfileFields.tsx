import { useState, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { AssistantConfiguration } from "../../types/assistant";
import { FormField, Textarea } from "../common/ui";
import { AvatarSection } from "../persona/PersonaEditorAvatarSection";
import { StarterPromptsEditor } from "../persona/PersonaEditorStarterPrompts";
import {
  draftRowsToStarterPrompts,
  starterPromptsToDraftRows,
} from "../persona/personaPresetEditor";

export function AssistantProfileFields({
  draft,
  setDraft,
  onUploadingChange,
}: {
  draft: AssistantConfiguration;
  setDraft: Dispatch<SetStateAction<AssistantConfiguration>>;
  onUploadingChange: (uploading: boolean) => void;
}) {
  const { t } = useTranslation();
  const [prompts, setPrompts] = useState(() =>
    starterPromptsToDraftRows(draft.starter_prompts),
  );
  return (
    <>
      <AvatarSection
        avatar={draft.avatar || ""}
        onAvatarChange={(avatar) =>
          setDraft((previous) => ({ ...previous, avatar }))
        }
        onUploadingChange={onUploadingChange}
      />
      <FormField label={t("personaPresets.description")}>
        <Textarea
          rows={2}
          maxLength={500}
          value={draft.description || ""}
          onChange={(event) =>
            setDraft((previous) => ({
              ...previous,
              description: event.target.value,
            }))
          }
        />
      </FormField>
      <StarterPromptsEditor
        prompts={prompts}
        onChange={(updater) => {
          const next = updater(prompts);
          setPrompts(next);
          setDraft((previous) => ({
            ...previous,
            starter_prompts: draftRowsToStarterPrompts(next),
          }));
        }}
      />
    </>
  );
}
