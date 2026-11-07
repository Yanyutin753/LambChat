import { AssistantProfileFields } from "./AssistantProfileFields";
import { AssistantConfigurationFields } from "./AssistantConfigurationFields";
import "../../styles/assistant-workspace.css";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Users } from "lucide-react";
import { assistantApi } from "../../services/api/assistant";
import {
  assistantConfiguration,
  type Assistant,
  type AssistantConfiguration,
} from "../../types/assistant";
import { EditorSidebar } from "../common/EditorSidebar";
import { AgentAvatar } from "../common/AgentAvatar";
import { Button, FormField, Input, Select, Textarea } from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";

export function AssistantGroupEditor({
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
  const [configuration, setConfiguration] = useState<AssistantConfiguration>(
    () => ({ ...assistantConfiguration(value), kind: "group" }),
  );
  const [uploading, setUploading] = useState(false);
  const [bots, setBots] = useState<Assistant[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState(value?.name ?? "");
  const [instructions, setInstructions] = useState(value?.instructions ?? "");
  const [members, setMembers] = useState(value?.member_ids ?? []);
  const [leader, setLeader] = useState(value?.leader_id ?? "");
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void (async () => {
      const all: Assistant[] = [];
      let skip = 0;
      while (active) {
        const page = await assistantApi.list(skip, 100);
        all.push(...page.assistants);
        skip += page.assistants.length;
        if (skip >= page.total || !page.assistants.length) break;
      }
      if (active)
        setBots(
          all.filter(
            (bot) =>
              bot.kind !== "group" &&
              !bot.team_id &&
              (bot.status === "active" || members.includes(bot.id)),
          ),
        );
    })()
      .catch((failure) => {
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
    // Membership edits do not reload the catalogue and erase the current selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, t]);
  const save = async () => {
    if (guard.current || uploading || loading || !leader || members.length < 2)
      return;
    guard.current = true;
    setBusy(true);
    setError("");
    try {
      const selected = bots.filter((bot) => members.includes(bot.id));
      const draft = {
        ...configuration,
        kind: "group" as const,
        name:
          name.trim() ||
          selected
            .map((bot) => bot.name)
            .join(" · ")
            .slice(0, 80),
        instructions,
        member_ids: members,
        leader_id: leader,
      };
      const result = saved
        ? await assistantApi.update(saved.id, {
            ...draft,
            status: saved.status,
            revision: saved.revision,
          })
        : await assistantApi.create(draft);
      onSaved(result.id);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : t("common.operationFailed"),
      );
    } finally {
      guard.current = false;
      setBusy(false);
    }
  };
  const reload = async () => {
    if (!saved || guard.current) return;
    guard.current = true;
    setBusy(true);
    try {
      const current = await assistantApi.get(saved.id);
      setSaved(current);
      setConfiguration(assistantConfiguration(current));
      setName(current.name);
      setInstructions(current.instructions);
      setMembers(current.member_ids ?? []);
      setLeader(current.leader_id ?? "");
      setError("");
      setRefresh((revision) => revision + 1);
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : t("common.loadFailed"),
      );
    } finally {
      guard.current = false;
      setBusy(false);
    }
  };
  return (
    <EditorSidebar
      open
      onClose={() => {
        if (!guard.current) onClose();
      }}
      title={t(value ? "assistants.groupDetails" : "assistants.createGroup")}
      icon={<Users size={16} aria-hidden="true" />}
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button disabled={busy} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            loading={busy}
            disabled={
              uploading ||
              (configuration.sandbox === "local" && !configuration.workspace) ||
              loading ||
              !leader ||
              members.length < 2 ||
              members.some(
                (id) =>
                  !bots.some((bot) => bot.id === id && bot.status === "active"),
              )
            }
          >
            {t(value ? "common.save" : "assistants.createGroup")}
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
              <Button disabled={busy} onClick={() => void reload()}>
                {t("assistants.reloadSaved")}
              </Button>
            )}
            <Button disabled={busy} onClick={() => setRefresh((x) => x + 1)}>
              {t("common.refresh")}
            </Button>
          </>
        )}
        {loading ? (
          <p role="status">{t("common.loading")}</p>
        ) : (
          <fieldset disabled={busy} className="space-y-5">
            <FormField label={t("assistants.name")}>
              <Input
                maxLength={80}
                value={name}
                placeholder={t("assistants.groupNameHint")}
                onChange={(event) => setName(event.target.value)}
              />
            </FormField>
            <AssistantProfileFields
              key={saved?.revision ?? "new"}
              draft={configuration}
              setDraft={setConfiguration}
              onUploadingChange={setUploading}
            />
            <FormField label={t("assistants.groupPurpose")}>
              <Textarea
                rows={3}
                maxLength={20000}
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
              />
            </FormField>
            <FormField label={t("assistants.groupLeader")}>
              <Select
                ariaLabel={t("assistants.groupLeader")}
                value={leader}
                placeholder={t("assistants.groupLeader")}
                disabled={busy}
                options={bots.map((bot) => ({
                  value: bot.id,
                  label: bot.name,
                  disabled:
                    bot.status !== "active" ||
                    (!members.includes(bot.id) && members.length >= 12),
                }))}
                onChange={(id) => {
                  setLeader(id);
                  setMembers((ids) => [
                    id,
                    ...ids.filter((member) => member !== id),
                  ]);
                }}
              />
            </FormField>
            {leader && (
              <div
                role="group"
                aria-label={t("assistants.groupMembers")}
                className="space-y-2"
              >
                <p className="text-13 text-theme-text-secondary">
                  {t("assistants.groupMembers")}
                </p>
                <div className="assistant-member-picker">
                  {bots
                    .filter((bot) => bot.id !== leader)
                    .map((bot) => (
                      <button
                        key={bot.id}
                        type="button"
                        role="checkbox"
                        aria-checked={members.includes(bot.id)}
                        disabled={
                          (bot.status !== "active" &&
                            !members.includes(bot.id)) ||
                          (!members.includes(bot.id) && members.length >= 12)
                        }
                        onClick={() =>
                          setMembers((ids) =>
                            ids.includes(bot.id)
                              ? ids.filter((id) => id !== bot.id)
                              : [...ids, bot.id],
                          )
                        }
                      >
                        <AgentAvatar
                          avatar={bot.avatar}
                          seed={bot.name}
                          size={28}
                        />
                        <span>{bot.name}</span>
                      </button>
                    ))}
                </div>
              </div>
            )}
            {members
              .filter((id) => !bots.some((bot) => bot.id === id))
              .map((id) => (
                <Button
                  key={id}
                  onClick={() => {
                    setMembers((ids) => ids.filter((member) => member !== id));
                    if (leader === id) setLeader("");
                  }}
                >
                  {t("assistants.unavailableSelection")} · {t("common.remove")}
                </Button>
              ))}
            <AssistantConfigurationFields
              draft={configuration}
              setDraft={setConfiguration}
            />
            <p className="text-12 text-theme-text-secondary">
              {t("assistants.groupPrivacyHint")}
            </p>
          </fieldset>
        )}
      </form>
    </EditorSidebar>
  );
}
