import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "../../../../../../..");

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

// 内置系统工具的扫描根：新增工具目录时在此登记。
const INTERNAL_TOOL_SCAN_ROOTS = [
  "src/infra/tool",
  "src/infra/memory/tools.py",
  "src/infra/skill/skill_search_tool.py",
];

function listPythonFiles(rootDir: string): string[] {
  if (statSync(rootDir).isFile()) return [rootDir];
  return readdirSync(rootDir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === "__pycache__") return [];
    const child = resolve(rootDir, entry.name);
    if (entry.isDirectory()) return listPythonFiles(child);
    return entry.name.endsWith(".py") ? [child] : [];
  });
}

/**
 * 规矩：后端每写一个内置系统工具，前端必须有对应的专属 Item 路由。
 * 自动扫描扫描根下的全部 Python 文件，提取 @tool 函数名与
 * BaseTool 子类的 name 字段，禁止再靠手工维护文件清单。
 */
function discoverInternalToolNames(): string[] {
  const files = INTERNAL_TOOL_SCAN_ROOTS.flatMap((root) =>
    listPythonFiles(resolve(repoRoot, root)),
  );
  const names = new Set<string>();
  for (const file of files) {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(
      /@tool(?:\([^)]*\))?\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)/g,
    )) {
      names.add(match[1]);
    }
    for (const match of source.matchAll(
      /^\s+name:\s*str\s*=\s*"([a-z0-9_]+)"/gm,
    )) {
      names.add(match[1]);
    }
  }
  return [...names].sort();
}

test("message part renderer routes internal inline tools to dedicated items", () => {
  const source = readSource("../../MessagePartRenderer.tsx");

  const expectedRoutes = [
    "upload_url_to_sandbox",
    "image_analyze",
    "image_edit_with_references",
    "transfer_file",
    "transfer_path",
    "env_var_delete_all",
    "create_persona_preset",
    "update_persona_preset",
    "search_conversation_history",
    "get_conversation_detail",
    "search_skills",
  ];

  for (const toolName of expectedRoutes) {
    expect(source).toMatch(new RegExp(`part\\.name\\s*===\\s*"${toolName}"`));
  }

  expect(source).toMatch(/<UploadUrlToSandboxItem/);
  expect(source).toMatch(/<ImageAnalyzeItem/);
  expect(source).toMatch(/<TransferItem/);
  expect(source).toMatch(/<ConversationHistoryItem/);
  expect(source).toMatch(/<SkillSearchItem/);
});

test("every backend internal tool ships a dedicated item route", () => {
  const source = readSource("../../MessagePartRenderer.tsx");
  const internalToolNames = discoverInternalToolNames();

  // 基线清单：扫描结果与清单不一致（新增/删除工具）时在此失败，
  // 提醒同步维护前端专属 Item 与本清单，防止静默落入通用 Wrench 兜底。
  expect(internalToolNames).toEqual([
    "ask_human",
    "audio_transcribe",
    "create_agent_team",
    "create_persona_preset",
    "env_var_delete",
    "env_var_delete_all",
    "env_var_list",
    "env_var_set",
    "get_conversation_detail",
    "image_analyze",
    "image_edit_with_references",
    "image_generate",
    "memory_delete",
    "memory_recall",
    "memory_retain",
    "reveal_file",
    "reveal_project",
    "save_persona_preset",
    "scheduled_task_create",
    "scheduled_task_delete",
    "scheduled_task_get",
    "scheduled_task_list",
    "scheduled_task_pause",
    "scheduled_task_resume",
    "scheduled_task_run",
    "scheduled_task_update",
    "search_conversation_history",
    "search_persona_presets",
    "search_skills",
    "search_tools",
    "transfer_file",
    "transfer_path",
    "update_persona_preset",
    "upload_url_to_sandbox",
  ]);

  for (const toolName of internalToolNames) {
    expect(source).toMatch(new RegExp(`part\\.name\\s*===\\s*"${toolName}"`));
  }
});

