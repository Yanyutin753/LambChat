import { useState } from "react";
import { createPortal } from "react-dom";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2 as Loader2Icon,
  Puzzle,
  Server,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { EditorSidebar } from "../../common/EditorSidebar";
import { pluginApi } from "../../../services/api/plugin";
import type { PluginResponse } from "../../../types";

interface PluginPreviewModalProps {
  plugin: PluginResponse;
  onClose: () => void;
}

interface FilePreviewState {
  content: string | null;
  loading: boolean;
  error: string | null;
}

export function PluginPreviewModal({ plugin, onClose }: PluginPreviewModalProps) {
  const { t } = useTranslation();
  const [expandedSkill, setExpandedSkill] = useState<string | null>(
    plugin.skills[0]?.skill_name ?? null,
  );
  const [skillFiles, setSkillFiles] = useState<Record<string, string[]>>({});
  const [filesLoading, setFilesLoading] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<FilePreviewState | null>(null);

  const toggleSkill = async (skillName: string) => {
    if (expandedSkill === skillName) {
      setExpandedSkill(null);
      return;
    }
    setExpandedSkill(skillName);
    if (!skillFiles[skillName]) {
      setFilesLoading(skillName);
      try {
        const data = await pluginApi.listSkillFiles(plugin.name, skillName);
        setSkillFiles((prev) => ({
          ...prev,
          [skillName]: data.file_paths ?? [],
        }));
      } catch {
        setSkillFiles((prev) => ({ ...prev, [skillName]: [] }));
      } finally {
        setFilesLoading(null);
      }
    }
  };

  const openFile = async (skillName: string, filePath: string) => {
    setPreviewFile({ content: null, loading: true, error: null });
    try {
      const data = await pluginApi.readSkillFile(plugin.name, skillName, filePath);
      setPreviewFile({ content: data.content, loading: false, error: null });
    } catch (err) {
      setPreviewFile({
        content: null,
        loading: false,
        error: err instanceof Error ? err.message : t("plugins.previewLoadFailed"),
      });
    }
  };

  return createPortal(
    <EditorSidebar
      open
      onClose={onClose}
      title={plugin.display_name || plugin.name}
      subtitle={plugin.description || t("plugins.noDescription")}
      icon={<Puzzle size={16} className="text-[var(--theme-primary)]" />}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--theme-border)] px-4 text-14 text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-bg-secondary)]"
        >
          {t("common.close", "关闭")}
        </button>
      }
    >
      <div className="space-y-4">
        {/* Skills payload */}
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 font-serif text-14 font-semibold text-[var(--theme-text)]">
            <FileText size={13} className="opacity-60" />
            {t("plugins.payloadSkills", "技能负载")}
            <span className="ml-1 text-12 text-[var(--theme-text-secondary)]">
              {plugin.skills.length}
            </span>
          </h4>
          {plugin.skills.length === 0 ? (
            <p className="text-13 text-[var(--theme-text-secondary)]">
              {t("plugins.noSkills", "该插件不携带技能")}
            </p>
          ) : (
            <div className="space-y-1.5">
              {plugin.skills.map((skill) => {
                const isExpanded = expandedSkill === skill.skill_name;
                return (
                  <div
                    key={skill.skill_name}
                    className="rounded-xl border border-[var(--theme-border)]"
                  >
                    <button
                      type="button"
                      onClick={() => void toggleSkill(skill.skill_name)}
                      className="flex w-full items-center gap-2 px-3 py-2.5 text-left"
                      aria-expanded={isExpanded}
                    >
                      {isExpanded ? (
                        <ChevronDown size={13} className="opacity-50" />
                      ) : (
                        <ChevronRight size={13} className="opacity-50" />
                      )}
                      <span className="min-w-0 flex-1 truncate font-serif text-13 font-medium">
                        {skill.skill_name}
                      </span>
                      {skill.description && (
                        <span className="hidden max-w-[45%] truncate text-11 text-[var(--theme-text-secondary)] sm:block">
                          {skill.description}
                        </span>
                      )}
                    </button>
                    {isExpanded && (
                      <div className="border-t border-[var(--theme-border)] px-3 py-2">
                        {filesLoading === skill.skill_name ? (
                          <div className="flex items-center gap-2 py-1 text-12 text-[var(--theme-text-secondary)]">
                            <Loader2Icon size={12} className="animate-spin" />
                            {t("common.loading", "加载中...")}
                          </div>
                        ) : (
                          <div className="space-y-0.5">
                            {(skillFiles[skill.skill_name] ?? []).map((path) => (
                              <button
                                key={path}
                                type="button"
                                onClick={() => void openFile(skill.skill_name, path)}
                                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-12 text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-bg-secondary)] hover:text-[var(--theme-text)]"
                              >
                                <FileText size={11} className="opacity-50" />
                                <span className="truncate">{path}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* MCP payload */}
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 font-serif text-14 font-semibold text-[var(--theme-text)]">
            <Server size={13} className="opacity-60" />
            {t("plugins.payloadMcp", "MCP 服务")}
            <span className="ml-1 text-12 text-[var(--theme-text-secondary)]">
              {plugin.mcp_servers.length}
            </span>
          </h4>
          {plugin.mcp_servers.length === 0 ? (
            <p className="text-13 text-[var(--theme-text-secondary)]">
              {t("plugins.noMcp", "该插件不携带 MCP 服务")}
            </p>
          ) : (
            <div className="space-y-1.5">
              {plugin.mcp_servers.map((server) => (
                <div
                  key={server.name}
                  className="flex items-center gap-2 rounded-xl border border-[var(--theme-border)] px-3 py-2.5"
                >
                  <Server size={13} className="opacity-60" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-serif text-13 font-medium">
                      {server.name}
                    </div>
                    <div className="truncate text-11 text-[var(--theme-text-secondary)]">
                      {server.ref
                        ? t("plugins.mcpRefBadge", "引用平台服务")
                        : server.url}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-md border border-[var(--theme-border)] px-1.5 py-0.5 text-10 text-[var(--theme-text-secondary)]">
                    {server.transport}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Persona payload */}
        {plugin.persona && (
          <section>
            <h4 className="mb-2 flex items-center gap-1.5 font-serif text-14 font-semibold text-[var(--theme-text)]">
              <Bot size={13} className="opacity-60" />
              {t("plugins.payloadPersona", "角色负载")}
            </h4>
            <div className="rounded-xl border border-[var(--theme-border)] px-3 py-2.5">
              <div className="font-serif text-13 font-medium">
                {plugin.persona.name}
              </div>
              {plugin.persona.description && (
                <p className="mt-1 text-12 text-[var(--theme-text-secondary)]">
                  {plugin.persona.description}
                </p>
              )}
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap rounded-lg bg-[var(--theme-bg-secondary)] p-2 text-11 text-[var(--theme-text-secondary)]">
                {plugin.persona.system_prompt}
              </p>
            </div>
          </section>
        )}
      </div>

      {/* File content overlay */}
      {previewFile && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
          <div className="flex h-[75vh] w-full max-w-2xl flex-col rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)] shadow-xl">
            <div className="flex items-center justify-between border-b border-[var(--theme-border)] px-4 py-3">
              <span className="truncate font-serif text-14 font-semibold">
                {t("plugins.filePreview", "文件预览")}
              </span>
              <button
                type="button"
                aria-label={t("common.close", "关闭")}
                onClick={() => setPreviewFile(null)}
                className="rounded-lg p-1 text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-bg-secondary)] hover:text-[var(--theme-text)]"
              >
                <X size={16} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-4">
              {previewFile.loading ? (
                <div className="flex h-full items-center justify-center">
                  <LoadingSpinner size="md" />
                </div>
              ) : previewFile.error ? (
                <p className="text-13 text-red-500">{previewFile.error}</p>
              ) : (
                <pre className="whitespace-pre-wrap break-words text-12 leading-relaxed">
                  {previewFile.content}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </EditorSidebar>,
    document.body,
  );
}
