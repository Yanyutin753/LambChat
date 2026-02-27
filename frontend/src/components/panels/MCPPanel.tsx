import { useState } from "react";
import {
  Plus,
  X,
  Search,
  Download,
  Upload,
  FolderOpen,
  Loader2,
  Check,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { MCPServerCard } from "../mcp/MCPServerCard";
import { MCPServerForm } from "../mcp/MCPServerForm";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useMCP } from "../../hooks/useMcp";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { MCPServerResponse, MCPServerCreate } from "../../types";

export function MCPPanel() {
  const { t } = useTranslation();
  const {
    servers,
    isLoading,
    error,
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    importServers,
    exportServers,
    promoteServer,
    demoteServer,
    clearError,
  } = useMCP();
  const { hasAnyPermission, user } = useAuth();

  const [searchQuery, setSearchQuery] = useState("");
  const [editingServer, setEditingServer] = useState<MCPServerResponse | null>(
    null,
  );
  const [isCreating, setIsCreating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [createAsSystem, setCreateAsSystem] = useState(false);
  const [changeToSystem, setChangeToSystem] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importJson, setImportJson] = useState("");
  const [importOverwrite, setImportOverwrite] = useState(false);
  const [importResult, setImportResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Delete confirmation dialog state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
    isSystem: boolean;
  } | null>(null);

  const canRead = hasAnyPermission([Permission.MCP_READ]);
  const canWrite = hasAnyPermission([Permission.MCP_WRITE]);
  const canAdmin = hasAnyPermission([Permission.MCP_ADMIN]);
  // Note: canDelete permission is checked server-side
  // Client-side uses canWrite for UI actions, server validates actual permissions

  const filteredServers = servers.filter((server) =>
    server.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const handleCreate = async () => {
    setIsCreating(true);
    setEditingServer(null);
    setCreateAsSystem(false);
    setChangeToSystem(false);
    setShowModal(true);
  };

  const handleEdit = (server: MCPServerResponse) => {
    setEditingServer(server);
    setIsCreating(false);
    setCreateAsSystem(false);
    setChangeToSystem(server.is_system); // Initialize with current type
    setShowModal(true);
  };

  const handleSave = async (data: MCPServerCreate): Promise<boolean> => {
    let success = false;

    try {
      if (isCreating) {
        const result = await createServer(data, createAsSystem);
        success = result !== null;
        if (success) {
          toast.success(t("mcp.createSuccess"));
        } else {
          toast.error(t("mcp.createFailed"));
        }
      } else if (editingServer) {
        // Check if server type is changing
        const typeChanging = changeToSystem !== editingServer.is_system;

        if (typeChanging && canAdmin) {
          // Handle type change
          if (changeToSystem) {
            // Promote user server to system server
            // We need the owner's user_id - for now, use current user
            const result = await promoteServer(
              editingServer.name,
              user?.id || "",
            );
            success = result !== null;
            if (success) {
              toast.success(t("mcp.promoteSuccess"));
            } else {
              toast.error(t("mcp.promoteFailed"));
            }
          } else {
            // Demote system server to user server
            const result = await demoteServer(
              editingServer.name,
              user?.id || "",
            );
            success = result !== null;
            if (success) {
              toast.success(t("mcp.demoteSuccess"));
            } else {
              toast.error(t("mcp.demoteFailed"));
            }
          }
        } else {
          // Normal update without type change
          const result = await updateServer(
            editingServer.name,
            data,
            editingServer.is_system,
          );
          success = result !== null;
          if (success) {
            toast.success(t("mcp.updateSuccess"));
          } else {
            toast.error(t("mcp.updateFailed"));
          }
        }
      }

      if (success) {
        setShowModal(false);
        setEditingServer(null);
        setIsCreating(false);
        setCreateAsSystem(false);
        setChangeToSystem(false);
      }
    } catch (error) {
      toast.error((error as Error).message || t("mcp.operationFailed"));
      success = false;
    }

    return success;
  };

  const handleCancel = () => {
    setShowModal(false);
    setEditingServer(null);
    setIsCreating(false);
    setCreateAsSystem(false);
    setChangeToSystem(false);
  };

  const handleDelete = async (name: string, isSystem: boolean = false) => {
    setDeleteConfirmData({ name, isSystem });
    setIsDeleteConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleteConfirmData) return;
    try {
      await deleteServer(deleteConfirmData.name, deleteConfirmData.isSystem);
      toast.success(t("mcp.deleteSuccess"));
    } catch (error) {
      toast.error((error as Error).message || t("mcp.deleteFailed"));
    } finally {
      setIsDeleteConfirmOpen(false);
      setDeleteConfirmData(null);
    }
  };

  const cancelDelete = () => {
    setIsDeleteConfirmOpen(false);
    setDeleteConfirmData(null);
  };

  const handleToggle = async (name: string) => {
    await toggleServer(name);
  };

  const handleExport = async () => {
    try {
      const result = await exportServers();
      if (result && result.servers) {
        // Create a blob and download the file
        const blob = new Blob(
          [JSON.stringify({ mcpServers: result.servers }, null, 2)],
          {
            type: "application/json",
          },
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "mcp-servers.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success(t("mcp.exportSuccess"));
      } else {
        toast.error(t("mcp.exportFailed"));
      }
    } catch (error) {
      toast.error((error as Error).message || t("mcp.exportFailed"));
    }
  };

  const handleImportClick = () => {
    setImportJson("");
    setImportOverwrite(false);
    setImportResult(null);
    setShowImportModal(true);
  };

  const handleImport = async () => {
    setImportResult(null);

    try {
      const parsed = JSON.parse(importJson);
      if (!parsed.mcpServers || typeof parsed.mcpServers !== "object") {
        setImportResult({
          success: false,
          message: "Invalid format: missing mcpServers object",
        });
        toast.error(t("mcp.invalidFormat"));
        return;
      }

      const result = await importServers({
        servers: parsed.mcpServers,
        overwrite: importOverwrite,
      });

      if (result) {
        const message = `${result.message}${
          result.errors.length > 0
            ? `\nErrors: ${result.errors.join(", ")}`
            : ""
        }`;
        setImportResult({ success: true, message });

        if (result.errors.length === 0) {
          toast.success(t("mcp.importSuccess"));
          setTimeout(() => {
            setShowImportModal(false);
            setImportJson("");
            setImportResult(null);
          }, 1500);
        } else {
          toast.error(result.errors.join(", "));
        }
      }
    } catch (error) {
      setImportResult({ success: false, message: "Invalid JSON format" });
      toast.error(t("mcp.invalidJson"));
    }
  };

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        {t("mcp.noPermission")}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Header */}
      <div className="panel-header">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
              {t("mcp.title")}
            </h2>
            <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
              {t("mcp.subtitle")}
            </p>
          </div>
          <div className="flex gap-2">
            {canWrite && (
              <>
                <button
                  onClick={handleImportClick}
                  className="btn-secondary"
                  title={t("mcp.importFromJSON")}
                >
                  <Upload size={18} />
                  <span className="hidden sm:inline">{t("common.import")}</span>
                </button>
                <button
                  onClick={handleExport}
                  className="btn-secondary"
                  title={t("mcp.exportToJSON")}
                >
                  <Download size={18} />
                  <span className="hidden sm:inline">{t("common.export")}</span>
                </button>
                <button onClick={handleCreate} className="btn-primary">
                  <Plus size={18} />
                  {t("mcp.addServer")}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Search */}
        <div className="relative mt-3">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            placeholder={t("mcp.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="panel-search"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <button
            onClick={clearError}
            className="btn-icon hover:bg-red-100 dark:hover:bg-red-900/50"
          >
            <X size={18} />
          </button>
        </div>
      )}

      {/* Servers List */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4">
        {isLoading && servers.length === 0 ? (
          <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
            <Loader2 size={24} className="animate-spin" />
            <span className="ml-2">{t("mcp.loading")}</span>
          </div>
        ) : filteredServers.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-stone-500 dark:text-stone-400">
            <FolderOpen
              size={48}
              className="mb-3 text-stone-300 dark:text-stone-600"
            />
            <p className="text-center">
              {searchQuery ? t("mcp.noMatchingServers") : t("mcp.noServers")}
            </p>
            {!searchQuery && canWrite && (
              <button
                onClick={handleCreate}
                className="mt-3 text-sm text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-200"
              >
                {t("mcp.addFirst")}
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {filteredServers.map((server) => (
              <MCPServerCard
                key={server.name}
                server={server}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {/* Form Modal */}
      {showModal && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 " onClick={handleCancel} />
          {/* Modal */}
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              {/* Mobile drag handle */}
              <div className="bottom-sheet-handle sm:hidden" />

              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                  {isCreating
                    ? t("mcp.addNew")
                    : t("mcp.editServer", { name: editingServer?.name })}
                </h3>
                <button onClick={handleCancel} className="btn-icon">
                  <X size={20} />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2">
                {/* Admin option for creating system server */}
                {isCreating && canAdmin && (
                  <div className="mb-4 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
                    <input
                      type="checkbox"
                      id="createAsSystem"
                      checked={createAsSystem}
                      onChange={(e) => setCreateAsSystem(e.target.checked)}
                      className="h-4 w-4 rounded border-stone-300 text-stone-900 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
                    />
                    <label
                      htmlFor="createAsSystem"
                      className="text-sm text-amber-800 dark:text-amber-200"
                    >
                      {t("mcp.createAsSystem")}
                    </label>
                  </div>
                )}
                {/* Admin option for changing server type when editing */}
                {!isCreating && editingServer && canAdmin && (
                  <div className="mb-4 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
                    <input
                      type="checkbox"
                      id="changeToSystem"
                      checked={changeToSystem}
                      onChange={(e) => setChangeToSystem(e.target.checked)}
                      className="h-4 w-4 rounded border-stone-300 text-stone-900 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
                    />
                    <label
                      htmlFor="changeToSystem"
                      className="text-sm text-amber-800 dark:text-amber-200"
                    >
                      {changeToSystem
                        ? t("mcp.systemServerVisible")
                        : t("mcp.userServerVisible")}
                    </label>
                  </div>
                )}
                <MCPServerForm
                  server={editingServer}
                  onSave={handleSave}
                  onCancel={handleCancel}
                  isLoading={isLoading}
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <>
          <div
            className="fixed inset-0 "
            onClick={() => setShowImportModal(false)}
          />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                  {t("mcp.importServers")}
                </h3>
                <button
                  onClick={() => setShowImportModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2">
                <div className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("mcp.jsonConfig")}
                    </label>
                    <textarea
                      value={importJson}
                      onChange={(e) => setImportJson(e.target.value)}
                      rows={8}
                      placeholder={`{
  "mcpServers": {
    "server-name": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@example/server"],
      "enabled": true
    }
  }
}`}
                      className="w-full rounded-xl border border-stone-200 bg-white px-3 py-2 font-mono text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="overwrite"
                      checked={importOverwrite}
                      onChange={(e) => setImportOverwrite(e.target.checked)}
                      className="h-4 w-4 rounded border-stone-300 text-stone-900 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
                    />
                    <label
                      htmlFor="overwrite"
                      className="text-sm text-stone-700 dark:text-stone-300"
                    >
                      {t("mcp.overwriteExisting")}
                    </label>
                  </div>

                  {importResult && (
                    <div
                      className={`flex items-center gap-2 rounded-xl p-3 ${
                        importResult.success
                          ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                      }`}
                    >
                      {importResult.success ? (
                        <Check size={20} className="flex-shrink-0" />
                      ) : (
                        <X size={20} className="flex-shrink-0" />
                      )}
                      <span className="whitespace-pre-wrap text-sm">
                        {importResult.message}
                      </span>
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      onClick={() => setShowImportModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      onClick={handleImport}
                      disabled={isLoading || !importJson.trim()}
                      className="btn-primary disabled:opacity-50"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 size={18} className="animate-spin" />
                          {t("common.importing")}
                        </>
                      ) : (
                        <>
                          <Upload size={18} />
                          {t("common.import")}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isDeleteConfirmOpen}
        title={t("mcp.confirmDelete", { name: deleteConfirmData?.name || "" })}
        message={t("mcp.confirmDeleteMessage", {
          name: deleteConfirmData?.name || "",
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
        variant="danger"
      />
    </div>
  );
}
