/** Local-only UI fixture server. No requests are forwarded to a real API. */
import { createServer } from "vite";
import { Permission, type PermissionsResponse } from "../src/types/auth";

const now = "2026-09-30T08:00:00Z";
const labels = [
  "季度业务分析",
  "产品研究与洞察",
  "客户支持知识库",
  "工程质量检查",
  "多语言内容交付",
  "跨部门项目协作与长期计划复盘",
];
const rows = (make: (i: number, name: string) => object) =>
  Array.from({ length: 65 }, (_, i) => ({
    created_at: now,
    updated_at: now,
    ...make(
      i,
      `${labels[i % labels.length]} ${String(i + 1).padStart(2, "0")}`,
    ),
  }));
const tags = ["研究", "工程", "写作", "团队协作"];
const localize = (text: string) =>
  Object.fromEntries(
    ["zh", "en", "ja", "ko", "ru"].map((lang) => [lang, text]),
  );
const user = {
  id: "preview-user",
  username: "Panel Preview",
  email: "preview@example.test",
  roles: ["admin"],
  permissions: Object.values(Permission),
  is_active: true,
  created_at: now,
  updated_at: now,
};
const agents = ["fast", "search", "team"].map((id, i) => ({
  id,
  name: ["通用助手", "研究助手", "团队助手"][i],
  description: "完成研究、分析和内容交付任务",
  enabled: true,
  version: "1.0",
  icon: "Bot",
  labels: {},
  sort_order: i,
  options: {},
}));
const users = rows((i, name) => ({
  ...user,
  id: `user-${i}`,
  username: name,
  email: `member-${i}@example.test`,
  is_active: i % 4 !== 0,
  roles: [i % 3 === 0 ? "admin" : "member"],
}));
const roles = rows((i, name) => ({
  id: `role-${i}`,
  name,
  description: "管理团队成员、模型与工具访问权限",
  permissions: Object.values(Permission).slice(0, (i % 10) + 2),
  limits: {},
  is_system: i < 2,
}));
const skills = rows((i, name) => ({
  skill_name: name,
  description: "从需求分析到成果检查的完整流程，提供结构化、可复用的专业交付。",
  tags: tags.slice(0, (i % 4) + 1),
  files: ["SKILL.md", "references/guide.md"],
  file_count: 2,
  enabled: i % 4 !== 0,
  installed_from: "manual",
  is_published: i % 3 === 0,
  marketplace_is_active: true,
  is_favorite: i % 5 === 0,
  is_pinned: i === 0,
}));
const servers = rows((i, name) => ({
  name,
  transport: i % 2 ? "sse" : "streamable_http",
  enabled: i % 4 !== 0,
  url: `https://tools-${i}.example.test/mcp`,
  is_system: i % 3 === 0,
  can_edit: true,
  allowed_roles: [],
  role_quotas: {},
}));
const presets = rows((i, name) => ({
  id: `persona-${i}`,
  name,
  description: "帮助团队梳理复杂信息，产出可追溯的分析与行动建议。",
  tags: tags.slice(0, (i % 4) + 1),
  scope: i % 2 ? "user" : "global",
  owner_user_id: user.id,
  system_prompt: "你是一名专业的研究助手。",
  starter_prompts: [{ text: "帮我总结本周的项目进展" }],
  skill_names: [],
  mcp_server_names: [],
  visibility: "public",
  status: "published",
  version: 1,
  usage_count: 120 + i,
  is_favorite: i % 5 === 0,
}));
const teams = rows((i, name) => ({
  id: `team-${i}`,
  name,
  description: "由研究、写作与校对成员共同完成任务，保持上下文一致。",
  owner_user_id: user.id,
  tags: tags.slice(0, (i % 4) + 1),
  members: [0, 1, 2].map((n) => ({
    member_id: `member-${n}`,
    persona_preset_id: `persona-${n}`,
    role_name: ["研究员", "编辑", "审阅者"][n],
    role_tags: [],
    role_instructions: "完成负责的工作并汇报结果。",
    position: n,
    enabled: true,
  })),
  team_instructions: "协作完成项目",
  starter_prompts: [],
  visibility: "private",
  is_pinned: i === 0,
  is_favorite: i % 5 === 0,
}));
const memories = rows((i, title) => ({
  memory_id: `memory-${i}`,
  title,
  summary: "团队偏好简洁、准确且有据可查的回复。请保留关键约束与来源。",
  memory_type: ["user", "project", "reference"][i % 3],
  tags: tags.slice(0, (i % 4) + 1),
  content: "项目背景与执行记录\n\n需要在移动端和桌面端维持一致体验。",
  source: "manual",
  access_count: i * 2,
  has_full_content: true,
}));
const tasks = rows((i, name) => ({
  id: `task-${i}`,
  name,
  description: "收集近期进展并生成项目周报",
  agent_id: "fast",
  trigger_type: "cron",
  trigger_config: { cron: "0 9 * * 1", expression: "0 9 * * 1" },
  timezone: "Asia/Shanghai",
  input_payload: { message: "生成本周项目进展摘要" },
  status: i % 4 ? "active" : "paused",
  enabled: i % 4 !== 0,
  run_on_start: false,
  max_retries: 2,
  timeout_seconds: 300,
  owner_id: user.id,
  source_session_id: null,
  source_run_id: null,
  created_by: "user",
  last_run_at: now,
  last_run_status: i % 5 ? "success" : "failed",
  last_run_id: `run-${i}`,
  total_runs: i + 2,
  unread_count: i % 3,
}));
const bookmarks = rows((i, name) => ({
  id: `bookmark-${i}`,
  user_id: user.id,
  session_id: `session-${i}`,
  message_id: `message-${i}`,
  run_id: `run-${i}`,
  label: name,
  session_name: `项目讨论 · ${name}`,
  session_is_active: i % 4 !== 0,
}));
const notifications = rows((i, name) => ({
  id: `notice-${i}`,
  title_i18n: localize(name),
  content_i18n: localize(
    "本次更新改进了模型配置与团队协作体验。已有工作可继续进行。",
  ),
  type: ["info", "success", "warning", "maintenance"][i % 4],
  start_time: null,
  end_time: null,
  is_active: i % 3 !== 0,
  created_by: user.id,
}));
const feedback = rows((i, name) => ({
  id: `feedback-${i}`,
  user_id: user.id,
  username: name,
  session_id: `session-${i}`,
  run_id: `run-${i}`,
  rating: i % 3 ? "up" : "down",
  comment:
    i % 3
      ? "结果结构清晰，参考资料完整，节省了整理时间。"
      : "长列表在移动端不易浏览，希望分页位置更一致。",
  attachments: [],
}));
const stats = {
  total_requests: 65,
  total_input_tokens: 132000,
  total_output_tokens: 46000,
  total_tokens: 178000,
  total_cache_creation_tokens: 0,
  total_cache_read_tokens: 42000,
  total_cost_usd: 2.18,
  unpriced_requests: 0,
  total_duration: 2600,
};
const feedbackStats = {
  total_count: 65,
  up_count: 43,
  down_count: 22,
  up_percentage: 66.2,
};
const logs = rows((i, name) => ({
  trace_id: `trace-${i}`,
  session_id: `session-${i}`,
  user_id: user.id,
  username: name,
  agent_name: "通用助手",
  team_id: "",
  team_name: "",
  persona_preset_id: "",
  persona_preset_name: "",
  source: "chat",
  scheduled_task_id: "",
  scheduled_task_run_id: "",
  scheduled_task_trigger_type: "",
  model: "preview-model",
  input_tokens: 2000,
  output_tokens: 600,
  total_tokens: 2600,
  cache_creation_tokens: 0,
  cache_read_tokens: 500,
  cost_usd: 0.03,
  cost_available: true,
  duration: 12.8,
  started_at: now,
  completed_at: now,
  status: i % 7 ? "completed" : "error",
  error_message: i % 7 ? "" : "Preview timeout",
  step_count: 3,
  tool_calls: 2,
}));
const files = rows((i, name) => ({
  id: `file-${i}`,
  file_key: `preview/${i}.md`,
  file_name: `${name}.md`,
  file_type: "document",
  mime_type: "text/markdown",
  file_size: 1800 + i * 100,
  url: "/preview-document.md",
  session_id: `session-${i}`,
  session_name: name,
  trace_id: `trace-${i}`,
  project_id: null,
  user_id: user.id,
  source: "reveal_file",
  description: "项目文档与交付记录",
  original_path: `/workspace/${name}.md`,
  is_favorite: i % 5 === 0,
  card_preview: {
    kind: "markdown",
    title: name,
    text: "## 研究结论\n\n整理关键发现、证据与后续行动。",
  },
}));
const models = rows((i, name) => ({
  id: `model-${i}`,
  label: name,
  value: `preview-model-${i}`,
  provider: "openai",
  enabled: i % 4 !== 0,
  sort_order: i,
  description: "用于分析、写作和工具调用",
  api_key: "",
  base_url: "https://models.example.test/v1",
  protocol: "openai",
  profile: {},
  supports_thinking: false,
}));
const settings = {
  settings: {
    frontend: [
      {
        key: "DEFAULT_AGENT",
        value: "fast",
        default_value: "fast",
        type: "string",
        category: "frontend",
        subcategory: "display",
        description: "settingDesc.DEFAULT_AGENT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "ADMIN_CONTACT_EMAIL",
        value: "",
        default_value: "",
        type: "string",
        category: "frontend",
        subcategory: "contact",
        description: "settingDesc.ADMIN_CONTACT_EMAIL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "ADMIN_CONTACT_URL",
        value: "",
        default_value: "",
        type: "string",
        category: "frontend",
        subcategory: "contact",
        description: "settingDesc.ADMIN_CONTACT_URL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    llm: [
      {
        key: "DEFAULT_MODEL_ID",
        value: "",
        default_value: "",
        type: "string",
        category: "llm",
        subcategory: "model",
        description: "settingDesc.DEFAULT_MODEL_ID",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LLM_MAX_RETRIES",
        value: 3,
        default_value: 3,
        type: "number",
        category: "llm",
        subcategory: "retry",
        description: "settingDesc.LLM_MAX_RETRIES",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LLM_RETRY_DELAY",
        value: 1.0,
        default_value: 1.0,
        type: "number",
        category: "llm",
        subcategory: "retry",
        description: "settingDesc.LLM_RETRY_DELAY",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LLM_REQUEST_TIMEOUT",
        value: 0.0,
        default_value: 0.0,
        type: "number",
        category: "llm",
        subcategory: "retry",
        description: "settingDesc.LLM_REQUEST_TIMEOUT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LLM_FIRST_EVENT_TIMEOUT",
        value: 30.0,
        default_value: 30.0,
        type: "number",
        category: "llm",
        subcategory: "retry",
        description: "settingDesc.LLM_FIRST_EVENT_TIMEOUT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    agent: [
      {
        key: "APP_BASE_URL",
        value: "",
        default_value: "",
        type: "string",
        category: "agent",
        subcategory: "general",
        description: "settingDesc.APP_BASE_URL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "DEBUG",
        value: false,
        default_value: false,
        type: "boolean",
        category: "agent",
        subcategory: "general",
        description: "settingDesc.DEBUG",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LOG_LEVEL",
        value: "INFO",
        default_value: "INFO",
        type: "string",
        category: "agent",
        subcategory: "general",
        description: "settingDesc.LOG_LEVEL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    session: [
      {
        key: "SESSION_MAX_RUNS_PER_SESSION",
        value: 1000,
        default_value: 1000,
        type: "number",
        category: "session",
        subcategory: "general",
        description: "settingDesc.SESSION_MAX_RUNS_PER_SESSION",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "ENABLE_MESSAGE_HISTORY",
        value: true,
        default_value: true,
        type: "boolean",
        category: "session",
        subcategory: "general",
        description: "settingDesc.ENABLE_MESSAGE_HISTORY",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "SSE_CACHE_TTL",
        value: 86400,
        default_value: 86400,
        type: "number",
        category: "session",
        subcategory: "general",
        description: "settingDesc.SSE_CACHE_TTL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "SESSION_EVENT_MONGO_BUFFER_MAX",
        value: 10000,
        default_value: 10000,
        type: "number",
        category: "session",
        subcategory: "events",
        description: "settingDesc.SESSION_EVENT_MONGO_BUFFER_MAX",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "SESSION_EVENT_READ_DEFAULT_LIMIT",
        value: 1000,
        default_value: 1000,
        type: "number",
        category: "session",
        subcategory: "events",
        description: "settingDesc.SESSION_EVENT_READ_DEFAULT_LIMIT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    file_upload: [
      {
        key: "FEISHU_UPLOAD_BYTES_MAX_SIZE",
        value: 20971520,
        default_value: 20971520,
        type: "number",
        category: "file_upload",
        subcategory: "feishu",
        description: "settingDesc.FEISHU_UPLOAD_BYTES_MAX_SIZE",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "LOCAL_STORAGE_PATH",
        value: "./uploads",
        default_value: "./uploads",
        type: "string",
        category: "file_upload",
        subcategory: "storage",
        description: "settingDesc.LOCAL_STORAGE_PATH",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "ENABLE_LOCAL_FILESYSTEM_FALLBACK",
        value: true,
        default_value: true,
        type: "boolean",
        category: "file_upload",
        subcategory: "storage",
        description: "settingDesc.ENABLE_LOCAL_FILESYSTEM_FALLBACK",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "FILE_UPLOAD_MAX_SIZE_IMAGE",
        value: 40,
        default_value: 40,
        type: "number",
        category: "file_upload",
        subcategory: "limits",
        description: "settingDesc.FILE_UPLOAD_MAX_SIZE_IMAGE",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "FILE_UPLOAD_MAX_SIZE_VIDEO",
        value: 100,
        default_value: 100,
        type: "number",
        category: "file_upload",
        subcategory: "limits",
        description: "settingDesc.FILE_UPLOAD_MAX_SIZE_VIDEO",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    memory: [
      {
        key: "ENABLE_MEMORY",
        value: false,
        default_value: false,
        type: "boolean",
        category: "memory",
        subcategory: "general",
        description: "settingDesc.ENABLE_MEMORY",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "ENABLE_MEMORY_VFS",
        value: false,
        default_value: false,
        type: "boolean",
        category: "memory",
        subcategory: "vfs",
        description: "settingDesc.ENABLE_MEMORY_VFS",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    tools: [
      {
        key: "ENABLE_MCP",
        value: true,
        default_value: true,
        type: "boolean",
        category: "tools",
        subcategory: "mcp",
        description: "settingDesc.ENABLE_MCP",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "MCP_GLOBAL_CACHE_TTL_SECONDS",
        value: 900,
        default_value: 900,
        type: "number",
        category: "tools",
        subcategory: "mcp",
        description: "settingDesc.MCP_GLOBAL_CACHE_TTL_SECONDS",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "MCP_GLOBAL_MAX_ENTRIES",
        value: 100,
        default_value: 100,
        type: "number",
        category: "tools",
        subcategory: "mcp",
        description: "settingDesc.MCP_GLOBAL_MAX_ENTRIES",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "MCP_GLOBAL_INIT_WAIT_SECONDS",
        value: 5,
        default_value: 5,
        type: "number",
        category: "tools",
        subcategory: "mcp",
        description: "settingDesc.MCP_GLOBAL_INIT_WAIT_SECONDS",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "MCP_GLOBAL_WARMUP_CONCURRENCY",
        value: 5,
        default_value: 5,
        type: "number",
        category: "tools",
        subcategory: "mcp",
        description: "settingDesc.MCP_GLOBAL_WARMUP_CONCURRENCY",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    sandbox: [
      {
        key: "ENABLE_SANDBOX",
        value: false,
        default_value: false,
        type: "boolean",
        category: "sandbox",
        subcategory: "general",
        description: "settingDesc.ENABLE_SANDBOX",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "SANDBOX_LOCAL_EXEC_TIMEOUT",
        value: 120,
        default_value: 120,
        type: "number",
        category: "sandbox",
        subcategory: "general",
        description: "settingDesc.SANDBOX_LOCAL_EXEC_TIMEOUT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "SANDBOX_PAUSE_WHEN_IDLE",
        value: true,
        default_value: true,
        type: "boolean",
        category: "sandbox",
        subcategory: "general",
        description: "settingDesc.SANDBOX_PAUSE_WHEN_IDLE",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "DAYTONA_SERVER_URL",
        value: "",
        default_value: "",
        type: "string",
        category: "sandbox",
        subcategory: "daytona",
        description: "settingDesc.DAYTONA_SERVER_URL",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
      {
        key: "DAYTONA_TIMEOUT",
        value: 180,
        default_value: 180,
        type: "number",
        category: "sandbox",
        subcategory: "daytona",
        description: "settingDesc.DAYTONA_TIMEOUT",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
    skills: [
      {
        key: "ENABLE_SKILLS",
        value: true,
        default_value: true,
        type: "boolean",
        category: "skills",
        subcategory: "general",
        description: "settingDesc.ENABLE_SKILLS",
        requires_restart: false,
        is_sensitive: false,
        frontend_visible: true,
      },
    ],
  },
};

function response(
  url: URL,
  scenario: string,
  chatState = "completed",
): unknown {
  const path = url.pathname.replace(/\/$/, "");
  const q = url.searchParams;
  const pageSize = Number(q.get("limit") ?? q.get("page_size") ?? 20);
  const skip = Number(
    q.get("skip") ??
      q.get("offset") ??
      (Number(q.get("page") ?? 1) - 1) * pageSize,
  );
  const paginate = (items: object[], key = "items", extra = {}) => {
    let data = scenario === "empty" ? [] : items;
    const search = (q.get("q") ?? q.get("search") ?? "").toLowerCase();
    if (search)
      data = data.filter((item) =>
        JSON.stringify(item).toLowerCase().includes(search),
      );
    return {
      [key]: data.slice(skip, skip + pageSize),
      total: data.length,
      skip,
      limit: pageSize,
      page: Math.floor(skip / pageSize) + 1,
      page_size: pageSize,
      has_more: skip + pageSize < data.length,
      ...extra,
    };
  };
  const all = (items: object[]) => (scenario === "empty" ? [] : items);
  if (["/api/auth/me", "/api/auth/profile"].includes(path)) return user;
  if (path === "/api/pricing/rates")
    return { base: "USD", rates: { USD: 1 }, synced_at: now };
  if (path === "/api/upload/config")
    return {
      enabled: false,
      uploadLimits: {
        image: 10485760,
        video: 52428800,
        audio: 20971520,
        document: 20971520,
        maxFiles: 10,
      },
    };
  if (path === "/api/settings") return settings;
  if (path === "/api/auth/permissions") {
    const permissions = Object.values(Permission).map((value) => ({
      value,
      label: value,
      description: value,
    }));
    return {
      groups: [{ name: "Permissions", permissions }],
      all_permissions: permissions,
    } satisfies PermissionsResponse;
  }
  if (path === "/api/users") return paginate(users, "users");
  if (path === "/api/roles") return paginate(roles, "roles");
  if (path === "/api/skills")
    return paginate(skills, "skills", {
      enabled_count: 48,
      available_tags: tags,
    });
  if (path.includes("/skills/") && path.includes("/files/"))
    return {
      content: "# 专业研究工作流\n\n1. 明确问题\n2. 收集证据\n3. 输出结论",
    };
  if (path.startsWith("/api/skills/"))
    return { ...skills[0], files: ["SKILL.md"] };
  if (path === "/api/mcp") return paginate(servers, "servers");
  if (path === "/api/env-vars")
    return {
      variables: all([
        { key: "PROJECT_API_TOKEN", value: "********" },
        {
          key: "RESEARCH_WORKSPACE_ACCESS_TOKEN_WITH_A_LONG_NAME",
          value: "********",
        },
      ]),
      count: scenario === "empty" ? 0 : 2,
    };
  if (path === "/api/tools")
    return {
      tools: all(
        servers.slice(0, 3).flatMap((server, index) => [
          {
            name: `${server.name}:search_documents`,
            description: "检索项目知识库，返回相关文档与来源。",
            category: "mcp",
            server: server.name,
            user_disabled: false,
          },
          {
            name: `${server.name}:read_document`,
            description:
              "读取完整文档内容，保留结构和来源信息，支持项目内较长的文档名称与描述。",
            category: "mcp",
            server: server.name,
            user_disabled: index === 1,
          },
        ]),
      ),
    };
  if (path.endsWith("/tools"))
    return {
      tools: [
        {
          name: "search_documents",
          description: "检索项目知识库",
          parameters: [],
        },
      ],
      count: 1,
    };
  if (path === "/api/marketplace/tags") return { tags };
  if (path === "/api/marketplace")
    return all(
      skills.map((s, i) => ({
        ...s,
        author: "LambChat Team",
        version: "1.2.0",
        install_count: i * 42,
        download_count: i * 42,
        is_active: i % 4 !== 0,
        is_owner: true,
        owner_username: "Preview",
        user_installed: false,
      })),
    );
  if (path === "/api/persona-presets") return paginate(presets, "presets");
  if (path.startsWith("/api/persona-presets/"))
    return presets.find((p) => path.endsWith(p.id)) ?? presets[0];
  if (path === "/api/teams") return paginate(teams, "teams");
  if (path.startsWith("/api/teams/"))
    return teams.find((p) => path.endsWith(p.id)) ?? teams[0];
  if (path === "/api/memory") return paginate(memories, "memories");
  if (path.startsWith("/api/memory/"))
    return memories.find((p) => path.endsWith(p.memory_id)) ?? memories[0];
  if (path === "/api/bookmarks")
    return { items: all(bookmarks), total: all(bookmarks).length };
  if (path === "/api/notifications/active") return [];
  if (path === "/api/notifications/admin") return paginate(notifications);
  if (path === "/api/feedback")
    return paginate(feedback, "items", { stats: feedbackStats });
  if (path === "/api/feedback/stats") return feedbackStats;
  if (path === "/api/usage/logs") return paginate(logs, "items", { stats });
  if (path === "/api/usage/stats") return stats;
  if (path === "/api/usage/dashboard")
    return {
      summary: {
        ...stats,
        total_tool_calls: 130,
        scheduled_runs: 12,
        failed_requests: 4,
        success_rate: 0.94,
        avg_tokens_per_request: 2738,
        avg_duration_per_request: 40,
        scheduled_share: 0.18,
        cache_read_share: 0.24,
        tool_calls_per_request: 2,
        max_duration: 90,
        peak_day: null,
      },
      daily: Array.from({ length: 14 }, (_, i) => ({
        date: `2026-09-${String(17 + i).padStart(2, "0")}`,
        requests: 24 + i * 3,
        tokens: 35000 + i * 5700,
        cost_usd: 0.4 + i * 0.13,
        duration: 360 + i * 70,
        scheduled_runs: 4 + i,
        failed_requests: i % 3,
        tool_calls: 32 + i * 5,
      })),
      top_agents: ["fast", "search", "team"].map((name, i) => ({
        id: name,
        name,
        requests: 40 - i * 9,
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
      top_teams: ["研究分析团队", "内容工作室", "产品研发组"].map(
        (name, i) => ({
          id: name,
          name,
          requests: 40 - i * 9,
          tokens: 68000 - i * 12000,
          cost_usd: 2.8 - i * 0.6,
          duration: 850 - i * 150,
          input_tokens: 45000,
          cache_creation_tokens: 3200,
          cache_read_tokens: 16000,
          cache_read_share: 0.35,
          zero_cache_requests: 4,
        }),
      ),
      top_personas: ["数据分析师", "产品设计师", "研究助理"].map((name, i) => ({
        id: name,
        name,
        requests: 40 - i * 9,
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
      top_models: ["model-0", "model-1", "model-2"].map((name, i) => ({
        id: name,
        name,
        requests: 40 - i * 9,
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
      top_users: ["林晓", "陈远", "苏晴"].map((name, i) => ({
        id: name,
        name,
        requests: 40 - i * 9,
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
      sources: ["agent", "team", "persona"].map((name, i) => ({
        id: name,
        name,
        requests: [30, 20, 15][i],
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
      triggers: ["cron", "interval"].map((name, i) => ({
        id: name,
        name,
        requests: [8, 4][i],
        tokens: 68000 - i * 12000,
        cost_usd: 2.8 - i * 0.6,
        duration: 850 - i * 150,
        input_tokens: 45000,
        cache_creation_tokens: 3200,
        cache_read_tokens: 16000,
        cache_read_share: 0.35,
        zero_cache_requests: 4,
      })),
    };
  if (path === "/api/scheduled-tasks") return paginate(tasks);
  if (path.startsWith("/api/scheduled-tasks/") && path.endsWith("/runs"))
    return paginate(
      rows((i) => ({
        id: `run-${i}`,
        task_id: "task-0",
        agent_id: "fast",
        trigger_type: "cron",
        status: i % 4 ? "success" : "failed",
        session_id: `session-${i}`,
        input_snapshot: {},
        output_result: "项目周报已生成",
        error_message: i % 4 ? null : "请求超时",
        retry_count: 0,
        started_at: now,
        finished_at: now,
        duration_ms: 12800,
      })),
    );
  if (path.startsWith("/api/scheduled-tasks/") && path.endsWith("/sessions"))
    return paginate(
      rows((i, name) => ({
        id: `session-${i}`,
        name,
        agent_id: "fast",
        is_active: true,
        metadata: {},
        unread_count: i % 3,
      })),
    );
  if (path.startsWith("/api/scheduled-tasks/"))
    return tasks.find((t) => path.endsWith(t.id)) ?? tasks[0];
  if (path === "/api/agents")
    return { agents, count: agents.length, default_agent: "fast" };
  if (path.startsWith("/api/agent/config/roles/"))
    return {
      allowed_agents: agents.map((a) => a.id),
      allowed_models: models.map((m) => m.id),
    };
  if (path.startsWith("/api/agent/config/"))
    return { agents, available_agents: agents.map((a) => a.id) };
  if (path === "/api/agent/models/providers/list")
    return [
      { value: "openai", protocol: "openai", prefixes: ["gpt-", "o3", "o4"] },
      { value: "anthropic", protocol: "anthropic", prefixes: ["claude-"] },
    ];
  if (path.startsWith("/api/agent/models"))
    return { models, total: models.length, default_model_id: "model-0" };
  if (path === "/api/files/revealed/stats") return { all: 65, document: 65 };
  if (path === "/api/files/revealed/sessions") return [];
  if (path === "/api/files/revealed") return paginate(files);
  if (path === "/api/files/revealed/grouped") {
    const groups = all(files).map((file, i) => ({
      session_id: file.session_id,
      session_name: file.session_name,
      file_count: i === 0 ? 4 : 3,
      files: [
        file,
        ...(i === 0
          ? [
              {
                ...file,
                id: "preview-drawing",
                file_name: "研究流程.excalidraw",
                file_key: "preview/workflow.excalidraw",
                original_path: "/workspace/研究流程.excalidraw",
                url: "/preview-document.excalidraw",
                mime_type: "application/json",
                card_preview: null,
              },
            ]
          : []),
        {
          ...file,
          id: `${file.id}-code`,
          file_name: `数据清洗-${i + 1}.py`,
          file_key: `preview/${i}.py`,
          original_path: `/workspace/数据清洗-${i + 1}.py`,
          url: "/preview-document.py",
          file_type: "code",
          mime_type: "text/x-python",
          card_preview: {
            kind: "code",
            language: "python",
            title: "数据处理",
            lines: [
              "import pandas as pd",
              "",
              "def summarize(data):",
              "    clean = data.dropna()",
              '    return clean.groupby("month").sum()',
              "",
              'report = summarize(pd.read_csv("metrics.csv"))',
            ],
          },
        },
        {
          ...file,
          id: `${file.id}-sheet`,
          file_name: `项目指标-${i + 1}.csv`,
          file_key: `preview/${i}.csv`,
          original_path: `/workspace/项目指标-${i + 1}.csv`,
          url: "/preview-document.csv",
          mime_type: "text/csv",
          card_preview: {
            kind: "text",
            title: "项目指标",
            text: "月份,交付数量,完成率\n六月,128,92%\n七月,156,96%\n八月,182,98%",
            badge: "CSV",
          },
        },
      ],
    }));
    return {
      sessions: groups.slice(skip, skip + pageSize),
      total_sessions: groups.length,
      page: Math.floor(skip / pageSize) + 1,
      page_size: pageSize,
    };
  }
  if (path === "/api/channels/types")
    return {
      types: ["feishu", "telegram", "slack"].map((channel_type) => ({
        channel_type,
        display_name: channel_type,
        description: "将专业助手连接到团队消息渠道",
        icon: "BotMessageSquare",
        capabilities: ["send_message", "group_chat"],
        config_schema: {},
        requires_webhook: false,
        requires_websocket: true,
        setup_guide: ["填写渠道配置并测试连接"],
        config_fields:
          channel_type === "feishu"
            ? []
            : [
                {
                  name: "workspace",
                  type: "text",
                  title: "Workspace",
                  required: true,
                },
                {
                  name: "token",
                  type: "password",
                  title: "Bot token",
                  sensitive: true,
                },
                {
                  name: "reply_mode",
                  type: "select",
                  title: "Reply mode",
                  default: "thread",
                  options: [
                    { value: "thread", label: "Thread" },
                    { value: "channel", label: "Channel" },
                  ],
                },
                {
                  name: "stream",
                  type: "toggle",
                  title: "Streaming",
                  default: true,
                },
              ],
      })),
    };
  if (path.startsWith("/api/channels/") && path.endsWith("/status"))
    return { channel_type: path.split("/")[3], enabled: true, connected: true };
  if (/^\/api\/channels\/[^/]+$/.test(path))
    return {
      channels: rows((i, name) => ({
        instance_id: `instance-${i}`,
        channel_type: path.split("/")[3],
        name,
        user_id: user.id,
        enabled: i % 4 !== 0,
        config: {},
        capabilities: ["send_message"],
        agent_id: "fast",
      })).slice(0, 5),
    };
  if (path.startsWith("/api/channels/"))
    return {
      instance_id: "instance-0",
      channel_type: path.split("/")[3],
      name: "项目协作渠道",
      user_id: user.id,
      enabled: true,
      config: { app_id: "cli_preview_only", workspace: "Preview workspace" },
      capabilities: ["send_message"],
      agent_id: "fast",
    };
  if (path === "/api/channels") return { channels: [] };
  if (path === "/api/share/public/preview-report") {
    const history = response(
      new URL("http://localhost/api/sessions/preview-report/events"),
      scenario,
      "completed",
    ) as { events: object[] };
    return {
      session: {
        id: "preview-report",
        name: "产品研究与交付计划",
        agent_id: "fast",
        agent_name: "通用助手",
        created_at: now,
      },
      events: history.events,
      owner: { username: "LambChat Demo" },
      share_type: "full",
      share_scope: "session",
    };
  }
  if (path === "/api/sessions/preview-report")
    return {
      id: "preview-report",
      user_id: user.id,
      agent_id: "fast",
      name: "产品研究与交付计划",
      is_active: true,
      created_at: now,
      updated_at: now,
      metadata: { current_run_id: "preview-run" },
    };
  if (path === "/api/chat/sessions/preview-report/status")
    return {
      session_id: "preview-report",
      run_id: "preview-run",
      status: ["working", "streaming"].includes(chatState)
        ? "running"
        : chatState === "error"
          ? "error"
          : "completed",
    };
  if (path === "/api/sessions/preview-report/events") {
    const active = ["working", "streaming"].includes(chatState);
    return {
      stream_run_id: active ? "preview-run" : null,
      events: [
        {
          id: "preview-user-message",
          event_type: "user:message",
          run_id: "preview-run",
          timestamp: now,
          data: {
            message_id: "preview-user-message",
            content: "请整理新产品的研究发现，并给出下一阶段的交付计划。",
            attachments: [],
          },
        },
        ...(!active
          ? [
              {
                id: "preview-thinking",
                event_type: "thinking",
                run_id: "preview-run",
                timestamp: now,
                data: {
                  content:
                    "正在整理研究资料、核对证据，并按优先级组织交付计划。",
                },
              },
            ]
          : []),
        ...(!active && chatState === "completed"
          ? [
              {
                id: "preview-answer",
                event_type: "message:chunk",
                run_id: "preview-run",
                timestamp: now,
                data: {
                  content:
                    '## 研究发现与交付计划\n\n已将需求归纳为三个重点：更清晰的工作入口、可追踪的执行过程，以及便于团队复用的成果。\n\n| 阶段 | 交付内容 | 验收方式 |\n| --- | --- | --- |\n| 需求确认 | 用户场景与优先级 | 团队评审 |\n| 原型验证 | 核心流程与交互原型 | 用户走查 |\n| 交付上线 | 功能实现与使用指南 | 多端验证 |\n\n### 下一步\n\n1. 确认目标用户和首要任务。\n2. 用原型验证关键路径。\n3. 将反馈整理为可执行的迭代清单。\n\n> 此会话为产品界面展示使用的演示数据。\n\n```python\nreport = summarize(source="quarterly_business_metrics.csv", columns=["month", "delivery_count", "completion_rate", "owner"])\n```',
                },
              },
            ]
          : []),
        {
          id: "preview-done",
          event_type:
            chatState === "error"
              ? "error"
              : chatState === "cancelled"
                ? "user:cancel"
                : "done",
          run_id: "preview-run",
          timestamp: now,
          data:
            chatState === "error"
              ? { error: "请求超时", type: "task_error", status: "error" }
              : { status: "completed" },
        },
      ].filter((event) => !active || event.id === "preview-user-message"),
      has_more_traces: false,
    };
  }
  if (path === "/api/sessions/preview-report/runs") {
    const runs = all(
      rows((i, name) => ({
        run_id: i === 0 ? "preview-run" : `preview-run-${i}`,
        trace_id: `preview-trace-${i}`,
        started_at: now,
        completed_at: now,
        status: "completed",
        event_count: 3,
        user_message: name,
      })),
    );
    return { session_id: "preview-report", runs, count: runs.length };
  }
  if (
    path.startsWith("/api/share/session/") ||
    path.startsWith("/api/share/project/")
  )
    return [];
  if (path === "/api/sessions")
    return paginate(
      rows((i, name) => ({
        id: i === 0 ? "preview-report" : `preview-session-${i}`,
        user_id: user.id,
        name,
        project_id: "preview-project",
        agent_id: "fast",
        is_active: true,
        metadata: {},
        unread_count: 0,
      })),
      "sessions",
    );
  if (path === "/api/projects")
    return all([
      {
        id: "preview-project",
        user_id: user.id,
        name: "跨部门项目协作与长期计划复盘",
        type: "custom",
        icon: "",
        sort_order: 0,
        created_at: now,
        updated_at: now,
      },
    ]);
  if (path === "/api/version")
    return {
      current_version: "2.13.0",
      latest_version: "2.13.0",
      has_update: false,
      release_assets: [
        "LambChat-v2.13.0-macOS.dmg",
        "LambChat-v2.13.0-Windows.msi",
        "LambChat-v2.13.0-Linux-x86_64.AppImage",
        "lambchat-daemon-x86_64-unknown-linux-gnu",
        "lambchat-daemon-aarch64-apple-darwin",
      ].map((name) => ({
        name,
        url: "https://example.test/preview-only",
        size: 64000000,
        content_type: "application/octet-stream",
      })),
    };
  if (path === "/api/sandbox/fs/cloud/status")
    return { state: "running", platform: "preview" };
  if (path === "/api/sandbox/fs/cloud/list") {
    const directory = url.searchParams.get("path") || "";
    return {
      entries:
        directory && directory !== "."
          ? [{ path: "研究资料/访谈笔记.md", is_dir: false }]
          : [
              { path: "研究资料", is_dir: true },
              { path: "今天吃什么.py", is_dir: false },
              { path: "随手记.txt", is_dir: false },
              { path: "交付计划与下一阶段验证清单.md", is_dir: false },
              { path: "品牌图标.png", is_dir: false },
            ],
    };
  }
  if (path === "/api/sandbox/fs/cloud/read") {
    const file = url.searchParams.get("path") || "";
    if (file.endsWith(".png"))
      return {
        encoding: "base64",
        content:
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF7sAAAAASUVORK5CYII=",
      };
    return {
      encoding: "utf-8",
      content: file.endsWith(".py")
        ? '# 今天吃什么\nfrom random import choice\n\nmeals = ["番茄炒蛋", "牛肉面", "蔬菜沙拉"]\nprint(choice(meals))\n'
        : file.endsWith(".md")
          ? "# 交付计划\n\n先让文件浏览清晰，再让内容阅读舒适。\n\n## 验证清单\n\n- 桌面左右分栏\n- 手机返回文件列表\n- 深浅色与长文件名\n"
          : "随手记\n\n今天整理了研究资料。\n下一步：核对交付清单，安排多端验证。\n",
      next_offset: null,
    };
  }
  if (path.includes("sandbox")) return { machines: [], status: "offline" };
  if (path.includes("health")) return { status: "healthy" };
  return undefined;
}

const token = `preview.${Buffer.from(
  JSON.stringify({ sub: user.id, exp: 4102444800 }),
).toString("base64url")}.fixture`;
const failedDocumentRequests = new Set<string>();
const failedDrawingRequests = new Map<string, number>();
const completedPreviewStreams = new Set<string>();
const failedWelcomeRequests = new Set<string>();
const failedChannelRequests = new Set<string>();
const server = await createServer({
  root: process.cwd(),
  cacheDir: "node_modules/.vite-panel-preview",
  server: {
    host: "127.0.0.1",
    port: Number(process.env.PANEL_PREVIEW_PORT ?? 3002),
    strictPort: true,
    proxy: {},
  },
  plugins: [
    {
      name: "panel-preview-fixtures",
      enforce: "pre",
      config: () => ({ server: { proxy: {} } }),
      configResolved(config) {
        config.server.proxy = {};
      },
      transformIndexHtml(html) {
        return html.replace(
          "<head>",
          `<head><script>const params=new URLSearchParams(location.search);if(params.has("guest")){localStorage.removeItem("access_token");localStorage.removeItem("refresh_token");}else{localStorage.setItem("access_token",${JSON.stringify(
            token,
          )});}localStorage.setItem("lambchat-theme",params.get("theme")||"light");</script>`,
        );
      },
      configureServer(vite) {
        vite.middlewares.use((req, res, next) => {
          const url = new URL(req.url ?? "/", "http://127.0.0.1:3002");
          const previewParams = new URL(
            req.headers.referer ?? "http://localhost",
          ).searchParams;
          if (
            url.pathname === "/preview-document.excalidraw" &&
            previewParams.get("fixture") === "error" &&
            previewParams.get("failure") === "excalidraw"
          ) {
            const key = `${req.headers.referer}:${url.pathname}`;
            const attempts = failedDrawingRequests.get(key) ?? 0;
            if (attempts < 2) {
              failedDrawingRequests.set(key, attempts + 1);
              res.statusCode = 503;
              res.end("Preview drawing temporarily unavailable");
              return;
            }
          }
          if (
            url.pathname.startsWith("/preview-document.") &&
            previewParams.get("fixture") === "error" &&
            previewParams.get("failure") === "document"
          ) {
            const key = `${req.headers.referer}:${url.pathname}`;
            if (!failedDocumentRequests.has(key)) {
              failedDocumentRequests.add(key);
              res.statusCode = 503;
              res.end("Preview document temporarily unavailable");
              return;
            }
          }
          if (url.pathname === "/preview-document.md") {
            res.end(
              '# 项目交付报告\n\n研究结果与后续计划。保持舒适的阅读宽度与清楚的信息层级。\n\n## 验证清单\n\n- 手机工具栏与长文件名\n- 代码与表格横向滚动\n- 深浅色与护眼主题\n\n```mermaid\ngraph LR\n  A[研究] --> B[设计] --> C[验证]\n```\n\n| 项目 | 负责人 | 阶段 | 交付成果 | 验证方法 | 下一步 |\n| --- | --- | --- | --- | --- | --- |\n| 响应式界面 | 产品设计团队 | 验收中 | 跨端界面与交互规范 | 手机、平板、桌面逐页走查 | 核对触屏和键盘焦点 |\n\n```python\nreport = summarize(source="quarterly_business_metrics.csv", columns=["month", "delivery_count", "completion_rate", "owner"])\n```\n',
            );
            return;
          }
          if (url.pathname === "/preview-document.excalidraw") {
            res.setHeader("Content-Type", "application/json");
            res.end(
              JSON.stringify({
                type: "excalidraw",
                version: 2,
                appState: { viewBackgroundColor: "#ffffff" },
                elements: ["研究", "设计", "验证"].flatMap((text, i) => {
                  const common = {
                    x: i * 180,
                    y: 0,
                    width: 140,
                    height: 80,
                    angle: 0,
                    strokeColor: "#1e1e1e",
                    backgroundColor: "#f5f5f4",
                    fillStyle: "solid",
                    strokeWidth: 1,
                    strokeStyle: "solid",
                    roughness: 0,
                    opacity: 100,
                    groupIds: [],
                    frameId: null,
                    roundness: null,
                    seed: i + 1,
                    version: 1,
                    versionNonce: i + 1,
                    isDeleted: false,
                    boundElements: null,
                    updated: 1,
                    link: null,
                    locked: false,
                  };
                  return [
                    { ...common, id: `box-${i}`, type: "rectangle" },
                    {
                      ...common,
                      id: `label-${i}`,
                      type: "text",
                      x: i * 180 + 44,
                      y: 28,
                      width: 52,
                      height: 24,
                      text,
                      originalText: text,
                      fontSize: 20,
                      fontFamily: 2,
                      textAlign: "left",
                      verticalAlign: "top",
                      containerId: null,
                      autoResize: true,
                      lineHeight: 1.2,
                    },
                  ];
                }),
                files: {},
              }),
            );
            return;
          }
          if (url.pathname === "/preview-document.py") {
            res.end(
              'import pandas as pd\n\ndef summarize(data):\n    clean = data.dropna()\n    return clean.groupby("month").sum()\n\nreport = summarize(pd.read_csv("quarterly_business_metrics_with_delivery_counts_and_completion_rates.csv"))\n',
            );
            return;
          }
          if (url.pathname === "/preview-document.csv") {
            res.end(
              "月份,交付数量,完成率,负责人,交付成果,验证方法,下一步\n六月,128,92%,产品设计团队,跨端界面与交互规范,手机平板桌面逐页走查,核对触屏和键盘焦点\n七月,156,96%,前端开发团队,文档阅读和文件预览,长文件名与表格验证,完成深浅色回归\n八月,182,98%,质量验证团队,异常恢复与发布验收,自动化检查和人工复核,整理验证结果\n",
            );
            return;
          }
          if (
            !url.pathname.startsWith("/api/") &&
            !url.pathname.startsWith("/ws")
          )
            return next();
          const scenario = previewParams.get("fixture") ?? "populated";
          const failureTarget = previewParams.get("failure");
          const streamKey = req.headers.referer ?? "";
          const chatState = completedPreviewStreams.has(streamKey)
            ? "completed"
            : (previewParams.get("chat-state") ?? "completed");
          if (
            req.method === "GET" &&
            url.pathname === "/api/chat/sessions/preview-report/stream" &&
            ["working", "streaming"].includes(chatState)
          ) {
            res.setHeader("Content-Type", "text/event-stream");
            res.setHeader("Cache-Control", "no-cache");
            res.flushHeaders();
            const sendEvent = (event: string, data: object, id: string) =>
              res.write(
                `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify({ ...data, run_id: "preview-run", _timestamp: new Date().toISOString() })}\n\n`,
              );
            const ping = setInterval(
              () => sendEvent("ping", {}, "preview-ping"),
              2000,
            );
            const timers: ReturnType<typeof setTimeout>[] = [];
            if (chatState === "streaming") {
              [
                "## 研究发现与交付计划\n\n",
                "已将需求归纳为三个重点：更清晰的工作入口、可追踪的执行过程，以及便于团队复用的成果。",
                "\n\n### 下一步\n\n1. 确认目标用户和首要任务。\n2. 用原型验证关键路径。\n3. 将反馈整理为可执行的迭代清单。",
              ].forEach((content, index) => {
                timers.push(
                  setTimeout(
                    () =>
                      sendEvent(
                        "message:chunk",
                        { content },
                        `preview-stream-${index}`,
                      ),
                    6000 * (index + 1),
                  ),
                );
              });
              timers.push(
                setTimeout(() => {
                  completedPreviewStreams.add(streamKey);
                  sendEvent(
                    "done",
                    { status: "completed" },
                    "preview-stream-done",
                  );
                  res.end();
                }, 24000),
              );
            }
            res.on("close", () => {
              clearInterval(ping);
              timers.forEach(clearTimeout);
            });
            return;
          }
          const data =
            failureTarget === "channel-config" &&
            url.pathname === "/api/channels/feishu"
              ? { channels: [] }
              : failureTarget === "welcome-teams" &&
                  url.pathname === "/api/agents"
                ? { agents, count: agents.length, default_agent: "team" }
                : response(url, scenario, chatState);
          const isRead = req.method === "GET";
          const channelConfigFailure =
            isRead &&
            ((failureTarget === "model-role" &&
              /^\/api\/agent\/config\/roles\/[^/]+\/models$/.test(
                url.pathname,
              )) ||
              (failureTarget === "agent-role" &&
                /^\/api\/agent\/config\/roles\/[^/]+$/.test(url.pathname)) ||
              (failureTarget === "channel-config" &&
                /^\/api\/channels\/[^/]+\/instance-[^/]+$/.test(
                  url.pathname,
                )) ||
              (failureTarget === "channel-list" &&
                /^\/api\/channels\/(feishu|slack|telegram)$/.test(
                  url.pathname,
                )) ||
              (failureTarget === "channel-status" &&
                /^\/api\/channels\/[^/]+\/instance-[^/]+\/status$/.test(
                  url.pathname,
                )));
          const channelConfigKey = `${streamKey}:${url.pathname}`;
          const firstChannelConfigFailure =
            channelConfigFailure &&
            !failedChannelRequests.has(channelConfigKey);
          if (firstChannelConfigFailure)
            failedChannelRequests.add(channelConfigKey);
          const welcomeFailure =
            scenario === "error" &&
            isRead &&
            ((failureTarget === "welcome-personas" &&
              url.pathname.replace(/\/$/, "") === "/api/persona-presets") ||
              (failureTarget === "welcome-teams" &&
                url.pathname.replace(/\/$/, "") === "/api/teams"));
          const welcomeKey = `${streamKey}:${url.pathname}`;
          const firstWelcomeFailure =
            welcomeFailure && !failedWelcomeRequests.has(welcomeKey);
          if (firstWelcomeFailure) failedWelcomeRequests.add(welcomeKey);
          const fault =
            firstWelcomeFailure ||
            firstChannelConfigFailure ||
            (scenario === "error" &&
              (!failureTarget ||
                url.pathname.replace(/\/$/, "") === `/api/${failureTarget}`) &&
              !/auth|settings|agent\/models/.test(url.pathname));
          res.statusCode = !isRead
            ? 405
            : fault
              ? 503
              : data === undefined
                ? 404
                : 200;
          res.setHeader("Content-Type", "application/json");
          res.setHeader("Cache-Control", "no-store");
          const send = () =>
            res.end(
              JSON.stringify(
                res.statusCode === 200
                  ? data
                  : {
                      detail: {
                        code: "preview_only",
                        message: !isRead
                          ? failureTarget === "editor-long-error"
                            ? `Preview is read-only. ${"The configuration could not be saved; your draft is still available. ".repeat(12)}https://preview.example.test/${"configuration".repeat(20)}`
                            : "Preview is read-only"
                          : "Preview fixture unavailable",
                      },
                    },
              ),
            );
          if (scenario === "loading" && !url.pathname.startsWith("/api/auth/"))
            setTimeout(send, 8000);
          else send();
          if (data === undefined && isRead)
            console.log("Missing fixture:", url.pathname);
        });
      },
    },
  ],
});
await server.listen();
console.log(
  "Panel preview: http://127.0.0.1:3002/mcp (65 items; ?fixture=empty|error|loading)",
);
