import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";
import { assistantApi } from "../../services/api/assistant";
import { modelApi } from "../../services/api/model";
import { personaPresetApi } from "../../services/api/personaPreset";
import { projectApi } from "../../services/api/project";
import { teamApi } from "../../services/api/team";
import { loadAssistantChoices } from "./assistantChoices";
import { assistantConfiguration, type Assistant } from "../../types/assistant";
import { Dialog } from "../common/Dialog";
import {
  Button,
  FormField,
  Input,
  Select,
  Textarea,
  type SelectOption,
} from "../common/ui";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { ProjectWorkspaceField } from "../sidebar/ProjectWorkspaceField";

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
  const { hasPermission } = useAuth();
  const formId = useId();
  const [saved, setSaved] = useState(value);
  const [draft, setDraft] = useState(() => assistantConfiguration(value));
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [choicesError, setChoicesError] = useState(false);
  const [choicesRevision, setChoicesRevision] = useState(0);
  const [choicesLoading, setChoicesLoading] = useState(true);
  const [models, setModels] = useState<SelectOption[]>([]);
  const [personas, setPersonas] = useState<SelectOption[]>([]);
  const [projects, setProjects] = useState<SelectOption[]>([]);
  const [teams, setTeams] = useState<SelectOption[]>([]);
  const canReadPersonas = hasPermission(Permission.PERSONA_PRESET_READ);
  const canReadProjects = hasPermission(Permission.PROJECT_READ);
  const canReadTeams = hasPermission(Permission.TEAM_READ);

  useEffect(() => {
    let active = true;
    setChoicesLoading(true);
    setChoicesError(false);
    void Promise.all([
      modelApi.listAvailable(),
      canReadPersonas
        ? loadAssistantChoices(
            async (skip) => {
              const result = await personaPresetApi.list({ skip, limit: 100 });
              return { items: result.presets, total: result.total };
            },
            () => active,
          )
        : Promise.resolve([]),
      canReadProjects ? projectApi.list() : Promise.resolve([]),
      canReadTeams
        ? loadAssistantChoices(
            async (skip) => {
              const result = await teamApi.list({ skip, limit: 100 });
              return { items: result.teams, total: result.total };
            },
            () => active,
          )
        : Promise.resolve([]),
    ])
      .then(([modelList, personaList, projectList, teamList]) => {
        if (!active) return;
        setModels(
          modelList.models.map((model) => ({
            value: model.id,
            label: model.label,
          })),
        );
        setPersonas(personaList);
        setProjects(
          projectList.map((project) => ({
            value: project.id,
            label: project.name,
          })),
        );
        setTeams(teamList);
      })
      .catch(() => {
        if (active) setChoicesError(true);
      })
      .finally(() => {
        if (active) setChoicesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [canReadPersonas, canReadProjects, canReadTeams, choicesRevision]);

  const save = async () => {
    if (busyRef.current) return;
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

  const choices = (
    options: SelectOption[],
    selected: string | null,
    empty: string,
  ) => [
    { value: "", label: empty },
    ...(selected && !options.some((option) => option.value === selected)
      ? [
          {
            value: selected,
            label: t("assistants.unavailableSelection"),
            disabled: true,
          },
        ]
      : []),
    ...options,
  ];

  return (
    <Dialog
      open
      onClose={onClose}
      title={t(saved ? "assistants.edit" : "assistants.create")}
      size="lg"
      dismissible={!busy}
      footer={
        <>
          <Button disabled={busy} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            type="submit"
            form={formId}
            loading={busy}
            disabled={
              !draft.name.trim() ||
              (draft.sandbox === "local" && !draft.workspace)
            }
          >
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="space-y-4"
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
          {choicesError && (
            <div role="alert" className="text-14 text-theme-error">
              {t("common.loadFailed")}{" "}
              <Button onClick={() => setChoicesRevision((old) => old + 1)}>
                {t("common.refresh")}
              </Button>
            </div>
          )}
          <FormField label={t("assistants.model")}>
            <Select
              ariaLabel={t("assistants.model")}
              value={draft.model_id ?? ""}
              disabled={choicesLoading}
              options={choices(
                models,
                draft.model_id,
                t("assistants.defaultModel"),
              )}
              onChange={(model_id) =>
                setDraft({ ...draft, model_id: model_id || null })
              }
            />
          </FormField>
          <FormField
            label={t("assistants.team")}
            hint={t("assistants.teamHint")}
          >
            <Select
              ariaLabel={t("assistants.team")}
              value={draft.team_id ?? ""}
              disabled={choicesLoading || !canReadTeams}
              options={choices(teams, draft.team_id, t("assistants.none"))}
              onChange={(team_id) =>
                setDraft({
                  ...draft,
                  team_id: team_id || null,
                  persona_preset_id: team_id ? null : draft.persona_preset_id,
                })
              }
            />
          </FormField>
          <FormField label={t("assistants.persona")}>
            <Select
              ariaLabel={t("assistants.persona")}
              value={draft.persona_preset_id ?? ""}
              disabled={choicesLoading || !canReadPersonas || !!draft.team_id}
              options={choices(
                personas,
                draft.persona_preset_id,
                t("assistants.none"),
              )}
              onChange={(persona_preset_id) =>
                setDraft({
                  ...draft,
                  persona_preset_id: persona_preset_id || null,
                })
              }
            />
          </FormField>
          <FormField label={t("assistants.project")}>
            <Select
              ariaLabel={t("assistants.project")}
              value={draft.project_id ?? ""}
              disabled={choicesLoading || !canReadProjects}
              options={choices(
                projects,
                draft.project_id,
                t("assistants.none"),
              )}
              onChange={(project_id) =>
                setDraft({
                  ...draft,
                  project_id: project_id || null,
                  memory_mode: project_id ? draft.memory_mode : "private",
                })
              }
            />
          </FormField>
          <FormField
            label={t("assistants.memoryMode")}
            hint={t("assistants.memoryModeHint")}
          >
            <Select
              ariaLabel={t("assistants.memoryMode")}
              value={draft.memory_mode}
              options={[
                { value: "private", label: t("assistants.privateMemory") },
                {
                  value: "project",
                  label: t("assistants.projectMemory"),
                  disabled: !draft.project_id,
                },
              ]}
              onChange={(memory_mode) =>
                setDraft({
                  ...draft,
                  memory_mode: memory_mode as "private" | "project",
                })
              }
            />
          </FormField>
          <FormField
            label={t("assistants.environment")}
            hint={t("assistants.environmentHint")}
          >
            <Select
              ariaLabel={t("assistants.environment")}
              value={draft.sandbox ?? ""}
              options={[
                { value: "", label: t("assistants.inheritEnvironment") },
                { value: "cloud", label: t("assistants.cloud") },
                { value: "local", label: t("assistants.local") },
              ]}
              onChange={(sandbox) =>
                setDraft({
                  ...draft,
                  sandbox: (sandbox as "local" | "cloud") || null,
                  workspace: sandbox === "local" ? draft.workspace : null,
                })
              }
            />
          </FormField>
          {draft.sandbox === "local" && (
            <>
              <ProjectWorkspaceField
                value={draft.workspace}
                onChange={(workspace) => setDraft({ ...draft, workspace })}
              />
              <p className="text-12 text-theme-text-secondary">
                {t("assistants.localHint")}
              </p>
            </>
          )}
        </fieldset>
      </form>
    </Dialog>
  );
}
