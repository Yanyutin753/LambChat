import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "../../../../../../..");

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

function readRepoSource(relativePath: string): string {
  return readFileSync(resolve(repoRoot, relativePath), "utf8");
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
    assert.match(source, new RegExp(`part\\.name\\s*===\\s*"${toolName}"`));
  }

  assert.match(source, /<UploadUrlToSandboxItem/);
  assert.match(source, /<ImageAnalyzeItem/);
  assert.match(source, /<TransferItem/);
});

test("message part renderer covers every backend internal tool", () => {
  const source = readSource("../../MessagePartRenderer.tsx");
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
    "src/infra/tool/team_tool.py",
    "src/infra/tool/image_generation_tool.py",
    "src/infra/tool/scheduled_task/read.py",
    "src/infra/tool/scheduled_task/delete.py",
    "src/infra/tool/scheduled_task/update.py",
    "src/infra/tool/scheduled_task/create.py",
    "src/infra/memory/tools.py",
  ];
  const internalToolNames = backendToolFiles.flatMap(extractToolFunctionNames);

  assert.equal(internalToolNames.length, 32);

  for (const toolName of internalToolNames) {
    assert.match(
      source,
      new RegExp(`part\\.name\\s*===\\s*"${toolName}"`),
      `${toolName} should route to a dedicated message item`,
    );
  }
});

test("upload URL to sandbox item presents URL and destination path details", () => {
  const source = readSource("../UploadUrlToSandboxItem.tsx");

  assert.match(source, /toolUploadUrlToSandbox/);
  assert.match(source, /args\.url/);
  assert.match(source, /args\.file_path/);
  assert.match(source, /Download size=\{12\}/);
  assert.match(source, /ToolResultContent/);
});

test("image analyze item presents prompt, images, and analysis output", () => {
  const source = readSource("../ImageAnalyzeItem.tsx");

  assert.match(source, /toolImageAnalyze/);
  assert.match(source, /args\.image_urls/);
  assert.match(source, /args\.prompt/);
  assert.match(source, /DeferredCodeMirrorViewer/);
  assert.match(source, /ScanSearch size=\{12\}/);
});

test("transfer item presents file and path transfer arguments", () => {
  const source = readSource("../TransferItem.tsx");

  assert.match(source, /toolTransferFile/);
  assert.match(source, /toolTransferPath/);
  assert.match(source, /args\.source_path/);
  assert.match(source, /args\.target_path/);
  assert.match(source, /args\.source_dir/);
  assert.match(source, /args\.target_prefix/);
});
