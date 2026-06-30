import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, ToggleLeft, ToggleRight, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { mcpApi } from "../../services/api/mcp";
import type { MCPRoleQuota, MCPToolInfo } from "../../types";
import { RoleSelector } from "./RoleSelector";

interface MCPToolPolicyEditorProps {
  serverName: string;
  onChanged?: () => void;
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

export function MCPToolPolicyEditor({
  serverName,
  onChanged,
}: MCPToolPolicyEditorProps) {
  const { t } = useTranslation();
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingTool, setSavingTool] = useState<string | null>(null);

  const loadTools = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await mcpApi.discoverTools(serverName);
      if (result.error) {
        setError(result.error);
        setTools([]);
        return;
      }
      setTools(
        [...result.tools].sort((a, b) =>
          a.name.toLowerCase().localeCompare(b.name.toLowerCase()),
        ),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("mcp.card.discoverFailed"),
      );
      setTools([]);
    } finally {
      setLoading(false);
    }
  }, [serverName, t]);

  useEffect(() => {
    if (serverName) {
      loadTools();
    }
  }, [loadTools, serverName]);

  const enabledCount = useMemo(
    () => tools.filter((tool) => !tool.system_disabled).length,
    [tools],
  );

  const savePolicy = useCallback(
    async (
      toolName: string,
      updates: {
        disabled?: boolean;
        inline_exposure?: boolean;
        allowed_roles?: string[];
        role_quotas?: Record<string, MCPRoleQuota>;
      },
    ) => {
      const current = tools.find((tool) => tool.name === toolName);
      if (!current) return;

      const nextDisabled = updates.disabled ?? current.system_disabled ?? false;
      const nextAllowedRoles =
        updates.allowed_roles ?? current.allowed_roles ?? [];
      const nextRoleQuotas = updates.role_quotas ?? current.role_quotas ?? {};
      const nextInlineExposure =
        updates.inline_exposure ?? current.inline_exposure ?? false;

      setSavingTool(toolName);
      try {
        await mcpApi.updateToolPolicy(serverName, toolName, {
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
        onChanged?.();
      } catch {
        toast.error(
          t("mcp.card.toolPolicyUpdateFailed", "Failed to update tool policy"),
        );
      } finally {
        setSavingTool(null);
      }
    },
    [onChanged, serverName, t, tools],
  );

  return (
    <div className="es-field">
      <div className="flex items-center justify-between gap-2">
        <label className="es-label inline-flex items-center gap-1.5">
          <Wrench size={13} />
          {t("mcp.card.tools")}
        </label>
        {loading ? (
          <Loader2
            size={13}
            className="animate-spin text-stone-300 dark:text-stone-600"
          />
        ) : (
          tools.length > 0 && (
            <span className="text-[11px] tabular-nums text-stone-300 dark:text-stone-600">
              {enabledCount}/{tools.length}
            </span>
          )
        )}
      </div>
      <p className="es-hint">
        {t(
          "mcp.form.toolPolicyDescription",
          "Configure role access and usage limits for each tool in this MCP server.",
        )}
      </p>

      {error && (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-800/40 dark:bg-red-950/20 dark:text-red-400">
          {error}
        </div>
      )}

      {!loading && !error && tools.length === 0 && (
        <p className="es-hint italic">{t("mcp.card.noTools")}</p>
      )}

      <div className="mt-2 space-y-1.5">
        {tools.map((tool) => {
          const disabled = tool.system_disabled ?? false;
          return (
            <div
              key={tool.name}
              className={`es-section !gap-1.5 !p-2.5 transition-opacity ${
                disabled ? "opacity-40" : ""
              }`}
            >
              <div className="flex items-start gap-2">
                <button
                  type="button"
                  onClick={() =>
                    savePolicy(tool.name, {
                      disabled: !disabled,
                    })
                  }
                  className="mt-0.5 flex-shrink-0 transition-transform active:scale-90"
                  title={
                    disabled
                      ? t("mcp.card.enableTool")
                      : t("mcp.card.disableTool")
                  }
                >
                  {disabled ? (
                    <ToggleLeft
                      size={17}
                      className="text-stone-300 dark:text-stone-600"
                    />
                  ) : (
                    <ToggleRight
                      size={17}
                      className="text-emerald-500 dark:text-emerald-400"
                    />
                  )}
                </button>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <code className="truncate text-xs font-semibold text-stone-700 dark:text-stone-200">
                      {tool.name}
                    </code>
                    {savingTool === tool.name && (
                      <Loader2
                        size={11}
                        className="animate-spin text-stone-300 dark:text-stone-600"
                      />
                    )}
                  </div>
                  {tool.description && (
                    <p className="mt-0.5 truncate text-[11px] leading-relaxed text-stone-400 dark:text-stone-500">
                      {tool.description}
                    </p>
                  )}

                  <div className="mt-2">
                    <div className="mb-2 flex items-center justify-between gap-3 rounded-md bg-stone-50 px-2 py-1.5 text-[11px] text-stone-500 dark:bg-stone-800/70 dark:text-stone-400">
                      <span>{t("mcp.form.inlineExposure")}</span>
                      <button
                        type="button"
                        onClick={() =>
                          savePolicy(tool.name, {
                            inline_exposure: !(tool.inline_exposure ?? false),
                          })
                        }
                        className={`team-toggle ${
                          tool.inline_exposure ? "team-toggle--on" : ""
                        }`}
                        title={
                          tool.inline_exposure
                            ? t("mcp.form.disableInlineExposure")
                            : t("mcp.form.enableInlineExposure")
                        }
                      />
                    </div>
                    <RoleSelector
                      selectedRoles={tool.allowed_roles ?? []}
                      onChange={(roles) =>
                        savePolicy(tool.name, {
                          allowed_roles: roles,
                          role_quotas: trimQuotasForRoles(
                            roles,
                            tool.role_quotas,
                          ),
                        })
                      }
                    />
                  </div>

                  {(tool.allowed_roles ?? []).length > 0 && (
                    <div className="mt-2 space-y-1">
                      {(tool.allowed_roles ?? []).map((role) => {
                        const quota = tool.role_quotas?.[role] ?? {};
                        return (
                          <div
                            key={role}
                            className="grid grid-cols-[minmax(0,1fr)_80px_80px] items-center gap-2"
                          >
                            <span className="truncate text-[11px] font-medium text-stone-500 dark:text-stone-400">
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
                                  savePolicy(tool.name, {
                                    role_quotas: nextQuotas,
                                  });
                                }
                              }}
                              placeholder={t("mcp.form.dailyLimit")}
                              className="glass-input h-7 px-2 text-[11px] tabular-nums"
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
                                  savePolicy(tool.name, {
                                    role_quotas: nextQuotas,
                                  });
                                }
                              }}
                              placeholder={t("mcp.form.weeklyLimit")}
                              className="glass-input h-7 px-2 text-[11px] tabular-nums"
                            />
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
