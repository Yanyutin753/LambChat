import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../common";
import { projectApi } from "../../../services/api/project";
import { useSandboxStatus } from "../../../hooks/useSandboxStatus";
import type { Project } from "../../../types";
import type { ChannelRuntimeConfig } from "../../../types/channel";
import { defaultChannelRuntime } from "./channelRuntimeConfig";

interface Props {
  value: ChannelRuntimeConfig;
  onChange: (value: ChannelRuntimeConfig) => void;
  projectId: string | null;
  onProjectChange: (value: string | null) => void;
  envText: string;
  onEnvTextChange: (value: string) => void;
  disabled?: boolean;
}

export function ChannelRunConfigFields({ value, onChange, projectId, onProjectChange,
  envText, onEnvTextChange, disabled = false }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const selectedProject = projects.find((project) => project.id === projectId);
  const workspace = selectedProject?.workspace;
  const effectiveSandbox = workspace ? "local" : value.sandbox || "default";
  const machineId = workspace?.machineId || value.sandbox_machine_id || "";
  const { machines, statusError } = useSandboxStatus({ enabled: effectiveSandbox === "local" });

  useEffect(() => {
    let stopped = false;
    setLoading(true);
    setLoadError(false);
    projectApi.list().then((items) => {
      if (!stopped) setProjects(items);
    }).catch(() => {
      if (!stopped) setLoadError(true);
    }).finally(() => { if (!stopped) setLoading(false); });
    return () => { stopped = true; };
  }, [retry]);

  useEffect(() => {
    if (workspace && (value.sandbox !== "local" || value.sandbox_machine_id !== workspace.machineId)) {
      onChange({ ...value, sandbox: "local", sandbox_machine_id: workspace.machineId });
    }
  }, [workspace, value, onChange]);

  const update = (next: Partial<ChannelRuntimeConfig>) => onChange({ ...value, ...next });
  const defaultOption = <option value="">{t("channel.runtime.inherit")}</option>;
  return <fieldset disabled={disabled} className="es-section space-y-4 min-w-0">
    <legend className="es-section-title">{t("channel.runtime.title")}</legend>
    <div className="es-field">
      <label htmlFor={`${id}-project`} className="es-label">{t("channel.runtime.project")}</label>
      <select id={`${id}-project`} className="glass-input es-input" value={projectId || ""}
        disabled={loading} onChange={(event) => onProjectChange(event.target.value || null)}>
        <option value="">{t("channel.runtime.noProject")}</option>
        {projectId && !selectedProject && <option value={projectId}>{t("channel.runtime.unavailableProject")}</option>}
        {projects.filter((project) => project.type === "custom" || project.id === projectId).map((project) =>
          <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
      {loading && <p className="es-hint" role="status">{t("common.loading")}</p>}
      {loadError && <div className="flex items-center gap-2"><p className="es-hint">{t("common.loadFailed")}</p>
        <Button size="sm" onClick={() => setRetry((previous) => previous + 1)}>{t("common.retry")}</Button></div>}
      {workspace && <p className="es-hint [overflow-wrap:anywhere]">{t("channel.runtime.projectWorkspace", { path: workspace.path, machine: workspace.machineId })}</p>}
    </div>
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="es-field">
        <label htmlFor={`${id}-sandbox`} className="es-label">{t("channel.runtime.sandbox")}</label>
        <select id={`${id}-sandbox`} className="glass-input es-input" value={effectiveSandbox} disabled={Boolean(workspace)}
          onChange={(event) => update({ sandbox: event.target.value as ChannelRuntimeConfig["sandbox"] })}>
          <option value="default">{t("channel.runtime.inherit")}</option>
          <option value="local">{t("channel.runtime.local")}</option>
          <option value="cloud">{t("channel.runtime.cloud")}</option>
        </select>
      </div>
      {effectiveSandbox === "local" && <div className="es-field">
        <label htmlFor={`${id}-machine`} className="es-label">{t("channel.runtime.machine")}</label>
        <select id={`${id}-machine`} className="glass-input es-input" value={machineId} disabled={Boolean(workspace)}
          onChange={(event) => update({ sandbox_machine_id: event.target.value })}>
          {defaultOption}
          {machineId && !machines.some((machine) => machine.machine_id === machineId) && <option value={machineId}>{machineId}</option>}
          {machines.map((machine) => <option key={machine.machine_id} value={machine.machine_id}>
            {machine.name || machine.machine_id}{machine.online === false ? ` (${t("channel.runtime.offline")})` : ""}
          </option>)}
        </select>
        {statusError && <p className="es-hint">{t("common.loadFailed")}</p>}
        {!machines.length && !machineId && <p className="es-hint">{t("channel.runtime.noMachines")}</p>}
      </div>}
      <div className="es-field">
        <label htmlFor={`${id}-thinking`} className="es-label">{t("channel.runtime.thinking")}</label>
        <select id={`${id}-thinking`} className="glass-input es-input" value={value.enable_thinking || ""}
          onChange={(event) => update({ enable_thinking: event.target.value as ChannelRuntimeConfig["enable_thinking"] })}>
          {defaultOption}{(["low", "medium", "high", "max"] as const).map((level) =>
            <option key={level} value={level}>{t(`channel.runtime.${level}`)}</option>)}
        </select>
      </div>
      <div className="es-field">
        <label htmlFor={`${id}-code`} className="es-label">{t("channel.runtime.code")}</label>
        <select id={`${id}-code`} className="glass-input es-input"
          value={value.enable_code_interpreter == null ? "" : String(value.enable_code_interpreter)}
          onChange={(event) => update({ enable_code_interpreter: event.target.value === "" ? null : event.target.value === "true" })}>
          {defaultOption}<option value="true">{t("common.on")}</option><option value="false">{t("common.off")}</option>
        </select>
      </div>
      <div className="es-field">
        <label htmlFor={`${id}-language`} className="es-label">{t("channel.runtime.language")}</label>
        <select id={`${id}-language`} className="glass-input es-input" value={value.response_language || ""}
          onChange={(event) => update({ response_language: event.target.value as ChannelRuntimeConfig["response_language"] })}>
          {defaultOption}<option value="en">English</option><option value="zh">中文</option>
          <option value="ja">日本語</option><option value="ko">한국어</option><option value="ru">Русский</option>
        </select>
      </div>
    </div>
    <div className="es-field">
      <label htmlFor={`${id}-env`} className="es-label">{t("channel.runtime.env")}</label>
      <textarea id={`${id}-env`} className="glass-input es-input min-h-28 font-mono resize-y" rows={4}
        spellCheck={false} autoComplete="off" value={envText} aria-describedby={`${id}-env-hint`}
        onChange={(event) => onEnvTextChange(event.target.value)} placeholder="API_TOKEN=..." />
      <p id={`${id}-env-hint`} className="es-hint">{t("channel.runtime.envHint")}</p>
    </div>
    <p className="es-hint">{t("channel.runtime.applyHint")}</p>
    <Button size="sm" onClick={() => { onChange(defaultChannelRuntime()); onEnvTextChange(""); }}>
      {t("channel.runtime.reset")}
    </Button>
  </fieldset>;
}
