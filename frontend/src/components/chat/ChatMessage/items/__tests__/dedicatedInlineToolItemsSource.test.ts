import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "../../../../../../..");

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

function readRepoSource(relativePath: string): string {
  return readFileSync(resolve(repoRoot, relativePath), "utf8");
}

function readToolRendererSources(): string {
  return [
    "frontend/src/extensions/coreContributions.ts",
    "plugins/preinstalled/audio_transcription/frontend/plugin.json",
    "plugins/preinstalled/image_generation/frontend/plugin.json",
    "plugins/system/agent_team/frontend/plugin.json",
  ]
    .map(readRepoSource)
    .join("\n");
}

function extractToolFunctionNames(relativePath: string): string[] {
  const source = readRepoSource(relativePath);
  const names = Array.from(
    source.matchAll(
      /@tool(?:\([^)]*\))?\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)/g,
    ),
    (match) => match[1],
  );

  return names;
}

test("message part renderer routes internal inline tools to dedicated items", () => {
  const source = readSource("../../MessagePartRenderer.tsx");
  const toolRendererSources = readToolRendererSources();

  const expectedRoutes = [
    "upload_url_to_sandbox",
    "image_analyze",
    "image_edit_with_references",
    "transfer_file",
    "transfer_path",
    "env_var_delete_all",
    "create_persona_preset",
    "update_persona_preset",
  ];

  for (const toolName of expectedRoutes) {
    expect(toolRendererSources).toMatch(new RegExp(`"${toolName}"`));
  }

  expect(source).toMatch(/coreToolRendererId === "upload-url-to-sandbox"/);
  expect(source).toMatch(/coreToolRendererId === "image-analyze"/);
  expect(source).toMatch(/coreToolRendererId === "transfer"/);
  expect(source).toMatch(/<UploadUrlToSandboxItem/);
  expect(source).toMatch(/<ImageAnalyzeItem/);
  expect(source).toMatch(/<TransferItem/);
});

test("message part renderer covers every backend internal tool", () => {
  const toolRendererSources = readToolRendererSources();
  const backendToolFiles = [
    "src/infra/tool/upload_url_tool.py",
    "src/infra/tool/reveal_file_tool.py",
    "src/infra/tool/image_analysis_tool.py",
    "src/infra/tool/audio_transcribe_tool.py",
    "src/infra/tool/env_var_tool.py",
    "src/infra/tool/persona_preset_tool.py",
    "src/infra/tool/reveal_project_tool.py",
    "src/infra/tool/transfer_file_tool.py",
    "src/infra/tool/sandbox_mcp_tool.py",
    "plugins/system/agent_team/backend/tools.py",
    "src/infra/tool/image_generation_tool.py",
    "src/infra/tool/scheduled_task/read.py",
    "src/infra/tool/scheduled_task/delete.py",
    "src/infra/tool/scheduled_task/update.py",
    "src/infra/tool/scheduled_task/create.py",
    "src/infra/memory/tools.py",
  ];
  const internalToolNames = backendToolFiles.flatMap(extractToolFunctionNames);

  expect(internalToolNames.length).toBe(32);

  for (const toolName of internalToolNames) {
    expect(toolRendererSources).toMatch(new RegExp(`"${toolName}"`));
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
  expect(source).toMatch(/DeferredCodeMirrorViewer/);
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
