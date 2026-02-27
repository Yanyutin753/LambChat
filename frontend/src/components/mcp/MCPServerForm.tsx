import { useState, useEffect } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  MCPServerResponse,
  MCPServerCreate,
  MCPTransport,
} from "../../types";

interface MCPServerFormProps {
  server?: MCPServerResponse | null;
  onSave: (data: MCPServerCreate) => Promise<boolean>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface KeyValuePair {
  key: string;
  value: string;
}

export function MCPServerForm({
  server,
  onSave,
  onCancel,
  isLoading = false,
}: MCPServerFormProps) {
  const { t } = useTranslation();
  const isEditing = !!server;

  const [name, setName] = useState(server?.name ?? "");
  const [transport, setTransport] = useState<MCPTransport>(
    server?.transport ?? "stdio",
  );
  const [enabled, setEnabled] = useState(server?.enabled ?? true);

  // STDIO fields
  const [command, setCommand] = useState(server?.command ?? "");
  const [args, setArgs] = useState(server?.args?.join(", ") ?? "");
  const [envVars, setEnvVars] = useState<KeyValuePair[]>(
    server?.env
      ? Object.entries(server.env).map(([key, value]) => ({
          key,
          value: String(value),
        }))
      : [],
  );

  // HTTP fields
  const [url, setUrl] = useState(server?.url ?? "");
  const [headers, setHeaders] = useState<KeyValuePair[]>(
    server?.headers
      ? Object.entries(server.headers).map(([key, value]) => ({
          key,
          value: String(value),
        }))
      : [],
  );

  const [errors, setErrors] = useState<Record<string, string>>({});

  // Update form when server changes
  useEffect(() => {
    if (server) {
      setName(server.name);
      setTransport(server.transport);
      setEnabled(server.enabled);
      setCommand(server.command ?? "");
      setArgs(server.args?.join(", ") ?? "");
      setEnvVars(
        server.env
          ? Object.entries(server.env).map(([key, value]) => ({
              key,
              value: String(value),
            }))
          : [],
      );
      setUrl(server.url ?? "");
      setHeaders(
        server.headers
          ? Object.entries(server.headers).map(([key, value]) => ({
              key,
              value: String(value),
            }))
          : [],
      );
    } else {
      setName("");
      setTransport("stdio");
      setEnabled(true);
      setCommand("");
      setArgs("");
      setEnvVars([]);
      setUrl("");
      setHeaders([]);
    }
    setErrors({});
  }, [server]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = t("mcp.form.validation.nameRequired");
    }

    if (transport === "stdio" && !command.trim()) {
      newErrors.command = t("mcp.form.validation.commandRequired");
    }

    if (transport !== "stdio" && !url.trim()) {
      newErrors.url = t("mcp.form.validation.urlRequired");
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
    };

    if (transport === "stdio") {
      data.command = command.trim();
      if (args.trim()) {
        data.args = args
          .split(",")
          .map((a: string) => a.trim())
          .filter((a: string) => a);
      }
      if (envVars.length > 0) {
        data.env = envVars.reduce(
          (acc, { key, value }) => {
            if (key.trim()) {
              acc[key.trim()] = value;
            }
            return acc;
          },
          {} as Record<string, string>,
        );
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

  const addEnvVar = () => {
    setEnvVars([...envVars, { key: "", value: "" }]);
  };

  const updateEnvVar = (
    index: number,
    field: "key" | "value",
    value: string,
  ) => {
    const newEnvVars = [...envVars];
    newEnvVars[index][field] = value;
    setEnvVars(newEnvVars);
  };

  const removeEnvVar = (index: number) => {
    setEnvVars(envVars.filter((_, i) => i !== index));
  };

  const addHeader = () => {
    setHeaders([...headers, { key: "", value: "" }]);
  };

  const updateHeader = (
    index: number,
    field: "key" | "value",
    value: string,
  ) => {
    const newHeaders = [...headers];
    newHeaders[index][field] = value;
    setHeaders(newHeaders);
  };

  const removeHeader = (index: number) => {
    setHeaders(headers.filter((_, i) => i !== index));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Name */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
          {t("mcp.form.serverName")}
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isEditing}
          placeholder={t("mcp.form.serverNamePlaceholder")}
          className={`w-full rounded-lg border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
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
          <p className="mt-1 text-xs text-gray-500 dark:text-stone-500">
            {t("mcp.form.serverNameUneditable")}
          </p>
        )}
      </div>

      {/* Transport Type */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
          {t("mcp.form.transportType")}
        </label>
        <select
          value={transport}
          onChange={(e) => setTransport(e.target.value as MCPTransport)}
          disabled={isEditing}
          className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
        >
          <option value="stdio">{t("mcp.form.transportStdio")}</option>
          <option value="sse">{t("mcp.form.transportSse")}</option>
          <option value="streamable_http">{t("mcp.form.transportHttp")}</option>
        </select>
        {isEditing && (
          <p className="mt-1 text-xs text-gray-500 dark:text-stone-500">
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
          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-stone-600 dark:bg-stone-800 dark:text-amber-600 dark:focus:ring-amber-500"
        />
        <label
          htmlFor="enabled"
          className="text-sm text-gray-700 dark:text-stone-300"
        >
          {t("mcp.form.enabled")}
        </label>
      </div>

      {/* STDIO-specific fields */}
      {transport === "stdio" && (
        <>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
              {t("mcp.form.command")}
            </label>
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder={t("mcp.form.commandPlaceholder")}
              className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
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

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
              {t("mcp.form.args")}
            </label>
            <input
              type="text"
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              placeholder={t("mcp.form.argsPlaceholder")}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("mcp.form.envVars")}
              </label>
              <button
                type="button"
                onClick={addEnvVar}
                className="flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50"
              >
                <Plus size={12} />
                {t("mcp.form.add")}
              </button>
            </div>
            <div className="space-y-2">
              {envVars.map((env, index) => (
                <div key={index} className="flex gap-2">
                  <input
                    type="text"
                    value={env.key}
                    onChange={(e) => updateEnvVar(index, "key", e.target.value)}
                    placeholder={t("mcp.form.keyPlaceholder")}
                    className="flex-1 rounded-lg border border-gray-200 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <input
                    type="text"
                    value={env.value}
                    onChange={(e) =>
                      updateEnvVar(index, "value", e.target.value)
                    }
                    placeholder={t("mcp.form.valuePlaceholder")}
                    className="flex-1 rounded-lg border border-gray-200 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <button
                    type="button"
                    onClick={() => removeEnvVar(index)}
                    className="rounded-lg p-2 text-gray-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
              {envVars.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-stone-500 italic">
                  {t("mcp.form.noEnvVars")}
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {/* HTTP-specific fields */}
      {transport !== "stdio" && (
        <>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-stone-300">
              {t("mcp.form.url")}
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("mcp.form.urlPlaceholder")}
              className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500 ${
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

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
                {t("mcp.form.httpHeaders")}
              </label>
              <button
                type="button"
                onClick={addHeader}
                className="flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50"
              >
                <Plus size={12} />
                {t("mcp.form.add")}
              </button>
            </div>
            <div className="space-y-2">
              {headers.map((header, index) => (
                <div key={index} className="flex gap-2">
                  <input
                    type="text"
                    value={header.key}
                    onChange={(e) => updateHeader(index, "key", e.target.value)}
                    placeholder={t("mcp.form.headerNamePlaceholder")}
                    className="flex-1 rounded-lg border border-gray-200 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <input
                    type="text"
                    value={header.value}
                    onChange={(e) =>
                      updateHeader(index, "value", e.target.value)
                    }
                    placeholder={t("mcp.form.valuePlaceholder")}
                    className="flex-1 rounded-lg border border-gray-200 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
                  />
                  <button
                    type="button"
                    onClick={() => removeHeader(index)}
                    className="rounded-lg p-2 text-gray-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
              {headers.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-stone-500 italic">
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
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50 dark:border-stone-700 dark:hover:bg-stone-800"
        >
          {t("mcp.form.cancel")}
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="flex items-center gap-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-amber-600 dark:hover:bg-amber-700"
        >
          {isEditing ? t("mcp.form.saveChanges") : t("mcp.form.createServer")}
        </button>
      </div>
    </form>
  );
}