test("upload URL to sandbox item presents URL and destination path details", () => {
  const source = readSource("../UploadUrlToSandboxItem.tsx");

  expect(source).toMatch(/toolUploadUrlToSandbox/);
  expect(source).toMatch(/args\.url/);
  expect(source).toMatch(/args\.file_path/);
  expect(source).toMatch(/Download size=\{12\}/);
  expect(source).toMatch(/ToolResultContent/);
});

test("image analyze item presents prompt, images, and analysis output", () => {
  const source = readSource("../ImageAnalyzeItem.tsx");

  expect(source).toMatch(/toolImageAnalyze/);
  expect(source).toMatch(/args\.image_urls/);
  expect(source).toMatch(/args\.prompt/);
  expect(source).toMatch(/MarkdownContent/);
  expect(source).toMatch(/ScanSearch size=\{12\}/);
});

test("transfer item presents file and path transfer arguments", () => {
  const source = readSource("../TransferItem.tsx");

  expect(source).toMatch(/toolTransferFile/);
  expect(source).toMatch(/toolTransferPath/);
  expect(source).toMatch(/args\.source_path/);
  expect(source).toMatch(/args\.target_path/);
  expect(source).toMatch(/args\.source_dir/);
  expect(source).toMatch(/args\.target_prefix/);
});

test("conversation history item covers both SOP tools with a dedicated icon", () => {
  const source = readSource("../ConversationHistoryItem.tsx");

  expect(source).toMatch(/toolName === "search_conversation_history"/);
  expect(source).toMatch(/toolName === "get_conversation_detail"/);
  expect(source).toMatch(/args\.query/);
  expect(source).toMatch(/args\.session_id/);
  expect(source).toMatch(/History size=\{12\}/);
  expect(source).toMatch(/JSON\.parse/);
  expect(source).toMatch(/ToolInlineDetails/);
});

test("conversation history item uses domain-specific overflow wording", () => {
  const source = readSource("../ConversationHistoryItem.tsx");

  // 会话/轮次列表的溢出提示不得复用文件语义的 toolMoreFiles
  expect(source).toMatch(/toolHistoryMoreSessions/);
  expect(source).toMatch(/toolHistoryMoreTurns/);
  expect(source).not.toMatch(/toolMoreFiles/);
});

test("skill search item presents query and matched skill metadata", () => {
  const source = readSource("../SkillSearchItem.tsx");

  expect(source).toMatch(/args\.query/);
  expect(source).toMatch(/Sparkles size=\{12\}/);
  expect(source).toMatch(/\/skills\//);
  expect(source).toMatch(/ToolInlineDetails/);
});

test("skill search item uses skill-specific overflow wording", () => {
  const source = readSource("../SkillSearchItem.tsx");

  // 技能匹配的溢出提示不得复用文件语义的 toolMoreFiles
  expect(source).toMatch(/toolSkillMore/);
  expect(source).not.toMatch(/toolMoreFiles/);
});

test("overflow wording keys exist in every locale", () => {
  const requiredKeys = [
    "chat.message.toolHistoryMoreSessions",
    "chat.message.toolHistoryMoreTurns",
    "chat.message.toolSkillMore",
  ];
  const locales = ["en", "zh", "ja", "ko", "ru"];

  for (const locale of locales) {
    const localeJson = JSON.parse(
      readFileSync(resolve(repoRoot, `frontend/src/i18n/locales/${locale}.json`), "utf8"),
    );
    const chatMessage = localeJson.chat.message;
    for (const key of requiredKeys) {
      const shortKey = key.split(".").pop() as string;
      expect(chatMessage[shortKey], `${locale}.json ${key}`).toBeTruthy();
      expect(chatMessage[`${shortKey}_other`], `${locale}.json ${key}_other`).toBeTruthy();
    }
  }
});
