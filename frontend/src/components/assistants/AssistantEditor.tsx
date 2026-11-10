import { AssistantProfileFields } from "./AssistantProfileFields";
import { AssistantConfigurationFields } from "./AssistantConfigurationFields";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { assistantApi } from "../../services/api/assistant";
import { assistantConfiguration, type Assistant } from "../../types/assistant";
import { AgentAvatar } from "../common/AgentAvatar";
import { EditorSidebar } from "../common/EditorSidebar";
import { Button, FormField, Input, Textarea } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

export function AssistantEditor({
  value,
  onClose,
  onSaved,
}: {
  value?: Assistant;
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const [saved, setSaved] = useState(value);
  const [draft, setDraft] = useState(() => assistantConfiguration(value));
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (busyRef.current || uploading) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const data = { ...draft, name: draft.name.trim() };
      const result = saved
        ? await assistantApi.update(saved.id, {
            ...data,
            revision: saved.revision,
            status: saved.status,
          })
        : await assistantApi.create(data);
      onSaved(result.id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const reload = async () => {
    if (!saved || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const current = await assistantApi.get(saved.id);
      setSaved(current);
      setDraft(assistantConfiguration(current));
      setError("");
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : t("common.loadFailed"),
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return (
    <EditorSidebar
      open
      onClose={() => {
        if (!busyRef.current) onClose();
      }}
      title={t(saved ? "assistants.edit" : "assistants.create")}
      icon={
        <AgentAvatar
          avatar={saved?.avatar}
          seed={saved?.name || t("assistants.create")}
          size={24}
        />
      }
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button disabled={busy} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            type="submit"
            form={formId}
            loading={busy}
            disabled={
              uploading ||
              !draft.name.trim() ||
              (draft.sandbox === "local" && !draft.workspace)
            }
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <form
        id={formId}
        className="es-form assistant-editor-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        {error && (
          <>
            <ConfigPanelErrorCallout message={error} />
            {saved && (
              <Button onClick={() => void reload()} disabled={busy}>
                {t("assistants.reloadSaved")}
              </Button>
            )}
          </>
        )}
        <fieldset disabled={busy} className="min-w-0 space-y-4">
          <FormField label={t("assistants.name")} required>
            <Input
              autoFocus
              required
              maxLength={80}
              value={draft.name}
              onChange={(event) =>
                setDraft({ ...draft, name: event.target.value })
              }
            />
          </FormField>
          <AssistantProfileFields
            key={saved?.revision ?? "new"}
            draft={draft}
            setDraft={setDraft}
            onUploadingChange={setUploading}
          />
          <FormField
            label={t("assistants.instructions")}
            hint={t("assistants.instructionsHint")}
          >
            <Textarea
              rows={5}
              maxLength={20000}
              value={draft.instructions}
              onChange={(event) =>
                setDraft({ ...draft, instructions: event.target.value })
              }
            />
          </FormField>
          <AssistantConfigurationFields draft={draft} setDraft={setDraft} />
        </fieldset>
      </form>
    </EditorSidebar>
  );
}
