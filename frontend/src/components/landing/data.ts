export interface FeatureItem {
  icon: string;
  titleKey: string;
  descKey: string;
  gradient: string;
}

export interface ScreenshotItem {
  src: string;
  altKey: string;
}

export const FEATURES: FeatureItem[] = [
  {
    icon: "🤖",
    titleKey: "agentSystem",
    descKey: "agentSystemDesc",
    gradient: "from-violet-500 to-purple-600",
  },
  {
    icon: "🧠",
    titleKey: "modelManagement",
    descKey: "modelManagementDesc",
    gradient: "from-cyan-500 to-blue-600",
  },
  {
    icon: "🔌",
    titleKey: "mcpIntegration",
    descKey: "mcpIntegrationDesc",
    gradient: "from-emerald-500 to-teal-600",
  },
  {
    icon: "🛠️",
    titleKey: "skillsSystem",
    descKey: "skillsSystemDesc",
    gradient: "from-amber-500 to-orange-600",
  },
  {
    icon: "💬",
    titleKey: "feedbackSystem",
    descKey: "feedbackSystemDesc",
    gradient: "from-rose-500 to-pink-600",
  },
  {
    icon: "📁",
    titleKey: "documentSupport",
    descKey: "documentSupportDesc",
    gradient: "from-indigo-500 to-blue-600",
  },
  {
    icon: "🔄",
    titleKey: "realtimeStorage",
    descKey: "realtimeStorageDesc",
    gradient: "from-teal-500 to-cyan-600",
  },
  {
    icon: "🔐",
    titleKey: "securityAuth",
    descKey: "securityAuthDesc",
    gradient: "from-red-500 to-rose-600",
  },
  {
    icon: "⚙️",
    titleKey: "taskManagement",
    descKey: "taskManagementDesc",
    gradient: "from-orange-500 to-amber-600",
  },
  {
    icon: "🔗",
    titleKey: "channelsIntegrations",
    descKey: "channelsIntegrationsDesc",
    gradient: "from-blue-500 to-sky-600",
  },
  {
    icon: "📊",
    titleKey: "observability",
    descKey: "observabilityDesc",
    gradient: "from-green-500 to-emerald-600",
  },
  {
    icon: "🎨",
    titleKey: "frontendFeatures",
    descKey: "frontendFeaturesDesc",
    gradient: "from-fuchsia-500 to-pink-600",
  },
];

export const TECH_STACK = [
  {
    label: "LangGraph",
    color: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
  {
    label: "deepagents",
    color: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400",
  },
  {
    label: "MCP",
    color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  {
    label: "Skills",
    color: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  },
  {
    label: "E2B",
    color: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  },
];

export const MAIN_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/login-page.webp", altKey: "loginPage" },
  { src: "/images/best-practice/chat-home.webp", altKey: "chatInterface" },
  {
    src: "/images/best-practice/chat-response.webp",
    altKey: "streamingResponse",
  },
  { src: "/images/best-practice/share-dialog.webp", altKey: "shareDialog" },
];

export const MGMT_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/skills-page.webp", altKey: "skills" },
  { src: "/images/best-practice/mcp-page.webp", altKey: "mcp" },
  { src: "/images/best-practice/settings-page.webp", altKey: "settings" },
  { src: "/images/best-practice/feedback-page.webp", altKey: "feedback" },
  { src: "/images/best-practice/shared-page.webp", altKey: "shared" },
  { src: "/images/best-practice/roles-page.webp", altKey: "roles" },
];

export const RESPONSIVE_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/mobile-view.webp", altKey: "mobile" },
  { src: "/images/best-practice/tablet-view.webp", altKey: "tablet" },
];

export const STATS = [
  { num: "14+", key: "settingCategories" },
  { num: "3", key: "agentTypes" },
  { num: "5", key: "languages" },
  { num: "3+", key: "oauthProviders" },
  { num: "SSE", key: "streamingOutput" },
];
