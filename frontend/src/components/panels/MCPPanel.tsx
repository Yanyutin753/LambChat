import { useState, useMemo, useCallback } from "react";
import {
  Plus,
  X,
  Download,
  Upload,
  FolderOpen,
  Server,
  Check,
  Pencil,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { MCPPanelSkeleton } from "../skeletons";
import { Pagination } from "../common/Pagination";
import {
  Button,
  Checkbox,
  IconButton,
  PanelFooterActions,
  Textarea,
} from "../common";
import { MCPServerCard } from "../mcp/MCPServerCard";
import { MCPServerToolsSidebar } from "../mcp/MCPServerToolsSidebar";
import { MCPServerForm } from "../mcp/MCPServerForm";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { EditorSidebar } from "../common/EditorSidebar";
import { resolveMCPServerFormSystemMode } from "../mcp/mcpServerEditor";
import { useMCP } from "../../hooks/useMcp";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { MCPServerResponse, MCPServerCreate } from "../../types";

export function MCPPanel() {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  // Pagination state
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const handleSearchQueryChange = useCallback((query: string) => {
    setPage(1);
    setSearchQuery(query);
  }, []);
  const listParams = useMemo(
    () => ({
      skip: (page - 1) * pageSize,
      limit: pageSize,
      q: searchQuery.trim() || undefined,
    }),
    [page, pageSize, searchQuery],
  );
  const {
    servers,
    total,
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
  } = useMCP({ listParams });
  const { hasAnyPermission, user } = useAuth();

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
  const [toolsSidebarServer, setToolsSidebarServer] =
    useState<MCPServerResponse | null>(null);

  // Delete confirmation dialog state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
    isSystem: boolean;
  } | null>(null);

  const canRead = hasAnyPermission([Permission.MCP_READ]);
  const canWrite = hasAnyPermission([
    Permission.MCP_ADMIN,
    Permission.MCP_WRITE_SSE,
    Permission.MCP_WRITE_HTTP,
  ]);
  const canAdmin = hasAnyPermission([Permission.MCP_ADMIN]);

  // 动态生成用户可以使用的传输类型权限
  const allowedTransports = [
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_SSE])
      ? Permission.MCP_WRITE_SSE
      : null,
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_HTTP])
      ? Permission.MCP_WRITE_HTTP
      : null,
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_SANDBOX])
      ? Permission.MCP_WRITE_SANDBOX
      : null,
  ].filter(Boolean) as Permission[];
  // Note: canDelete permission is checked server-side
  // Client-side uses canWrite for UI actions, server validates actual permissions

  const filteredServers = servers;
  const paginatedServers = servers;
  const formIsSystemServer = resolveMCPServerFormSystemMode({
    isCreating,
    createAsSystem,
    changeToSystem,
  });

  const handleCreate = useCallback(async () => {
    setIsCreating(true);
    setEditingServer(null);
    setCreateAsSystem(false);
    setChangeToSystem(false);
    setShowModal(true);
  }, []);

  const handleEdit = useCallback((server: MCPServerResponse) => {
    setEditingServer(server);
    setIsCreating(false);
    setCreateAsSystem(false);
    setChangeToSystem(server.is_system); // Initialize with current type
    setShowModal(true);
  }, []);

  const handleSave = useCallback(
    async (data: MCPServerCreate): Promise<boolean> => {
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
                const updated = await updateServer(
                  editingServer.name,
                  data,
                  true,
                );
                success = updated !== null;
                if (success) {
                  toast.success(t("mcp.promoteSuccess"));
                } else {
                  toast.error(t("mcp.updateFailed"));
                }
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
                const updated = await updateServer(
                  editingServer.name,
                  data,
                  false,
                );
                success = updated !== null;
                if (success) {
                  toast.success(t("mcp.demoteSuccess"));
                } else {
                  toast.error(t("mcp.updateFailed"));
                }
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
    },
    [
      isCreating,
      editingServer,
      createAsSystem,
      changeToSystem,
      canAdmin,
      createServer,
      updateServer,
      promoteServer,
      demoteServer,
      user?.id,
      t,
    ],
  );

  const handleCancel = useCallback(() => {
    setShowModal(false);
    setEditingServer(null);
    setIsCreating(false);
    setCreateAsSystem(false);
    setChangeToSystem(false);
  }, []);

  const handleDelete = useCallback(
    async (name: string, isSystem: boolean = false) => {
      setDeleteConfirmData({ name, isSystem });
      setIsDeleteConfirmOpen(true);
    },
    [],
  );

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

  const handleToggle = useCallback(
    async (name: string) => {
      await toggleServer(name);
    },
    [toggleServer],
  );

  // Stable callback for tool toggled — avoids inline arrow in .map()
  const handleToolToggled = useCallback(() => {
    // Notify useTools hook to refresh conversation tool state
    window.dispatchEvent(new CustomEvent("mcp-tools-changed"));
  }, []);

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
          message: t("mcp.invalidFormat", "格式无效：缺少 mcpServers 对象"),
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
    } catch {
      setImportResult({
        success: false,
        message: t("mcp.invalidJson", "无效的 JSON 格式"),
      });
      toast.error(t("mcp.invalidJson"));
    }
  };

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-theme-text-secondary">
        {t("mcp.noPermission")}
      </div>
    );
  }

  const isInitialLoading =
    isLoading && servers.length === 0 && searchQuery.trim().length === 0;

  if (isInitialLoading) {
    return <MCPPanelSkeleton />;
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("mcp.title")}
        subtitle={t("mcp.subtitle")}
        icon={<Server size={20} className="text-theme-text-secondary" />}
        searchValue={searchQuery}
        onSearchChange={handleSearchQueryChange}
        searchPlaceholder={t("mcp.searchPlaceholder")}
        actions={
          canWrite && (
            <>
              <Button
                onClick={handleImportClick}
                leftIcon={<Upload size={16} />}
                title={t("mcp.importFromJSON")}
              >
                <span className="hidden sm:inline">{t("common.import")}</span>
              </Button>
              <Button
                onClick={handleExport}
                leftIcon={<Download size={16} />}
                title={t("mcp.exportToJSON")}
              >
                <span className="hidden sm:inline">{t("common.export")}</span>
              </Button>
              <Button
                variant="primary"
                onClick={handleCreate}
                leftIcon={<Plus size={16} />}
              >
                <span className="hidden sm:inline">{t("mcp.addServer")}</span>
              </Button>
            </>
          )
        }
      />

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <IconButton
            aria-label={t("common.close")}
            icon={<X size={18} />}
            onClick={clearError}
            className="hover:bg-red-100 dark:hover:bg-red-900/50"
          />
        </div>
      )}

      {/* Servers Grid */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        {filteredServers.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-theme-text-secondary">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-stone-100 dark:bg-stone-800 mb-4">
              <FolderOpen
                size={28}
                className="text-stone-400 dark:text-stone-500"
              />
            </div>
            <p className="text-center text-sm">
              {searchQuery ? t("mcp.noMatchingServers") : t("mcp.noServers")}
            </p>
            {!searchQuery && canWrite && (
              <Button
                variant="ghost"
                onClick={handleCreate}
                className="mt-3 text-sm font-medium text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] transition-colors"
              >
                {t("mcp.addFirst")}
              </Button>
            )}
          </div>
        ) : (
          <div className="grid auto-grid-cols gap-3">
            {paginatedServers.map((server) => (
              <MCPServerCard
                key={server.name}
                server={server}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onClick={() => setToolsSidebarServer(server)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="glass-divider px-3 py-3 sm:px-4">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onChange={setPage}
          />
        </div>
      )}

      {/* Form Sidebar */}
      <EditorSidebar
        open={showModal}
        onClose={handleCancel}
        title={
          isCreating
            ? t("mcp.addNew")
            : t("mcp.editServer", { name: editingServer?.name })
        }
        icon={isCreating ? <Plus size={16} /> : <Pencil size={16} />}
        width="wide"
      >
        <div className="es-form" style={{ gap: 0 }}>
          {/* Admin option for creating system server */}
          {isCreating && canAdmin && (
            <label className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 mb-4 transition-colors hover:bg-[var(--theme-bg-subtle)]">
              <Checkbox
                size="sm"
                checked={createAsSystem}
                onChange={() => setCreateAsSystem(!createAsSystem)}
              />
              <span className="text-sm font-medium text-[var(--theme-text)]">
                {t("mcp.createAsSystem")}
              </span>
            </label>
          )}
          {/* Admin option for changing server type when editing */}
          {!isCreating && editingServer && canAdmin && (
            <label className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 mb-4 transition-colors hover:bg-[var(--theme-bg-subtle)]">
              <Checkbox
                size="sm"
                checked={changeToSystem}
                onChange={() => setChangeToSystem(!changeToSystem)}
              />
              <span className="text-sm font-medium text-[var(--theme-text)]">
                {changeToSystem
                  ? t("mcp.systemServerVisible")
                  : t("mcp.userServerVisible")}
              </span>
            </label>
          )}
          <MCPServerForm
            server={editingServer}
            onSave={handleSave}
            onCancel={handleCancel}
            isLoading={isLoading}
            allowedTransports={allowedTransports}
            isSystemServer={formIsSystemServer}
            onToolPoliciesChanged={handleToolToggled}
          />
        </div>
      </EditorSidebar>

      {/* Import Sidebar */}
      <EditorSidebar
        open={showImportModal}
        onClose={() => setShowImportModal(false)}
        title={t("mcp.importServers")}
        icon={<Download size={16} />}
        width="wide"
        footer={
          <PanelFooterActions>
            <Button onClick={() => setShowImportModal(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="primary"
              onClick={handleImport}
              disabled={isLoading || !importJson.trim()}
              loading={isLoading}
              leftIcon={<Upload size={18} />}
            >
              {t("common.import")}
            </Button>
          </PanelFooterActions>
        }
      >
        <div className="es-form">
          <div className="es-field">
            <label className="es-label">{t("mcp.jsonConfig")}</label>
            <Textarea
              value={importJson}
              onChange={(e) => setImportJson(e.target.value)}
              rows={8}
              placeholder={`{
  "mcpServers": {
    "server-name": {
      "transport": "sse",
      "url": "http://localhost:3000/sse",
      "enabled": true
    }
  }
}`}
              className="es-textarea font-mono"
            />
          </div>

          <div className="es-field">
            <label className="group flex cursor-pointer items-center gap-2.5 es-label rounded-lg px-1 py-1 transition-colors hover:bg-[var(--theme-bg-subtle)]">
              <Checkbox
                size="sm"
                checked={importOverwrite}
                onChange={() => setImportOverwrite(!importOverwrite)}
              />
              {t("mcp.overwriteExisting")}
            </label>
          </div>

          {importResult && (
            <div
              className={`flex items-center gap-2.5 rounded-lg border p-3 ${
                importResult.success
                  ? "bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-950/20 dark:border-emerald-800/40 dark:text-emerald-400"
                  : "bg-red-50 border-red-200 text-red-700 dark:bg-red-950/20 dark:border-red-800/40 dark:text-red-400"
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
        </div>
      </EditorSidebar>

      {/* Tools Sidebar */}
      <EditorSidebar
        open={toolsSidebarServer !== null}
        onClose={() => setToolsSidebarServer(null)}
        title={toolsSidebarServer?.name ?? ""}
        icon={<Wrench size={16} />}
        width="wide"
      >
        {toolsSidebarServer && (
          <MCPServerToolsSidebar
            key={toolsSidebarServer.name}
            server={toolsSidebarServer}
            onToolToggled={handleToolToggled}
          />
        )}
      </EditorSidebar>

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
