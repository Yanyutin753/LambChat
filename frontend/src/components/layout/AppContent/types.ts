export type TabType =
  | "chat"
  | "persona"
  | "skills"
  | "marketplace"
  | "users"
  | "roles"
  | "settings"
  | "mcp"
  | "feedback"
  | "channels"
  | "agents"
  | "files"
  | "notifications"
  | "memory"
  | "team"
  | "scheduled-tasks"
  | "usage";

export interface ChatAppContentProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: import("../../../types").VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
}
