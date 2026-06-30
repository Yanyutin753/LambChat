import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { mcpApi } from "../../services/api/mcp";
import type { MCPRoleQuota, MCPServerResponse, MCPToolInfo } from "../../types";
import { RoleSelector } from "./RoleSelector";

interface MCPServerToolsSidebarProps {
  server: MCPServerResponse;
  onToolToggled?: () => void;
}

function trimQuotasForRoles(
  roles: string[],
  quotas: Record<string, MCPRoleQuota> = {},
): Record<string, MCPRoleQuota> {
  return Object.fromEntries(
    roles.filter((role) => quotas[role]).map((role) => [role, quotas[role]]),
  );
}

function updateQuotaValue(
  quotas: Record<string, MCPRoleQuota> = {},
  role: string,
  field: keyof MCPRoleQuota,
  value: string,
): Record<string, MCPRoleQuota> | null {
  if (value !== "") {
    const num = Number(value);
    if (!Number.isInteger(num) || num < 0) return null;
  }

  const next = { ...quotas };
  const current = next[role] ?? {};
  const updated: MCPRoleQuota = {
    ...current,
    [field]: value === "" ? null : Number(value),
  };
  if (updated.daily_limit == null && updated.weekly_limit == null) {
    delete next[role];
  } else {
    next[role] = updated;
  }
  return next;
}

