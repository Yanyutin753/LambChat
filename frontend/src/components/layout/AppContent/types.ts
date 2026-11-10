export type TabType =
  | "chat"
  | "assistants"
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
  | "bookmarks"
  | "notifications"
  | "memory"
  | "team"
  | "scheduled-tasks"
  | "usage";

export interface ChatAppContentProps {
  embedded?: boolean;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
}
