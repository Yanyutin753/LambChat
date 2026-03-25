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
    icon: "🔍",
    titleKey: "webSearch",
    descKey: "webSearchDesc",
    gradient: "from-sky-500 to-blue-600",
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
    labelKey: "sandboxExecution",
    label: "FastAPI",
    color: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
  },
  {
    labelKey: "harnessEngineeringAgent",
    label: "React 19",
    color: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  {
    labelKey: "customSkillsMcp",
    label: "MongoDB",
    color: "bg-green-500/10 text-green-600 dark:text-green-400",
  },
];

export const MAIN_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/login-page.png", altKey: "loginPage" },
  { src: "/images/best-practice/chat-home.png", altKey: "chatInterface" },
  {
    src: "/images/best-practice/chat-response.png",
    altKey: "streamingResponse",
  },
  { src: "/images/best-practice/share-dialog.png", altKey: "shareDialog" },
];

export const MGMT_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/skills-page.png", altKey: "skills" },
  { src: "/images/best-practice/mcp-page.png", altKey: "mcp" },
  { src: "/images/best-practice/settings-page.png", altKey: "settings" },
  { src: "/images/best-practice/feedback-page.png", altKey: "feedback" },
  { src: "/images/best-practice/shared-page.png", altKey: "shared" },
  { src: "/images/best-practice/roles-page.png", altKey: "roles" },
];

export const RESPONSIVE_SHOTS: ScreenshotItem[] = [
  { src: "/images/best-practice/mobile-view.png", altKey: "mobile" },
  { src: "/images/best-practice/tablet-view.png", altKey: "tablet" },
];

export const STATS = [
  { num: "14", key: "settingCategories" },
  { num: "4", key: "agentTypes" },
  { num: "4", key: "languages" },
  { num: "3+", key: "oauthProviders" },
  { num: "SSE", key: "streamingOutput" },
];
