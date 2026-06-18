import { Star } from "lucide-react";
import { Permission } from "../../types";
import type {
  CoreAppRouteContribution,
  CoreMessageActionContribution,
  CoreUserMenuContribution,
} from "../../extensions/coreContributions";

export const FEEDBACK_PLUGIN_ID = "feedback";

export const FEEDBACK_APP_ROUTE_CONTRIBUTION: CoreAppRouteContribution = {
  id: "feedback",
  pluginId: FEEDBACK_PLUGIN_ID,
  insertAfterId: "settings",
  path: "/feedback",
  seoTitle: "seo.feedback.title",
  seoDescription: "seo.feedback.description",
  tab: "feedback",
  permissions: [Permission.FEEDBACK_READ],
  redirectTo: "/chat",
  showNoPermissionToast: true,
  area: "app_route",
};

export const FEEDBACK_USER_MENU_CONTRIBUTION: CoreUserMenuContribution = {
  id: "feedback",
  pluginId: FEEDBACK_PLUGIN_ID,
  path: "/feedback",
  labelKey: "nav.feedback",
  icon: Star,
  requiredAnyPermissions: [Permission.FEEDBACK_READ],
  group: "system",
  area: "user_menu",
};

export const FEEDBACK_MESSAGE_ACTION_CONTRIBUTION: CoreMessageActionContribution = {
  id: "feedback:message-feedback",
  pluginId: FEEDBACK_PLUGIN_ID,
  action: "feedback",
  area: "message_action",
};

export const FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS = {
  appRoutes: [FEEDBACK_APP_ROUTE_CONTRIBUTION],
  userMenuItems: [FEEDBACK_USER_MENU_CONTRIBUTION],
  messageActions: [FEEDBACK_MESSAGE_ACTION_CONTRIBUTION],
} as const;