export function MCPServerToolsSidebar({
  server,
  onToolToggled,
}: MCPServerToolsSidebarProps) {
  const { t } = useTranslation();
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [savingToolPolicy, setSavingToolPolicy] = useState<string | null>(null);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const pendingToggleRef = useRef<Promise<void> | null>(null);

  const toggleExpanded = useCallback((toolName: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
  }, []);

  const TRANSPORT_LABELS: Record<string, string> = {
    sse: t("mcp.form.transportSse"),
    streamable_http: t("mcp.form.transportHttp"),
    sandbox: t("mcp.form.transportSandbox"),
  };

  const transportLabel =
    TRANSPORT_LABELS[server.transport] || server.transport.toUpperCase();

  const enabledToolCount = useMemo(
    () =>
      tools.length > 0
        ? tools.filter((t) => !t.system_disabled && !t.user_disabled).length
        : 0,
    [tools],
  );

  useEffect(() => {
    let cancelled = false;
    setToolsLoading(true);
    mcpApi
      .discoverTools(server.name)
      .then((result) => {
        if (cancelled) return;
        if (result.error) {
          setToolsError(result.error);
        } else {
          setTools(
            [...result.tools].sort((a, b) =>
              a.name.toLowerCase().localeCompare(b.name.toLowerCase()),
            ),
          );
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setToolsError(
          err instanceof Error ? err.message : t("mcp.card.discoverFailed"),
        );
      })
      .finally(() => {
        if (!cancelled) setToolsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [server.name, t]);

  const handleToggleTool = useCallback(
    async (toolName: string, currentEnabled: boolean) => {
      const newEnabled = !currentEnabled;
      const togglePromise = (async () => {
        if (pendingToggleRef.current) {
          await pendingToggleRef.current;
        }
        try {
          if (server.can_edit) {
            await mcpApi.toggleSystemTool(server.name, toolName, newEnabled);
          } else {
            await mcpApi.toggleTool(server.name, toolName, newEnabled, "user");
          }
          setTools((prev) =>
            prev.map((t) =>
              t.name === toolName
                ? server.can_edit
                  ? { ...t, system_disabled: !newEnabled }
                  : { ...t, user_disabled: !newEnabled }
                : t,
            ),
          );
          onToolToggled?.();
        } catch {
          toast.error(t("mcp.card.toolToggleFailed"));
          onToolToggled?.();
        }
      })();
      pendingToggleRef.current = togglePromise;
      await togglePromise;
      pendingToggleRef.current = null;
    },
    [server.can_edit, server.name, onToolToggled, t],
  );

  const handleUpdateToolPolicy = useCallback(
    async (
      toolName: string,
      updates: {
        allowed_roles?: string[];
        role_quotas?: Record<string, MCPRoleQuota>;
        disabled?: boolean;
        inline_exposure?: boolean;
      },
    ) => {
      const current = tools.find((tool) => tool.name === toolName);
      if (!current) return;

      const nextAllowedRoles =
        updates.allowed_roles ?? current.allowed_roles ?? [];
      const nextRoleQuotas = updates.role_quotas ?? current.role_quotas ?? {};
      const nextDisabled = updates.disabled ?? current.system_disabled ?? false;
      const nextInlineExposure =
        updates.inline_exposure ?? current.inline_exposure ?? false;

      setSavingToolPolicy(toolName);
      try {
        await mcpApi.updateToolPolicy(server.name, toolName, {
          disabled: nextDisabled,
          inline_exposure: nextInlineExposure,
          allowed_roles: nextAllowedRoles,
          role_quotas: nextRoleQuotas,
        });
        setTools((prev) =>
          prev.map((tool) =>
            tool.name === toolName
              ? {
                  ...tool,
                  system_disabled: nextDisabled,
                  inline_exposure: nextInlineExposure,
                  allowed_roles: nextAllowedRoles,
                  role_quotas: nextRoleQuotas,
                  policy_configured: true,
                }
              : tool,
          ),
        );
        onToolToggled?.();
      } catch {
        toast.error(t("mcp.card.toolPolicyUpdateFailed"));
      } finally {
        setSavingToolPolicy(null);
      }
    },
    [onToolToggled, server.name, t, tools],
  );

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {/* Server info */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-[var(--theme-text-secondary)]">
          {transportLabel}
        </span>
        <span className="text-[11px] text-[var(--theme-text-secondary)]">
          {server.is_internal
            ? t("mcp.card.internal", "Internal")
            : server.is_system
              ? t("mcp.card.system")
              : t("mcp.card.user")}
        </span>
      </div>

      {(server.url || server.command) && (
        <div className="font-mono text-[11px] text-[var(--theme-text-tertiary)] truncate">
          {server.url || server.command}
        </div>
      )}

      {/* Tools */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between px-1 py-1.5">
          <span className="text-xs font-medium text-[var(--theme-text)]">
            {t("mcp.card.tools")}
          </span>
          {tools.length > 0 && !toolsLoading && (
            <span className="text-[11px] tabular-nums text-[var(--theme-text-tertiary)]">
              {enabledToolCount}/{tools.length}
            </span>
          )}
        </div>

        {toolsLoading && (
          <div className="flex items-center gap-2 py-6 text-xs text-[var(--theme-text-tertiary)] justify-center">
            <Loader2 size={14} className="animate-spin" />
            <span>{t("mcp.card.discovering")}</span>
          </div>
        )}

        {toolsError && (
          <div className="text-xs text-red-500 dark:text-red-400 py-2 px-1">
            {toolsError}
          </div>
        )}

        {!toolsLoading && tools.length === 0 && !toolsError && (
          <div className="text-xs text-[var(--theme-text-tertiary)] py-3 px-1 text-center">
            {t("mcp.card.noTools")}
          </div>
        )}

        {!toolsLoading && tools.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {tools.map((tool) => {
              const isDisabled =
                tool.system_disabled || tool.user_disabled || false;
              const isExpanded = expandedTools.has(tool.name);
              const canConfigurePolicy = server.can_edit && server.is_system;
              return (
                <div
                  key={tool.name}
                  className={`list-item-card ${
                    isDisabled ? "list-item-card--disabled" : ""
                  } ${isExpanded ? "list-item-card--expanded" : ""}`}
                >
                  <div className="list-item-card__body">
                    <div
                      className="list-item-card__top cursor-pointer"
                      onClick={() =>
                        canConfigurePolicy && toggleExpanded(tool.name)
                      }
                    >
                      {canConfigurePolicy && (
                        <ChevronDown
                          size={14}
                          className={`shrink-0 text-[var(--theme-text-quaternary)] transition-transform duration-200 ${
                            isExpanded ? "rotate-180" : ""
                          }`}
                        />
                      )}
                      <div className="list-item-card__identity">
                        <code className="list-item-card__name">
                          {tool.name}
                        </code>
                        {tool.description && (
                          <p className="text-[11px] text-[var(--theme-text-tertiary)] leading-snug line-clamp-2">
                            {tool.description}
                          </p>
                        )}
                      </div>
                      <div className="list-item-card__actions">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleTool(tool.name, !isDisabled);
                          }}
                          className={`team-toggle ${
                            !isDisabled ? "team-toggle--on" : ""
                          }`}
                          title={
                            isDisabled
                              ? t("mcp.card.enableTool")
                              : t("mcp.card.disableTool")
                          }
                        />
                      </div>
                    </div>

                    {canConfigurePolicy && isExpanded && (
                      <div className="list-item-card__instructions">
                        <div className="mb-3 flex items-center justify-between gap-3 rounded-md bg-[var(--theme-bg-subtle)] px-2 py-2">
                          <div className="min-w-0">
                            <div className="text-[10px] font-medium text-[var(--theme-text-tertiary)]">
                              {t("mcp.form.inlineExposure")}
                            </div>
                            <p className="mt-0.5 text-[10px] leading-snug text-[var(--theme-text-quaternary)]">
                              {t("mcp.form.inlineExposureDescription")}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleUpdateToolPolicy(tool.name, {
                                inline_exposure: !(
                                  tool.inline_exposure ?? false
                                ),
                              });
                            }}
                            className={`team-toggle shrink-0 ${
                              tool.inline_exposure ? "team-toggle--on" : ""
                            }`}
                            title={
                              tool.inline_exposure
                                ? t("mcp.form.disableInlineExposure")
                                : t("mcp.form.enableInlineExposure")
                            }
                          />
                        </div>
                        <div className="flex items-center gap-1.5 mb-2">
                          <span className="text-[10px] font-medium text-[var(--theme-text-tertiary)]">
                            {t("mcp.form.allowedRoles")}
                          </span>
                          {savingToolPolicy === tool.name && (
                            <Loader2
                              size={10}
                              className="animate-spin text-[var(--theme-text-tertiary)]"
                            />
                          )}
                        </div>
                        <RoleSelector
                          selectedRoles={tool.allowed_roles ?? []}
                          onChange={(roles) =>
                            handleUpdateToolPolicy(tool.name, {
                              allowed_roles: roles,
                              role_quotas: trimQuotasForRoles(
                                roles,
                                tool.role_quotas,
                              ),
                            })
                          }
                        />
                        {(tool.allowed_roles ?? []).length > 0 && (
                          <>
                            <button
                              type="button"
                              onClick={() =>
                                toggleExpanded(`${tool.name}:quotas`)
                              }
                              className="mt-2.5 flex w-full items-center gap-1.5 rounded-md px-1 py-1 text-[10px] font-medium text-[var(--theme-text-tertiary)] hover:bg-[var(--theme-bg-hover)] transition-colors"
                            >
                              <ChevronDown
                                size={12}
                                className={`transition-transform duration-200 ${
                                  expandedTools.has(`${tool.name}:quotas`)
                                    ? "rotate-180"
                                    : ""
                                }`}
                              />
                              <span className="flex-1 text-left">
                                {t("mcp.form.rateLimits")}
                              </span>
                              <span className="text-[var(--theme-text-quaternary)]">
                                {(tool.allowed_roles ?? []).length}{" "}
                                {t("mcp.form.roles")}
                              </span>
                            </button>
                            {expandedTools.has(`${tool.name}:quotas`) && (
                              <div className="mt-1.5 space-y-1">
                                <div className="grid grid-cols-[1fr_76px_76px] items-center gap-1.5 px-1 pb-0.5">
                                  <span className="text-[9px] text-[var(--theme-text-quaternary)]">
                                    {t("mcp.form.role")}
                                  </span>
                                  <span className="text-[9px] text-[var(--theme-text-quaternary)]">
                                    {t("mcp.form.dailyLimit")}
                                  </span>
                                  <span className="text-[9px] text-[var(--theme-text-quaternary)]">
                                    {t("mcp.form.weeklyLimit")}
                                  </span>
                                </div>
                                {(tool.allowed_roles ?? []).map((role) => {
                                  const quota = tool.role_quotas?.[role] ?? {};
                                  return (
                                    <div
                                      key={role}
                                      className="grid grid-cols-[1fr_76px_76px] items-center gap-1.5 rounded-md px-1 py-1 hover:bg-[var(--theme-bg-hover)] transition-colors"
                                    >
                                      <span className="truncate text-[10px] text-[var(--theme-text-secondary)]">
                                        {role}
                                      </span>
                                      <input
                                        type="number"
                                        min="0"
                                        value={quota.daily_limit ?? ""}
                                        onChange={(e) => {
                                          const nextQuotas = updateQuotaValue(
                                            tool.role_quotas,
                                            role,
                                            "daily_limit",
                                            e.target.value,
                                          );
                                          if (nextQuotas) {
                                            handleUpdateToolPolicy(tool.name, {
                                              role_quotas: nextQuotas,
                                            });
                                          }
                                        }}
                                        placeholder={t("mcp.form.dailyLimit")}
                                        className="glass-input h-6 px-1.5 text-[10px] tabular-nums"
                                      />
                                      <input
                                        type="number"
                                        min="0"
                                        value={quota.weekly_limit ?? ""}
                                        onChange={(e) => {
                                          const nextQuotas = updateQuotaValue(
                                            tool.role_quotas,
                                            role,
                                            "weekly_limit",
                                            e.target.value,
                                          );
                                          if (nextQuotas) {
                                            handleUpdateToolPolicy(tool.name, {
                                              role_quotas: nextQuotas,
                                            });
                                          }
                                        }}
                                        placeholder={t("mcp.form.weeklyLimit")}
                                        className="glass-input h-6 px-1.5 text-[10px] tabular-nums"
                                      />
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
