export type CoreTabType =
  | "chat"
  | "persona"
  | "skills"
  | "marketplace"
  | "plugins"
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

export type PluginTabType = string & {};

export type TabType = CoreTabType | PluginTabType;
