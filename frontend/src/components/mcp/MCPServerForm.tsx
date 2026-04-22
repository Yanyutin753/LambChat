import { useState, useEffect } from "react";
import { Plus, Trash2, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Permission } from "../../types";
import type {
  MCPServerResponse,
  MCPServerCreate,
  MCPRoleQuota,
  MCPTransport,
} from "../../types";
import { EnvKeysSelector } from "./EnvKeysSelector";
import { RoleSelector } from "./RoleSelector";

interface MCPServerFormProps {
  server?: MCPServerResponse | null;
  onSave: (data: MCPServerCreate) => Promise<boolean>;
  onCancel: () => void;
  isLoading?: boolean;
  allowedTransports?: Permission[];
  isSystemServer?: boolean;
}

interface KeyValuePair {
  id: string;
  key: string;
  value: string;
}

type RoleQuotaDraft = {
  daily_limit: number | "";
  weekly_limit: number | "";
};

// Simple counter-based ID generator (avoids crypto.randomUUID() browser compat issues)
let _headerIdCounter = 0;
function nextHeaderId(): string {
  return `h-${++_headerIdCounter}-${Math.random().toString(36).slice(2, 8)}`;
}

function toQuotaDrafts(
  quotas: Record<string, MCPRoleQuota>,
): Record<string, RoleQuotaDraft> {
  return Object.fromEntries(
    Object.entries(quotas).map(([role, quota]) => [
      role,
      {
        daily_limit: quota.daily_limit ?? "",
        weekly_limit: quota.weekly_limit ?? "",
      },
    ]),
  );
}

function serializeRoleQuotas(
  roles: string[],
  drafts: Record<string, RoleQuotaDraft>,
): Record<string, MCPRoleQuota> {
  const quotas: Record<string, MCPRoleQuota> = {};
  for (const role of roles) {
    const quota = drafts[role];
    if (!quota) continue;
    if (quota.daily_limit === "" && quota.weekly_limit === "") continue;
    quotas[role] = {
      daily_limit: quota.daily_limit === "" ? null : quota.daily_limit,
      weekly_limit: quota.weekly_limit === "" ? null : quota.weekly_limit,
    };
  }
  return quotas;
}

