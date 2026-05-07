import test from "node:test";
import assert from "node:assert/strict";
import { buildFileCardPreview, getSessionNavigationTarget } from "../utils.ts";
import type { RevealedFileItem } from "../../../services/api";

function createFile(
  overrides: Partial<RevealedFileItem> = {},
): RevealedFileItem {
  return {
    id: overrides.id ?? "file-1",
    file_key: overrides.file_key ?? "revealed/file-1",
    file_name: overrides.file_name ?? "demo.txt",
    file_type: overrides.file_type ?? "document",
    mime_type: overrides.mime_type ?? "text/plain",
    file_size: overrides.file_size ?? 12,
    url: overrides.url ?? null,
    session_id: overrides.session_id ?? "session-1",
    session_name: overrides.session_name ?? "Session 1",
    trace_id: overrides.trace_id ?? "trace-1",
    project_id: overrides.project_id ?? null,
    user_id: overrides.user_id ?? "user-1",
    source: overrides.source ?? "reveal_file",
    description: overrides.description ?? null,
    original_path: overrides.original_path ?? "/tmp/demo.txt",
    created_at: overrides.created_at ?? "2026-04-25T00:00:00.000Z",
    is_favorite: overrides.is_favorite ?? false,
    card_preview: overrides.card_preview,
    project_meta: overrides.project_meta,
  };
}

test("uses the first file in the session group as the navigation target", () => {
  const files = [
    createFile({ id: "latest", file_name: "latest.txt" }),
    createFile({ id: "older", file_name: "older.txt" }),
  ];

  assert.equal(getSessionNavigationTarget(files)?.id, "latest");
});

test("returns null when a session group has no files", () => {
  assert.equal(getSessionNavigationTarget([]), null);
});

test("builds a markdown card preview from existing revealed file metadata", () => {
  const preview = buildFileCardPreview(
    createFile({
      file_name: "mermaid-sdlc.md",
      mime_type: "text/markdown",
      description: "生成一个好看的mermaid",
    }),
  );

  assert.equal(preview.kind, "markdown");
  assert.equal(preview.badge, "MD");
  assert.equal(preview.title, "mermaid-sdlc");
  assert.equal(preview.subtitle, "生成一个好看的mermaid");
  assert.deepEqual(preview.lines.slice(0, 2), [
    "# mermaid-sdlc",
    "生成一个好看的mermaid",
  ]);
});

test("builds a project card preview without fetching project files", () => {
  const preview = buildFileCardPreview(
    createFile({
      file_name: "demo-app",
      file_type: "project",
      source: "reveal_project",
      project_meta: {
        template: "react",
        entry: "/src/main.tsx",
        file_count: 12,
        files: {
          "/src/main.tsx": { url: "/file/main", size: 10 },
        },
      },
    }),
  );

  assert.equal(preview.kind, "project");
  assert.equal(preview.badge, "REACT");
  assert.equal(preview.subtitle, "12 files");
  assert.deepEqual(preview.lines, ["Entry /src/main.tsx", "12 files indexed"]);
});