export function MCPServerForm({
  server,
  onSave,
  onCancel,
  isLoading = false,
  allowedTransports = [
    Permission.MCP_ADMIN,
    Permission.MCP_WRITE_SSE,
    Permission.MCP_WRITE_HTTP,
    Permission.MCP_WRITE_SANDBOX,
  ],
  isSystemServer = false,
}: MCPServerFormProps) {
  const { t } = useTranslation();
  const isEditing = !!server;

  const allTransports: {
    value: MCPTransport;
    label: string;
    permission: Permission;
  }[] = [
    {
      value: "sse" as MCPTransport,
      label: t("mcp.form.transportSse"),
      permission: Permission.MCP_WRITE_SSE,
    },
    {
      value: "streamable_http" as MCPTransport,
      label: t("mcp.form.transportHttp"),
      permission: Permission.MCP_WRITE_HTTP,
    },
    {
      value: "sandbox" as MCPTransport,
      label: t("mcp.form.transportSandbox"),
      permission: Permission.MCP_WRITE_SANDBOX,
    },
  ];
  const availableTransports = allTransports.filter((tr) =>
    allowedTransports.includes(tr.permission),
  );

  const defaultTransport = availableTransports[0]?.value ?? "sse";

  const [name, setName] = useState(server?.name ?? "");
  const [transport, setTransport] = useState<MCPTransport>(
    server?.transport ?? defaultTransport,
  );
  const isSandbox = transport === "sandbox";
  const [enabled, setEnabled] = useState(server?.enabled ?? true);

  // HTTP fields
  const [url, setUrl] = useState(server?.url ?? "");
  const [headers, setHeaders] = useState<KeyValuePair[]>(
    server?.headers
      ? Object.entries(server.headers).map(([key, value]) => ({
          id: nextHeaderId(),
          key,
          value: String(value),
        }))
      : [],
  );

  // Sandbox fields
  const [command, setCommand] = useState(server?.command ?? "");
  const [envKeys, setEnvKeys] = useState<string[]>(server?.env_keys ?? []);
  const [allowedRoles, setAllowedRoles] = useState<string[]>(
    server?.allowed_roles ?? [],
  );
  const [roleQuotas, setRoleQuotas] = useState<Record<string, RoleQuotaDraft>>(
    () => toQuotaDrafts(server?.role_quotas ?? {}),
  );

  const [errors, setErrors] = useState<Record<string, string>>({});

  // Update form when server changes
  useEffect(() => {
    if (server) {
      setName(server.name);
      setTransport(server.transport);
      setEnabled(server.enabled);
      setUrl(server.url ?? "");
      setHeaders(
        server.headers
          ? Object.entries(server.headers).map(([key, value]) => ({
              id: nextHeaderId(),
              key,
              value: String(value),
            }))
          : [],
      );
      setCommand(server.command ?? "");
      setEnvKeys(server.env_keys ?? []);
      setAllowedRoles(server.allowed_roles ?? []);
      setRoleQuotas(toQuotaDrafts(server.role_quotas ?? {}));
    } else {
      setName("");
      setTransport("sse");
      setEnabled(true);
      setUrl("");
      setHeaders([]);
      setCommand("");
      setEnvKeys([]);
      setAllowedRoles([]);
      setRoleQuotas({});
    }
    setErrors({});
  }, [server]);

  const handleAllowedRolesChange = (roles: string[]) => {
    setAllowedRoles(roles);
    setRoleQuotas((prev) => {
      const next: Record<string, RoleQuotaDraft> = {};
      for (const role of roles) {
        next[role] = prev[role] ?? { daily_limit: "", weekly_limit: "" };
      }
      return next;
    });
  };

  const updateRoleQuota = (
    role: string,
    field: keyof RoleQuotaDraft,
    value: string,
  ) => {
    if (value !== "") {
      const num = Number(value);
      if (!Number.isInteger(num) || num < 0) return;
    }
    setRoleQuotas((prev) => ({
      ...prev,
      [role]: {
        ...(prev[role] ?? { daily_limit: "", weekly_limit: "" }),
        [field]: value === "" ? "" : Number(value),
      },
    }));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = t("mcp.form.validation.nameRequired");
    }

    if (isSandbox) {
      if (!command.trim()) {
        newErrors.command = t("mcp.form.validation.commandRequired");
      }
    } else {
      if (!url.trim()) {
        newErrors.url = t("mcp.form.validation.urlRequired");
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const data: MCPServerCreate = {
      name: name.trim(),
      transport,
      enabled,
      allowed_roles: isSystemServer ? allowedRoles : undefined,
      role_quotas: isSystemServer
        ? serializeRoleQuotas(allowedRoles, roleQuotas)
        : undefined,
    };

    if (isSandbox) {
      data.command = command.trim();
      if (envKeys.length > 0) {
        data.env_keys = envKeys;
      }
    } else {
      data.url = url.trim();
      if (headers.length > 0) {
        data.headers = headers.reduce(
          (acc, { key, value }) => {
            if (key.trim()) {
              acc[key.trim()] = value;
            }
            return acc;
          },
          {} as Record<string, string>,
        );
      }
    }

    await onSave(data);
  };

  const addHeader = () => {
    setHeaders([...headers, { id: crypto.randomUUID(), key: "", value: "" }]);
  };

  const updateHeader = (id: string, field: "key" | "value", value: string) => {
    setHeaders(
      headers.map((h) => (h.id === id ? { ...h, [field]: value } : h)),
    );
  };

  const removeHeader = (id: string) => {
    setHeaders(headers.filter((h) => h.id !== id));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Name */}
      <div>
        <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
          {t("mcp.form.serverName")}
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isEditing}
          placeholder={t("mcp.form.serverNamePlaceholder")}
          className={`w-full rounded-lg border px-3 py-2 text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
            errors.name
              ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
              : ""
          }`}
        />
        {errors.name && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.name}
          </p>
        )}
        {isEditing && (
          <p className="mt-1 text-xs text-stone-500 dark:text-stone-500">
            {t("mcp.form.serverNameUneditable")}
          </p>
        )}
      </div>

      {/* Transport Type */}
      <div>
        <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
          {t("mcp.form.transportType")}
        </label>
        <div className="relative">
          <select
            value={transport}
            onChange={(e) => setTransport(e.target.value as MCPTransport)}
            disabled={isEditing}
            className="w-full appearance-none rounded-lg border border-stone-200 bg-white pl-3 pr-9 py-2 text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
          >
            {availableTransports.map((tr) => (
              <option key={tr.value} value={tr.value}>
                {tr.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
        </div>
        {isEditing && (
          <p className="mt-1 text-xs text-stone-500 dark:text-stone-500">
            {t("mcp.form.transportUneditable")}
          </p>
        )}
      </div>

      {/* Enabled */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="enabled"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className=""
        />
        <label
          htmlFor="enabled"
          className="text-sm text-stone-700 dark:text-stone-300"
        >
          {t("mcp.form.enabled")}
        </label>
      </div>

      {/* Allowed Roles (system servers only) */}
      {isSystemServer && (
        <div>
          <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
            {t("mcp.form.allowedRoles")}
          </label>
          <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">
            {t("mcp.form.allowedRolesDescription")}
          </p>
          <RoleSelector
            selectedRoles={allowedRoles}
            onChange={handleAllowedRolesChange}
          />
          {allowedRoles.length > 0 && (
            <div className="mt-3 space-y-2">
              {allowedRoles.map((role) => {
                const quota = roleQuotas[role] ?? {
                  daily_limit: "",
                  weekly_limit: "",
                };
                return (
                  <div
                    key={role}
                    className="rounded-lg border border-stone-200 bg-stone-50 p-2 dark:border-stone-700 dark:bg-stone-800/50"
                  >
                    <div className="mb-2 text-xs font-medium text-stone-700 dark:text-stone-200">
                      {role}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div>
                        <label className="mb-1 block text-xs text-stone-500 dark:text-stone-400">
                          {t("mcp.form.dailyLimit")}
                        </label>
                        <input
                          type="number"
                          min="0"
                          value={quota.daily_limit}
                          onChange={(e) =>
                            updateRoleQuota(role, "daily_limit", e.target.value)
                          }
                          placeholder={t("mcp.form.unlimited")}
                          className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm text-stone-900 focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs text-stone-500 dark:text-stone-400">
                          {t("mcp.form.weeklyLimit")}
                        </label>
                        <input
                          type="number"
                          min="0"
                          value={quota.weekly_limit}
                          onChange={(e) =>
                            updateRoleQuota(
                              role,
                              "weekly_limit",
                              e.target.value,
                            )
                          }
                          placeholder={t("mcp.form.unlimited")}
                          className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm text-stone-900 focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Sandbox-specific fields ── */}
      {isSandbox && (
        <>
          {/* Command */}
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              {t("mcp.form.command")}
            </label>
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder={t("mcp.form.commandPlaceholder")}
              className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
                errors.command
                  ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
                  : ""
              }`}
            />
            {errors.command && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.command}
              </p>
            )}
          </div>

          {/* Env Keys Selector */}
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              {t("mcp.form.envKeys")}
            </label>
            <p className="mb-2 text-xs text-stone-500 dark:text-stone-400">
              {t("mcp.form.envKeysDescription")}
            </p>
            <EnvKeysSelector selectedKeys={envKeys} onChange={setEnvKeys} />
          </div>
        </>
      )}

      {/* ── HTTP/SSE-specific fields ── */}
      {!isSandbox && (
        <>
          {/* URL field */}
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              {t("mcp.form.url")}
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("mcp.form.urlPlaceholder")}
              className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
                errors.url
                  ? "border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700"
                  : ""
              }`}
            />
            {errors.url && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                {errors.url}
              </p>
            )}
          </div>

          {/* HTTP Headers */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("mcp.form.httpHeaders")}
              </label>
              <button
                type="button"
                onClick={addHeader}
                className="flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 text-xs font-medium text-stone-700 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
              >
                <Plus size={12} />
                {t("mcp.form.add")}
              </button>
            </div>
            <div className="space-y-2">
              {headers.map((header) => (
                <div key={header.id} className="flex gap-2">
                  <input
                    type="text"
                    value={header.key}
                    onChange={(e) =>
                      updateHeader(header.id, "key", e.target.value)
                    }
                    placeholder={t("mcp.form.headerNamePlaceholder")}
                    className="flex-1 rounded-lg border border-stone-200 px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <input
                    type="text"
                    value={header.value}
                    onChange={(e) =>
                      updateHeader(header.id, "value", e.target.value)
                    }
                    placeholder={t("mcp.form.valuePlaceholder")}
                    className="flex-1 rounded-lg border border-stone-200 px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <button
                    type="button"
                    onClick={() => removeHeader(header.id)}
                    className="rounded-lg p-2 text-stone-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
              {headers.length === 0 && (
                <p className="text-sm text-stone-500 dark:text-stone-500 italic">
                  {t("mcp.form.noHeaders")}
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          className="rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 disabled:opacity-50 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
        >
          {t("mcp.form.cancel")}
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="flex items-center gap-1 rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white hover:bg-stone-900 disabled:opacity-50 dark:bg-amber-600 dark:hover:bg-amber-700"
        >
          {isEditing ? t("mcp.form.saveChanges") : t("mcp.form.createServer")}
        </button>
      </div>
    </form>
  );
}
