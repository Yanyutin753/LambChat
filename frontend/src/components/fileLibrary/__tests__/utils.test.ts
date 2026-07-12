import { readFileSync } from "node:fs";
import {
  buildFileCardPreview,
  getImagePreviewNavigation,
  getPreviewableImageFiles,
  getSessionNavigationTarget,
} from "../utils.ts";
import type { RevealedFileItem } from "../../../services/api";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

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

  expect(getSessionNavigationTarget(files)?.id).toBe("latest");
});

test("returns null when a session group has no files", () => {
  expect(getSessionNavigationTarget([])).toBe(null);
});

test("collects previewable images from visible session groups in render order", () => {
  const first = createFile({
    id: "first",
    file_name: "first.png",
    file_type: "image",
    url: "/files/first.png",
  });
  const second = createFile({
    id: "second",
    file_name: "second.webp",
    file_type: "document",
    url: "/files/second.webp",
  });
  const missingUrl = createFile({
    id: "missing-url",
    file_name: "missing.png",
    file_type: "image",
    url: null,
  });
  const document = createFile({
    id: "document",
    file_name: "notes.pdf",
    file_type: "document",
    url: "/files/notes.pdf",
  });

  const files = getPreviewableImageFiles([
    { files: [first, missingUrl] },
    { files: [document, second] },
  ]);

  expect(files.map((file) => file.id)).toEqual(["first", "second"]);
});

test("resolves previous and next image preview files with boundary states", () => {
  const files = [
    createFile({ id: "first", file_name: "first.png" }),
    createFile({ id: "second", file_name: "second.png" }),
    createFile({ id: "third", file_name: "third.png" }),
  ];

  expect(getImagePreviewNavigation(files, "first")).toEqual({
    current: files[0],
    previous: null,
    next: files[1],
    index: 0,
    total: 3,
  });
  expect(getImagePreviewNavigation(files, "second")).toEqual({
    current: files[1],
    previous: files[0],
    next: files[2],
    index: 1,
    total: 3,
  });
  expect(getImagePreviewNavigation(files, "third")).toEqual({
    current: files[2],
    previous: files[1],
    next: null,
    index: 2,
    total: 3,
  });
});

test("builds a markdown card preview from existing revealed file metadata", () => {
  const preview = buildFileCardPreview(
    createFile({
      file_name: "mermaid-sdlc.md",
      mime_type: "text/markdown",
      description: "生成一个好看的mermaid",
    }),
  );

  expect(preview.kind).toBe("markdown");
  expect(preview.badge).toBe("Markdown");
  expect(preview.title).toBe("mermaid-sdlc");
  expect(preview.subtitle).toBe("生成一个好看的mermaid");
  expect(preview.lines.slice(0, 2)).toEqual([
    "mermaid-sdlc",
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

  expect(preview.kind).toBe("project");
  expect(preview.badge).toBe("REACT");
  expect(preview.subtitle).toBe("12 files");
  expect(preview.lines).toEqual([
    "▸ Entry /src/main.tsx",
    "· 12 files indexed",
  ]);
});

test("file library document previews fill the mobile viewport like chat previews", () => {
  const source = readSource("../RevealedFilesPanel.tsx");

  expect(source).toMatch(
    /<DocumentPreview[\s\S]*?\bmobileFillViewport\b[\s\S]*?\/>/,
  );
});

test("file library image previews wire gallery navigation into ImageViewer", () => {
  const source = readSource("../RevealedFilesPanel.tsx");

  expect(source).toMatch(/getPreviewableImageFiles/);
  expect(source).toMatch(/getImagePreviewNavigation/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bonPrevious=/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bonNext=/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bhasPrevious=/);
  expect(source).toMatch(/<ImageViewer[\s\S]*?\bhasNext=/);
});

test("ImageViewer exposes previous and next controls with keyboard shortcuts", () => {
  const source = readSource("../../common/ImageViewer.tsx");

  expect(source).toMatch(/onPrevious\?:/);
  expect(source).toMatch(/onNext\?:/);
  expect(source).toMatch(/hasPrevious\?:/);
  expect(source).toMatch(/hasNext\?:/);
  expect(source).toMatch(/ArrowLeft/);
  expect(source).toMatch(/ArrowRight/);
  expect(source).toMatch(/ChevronLeft/);
  expect(source).toMatch(/ChevronRight/);
});

test("ImageViewer shows a loading affordance while switched images load", () => {
  const source = readSource("../../common/ImageViewer.tsx");

  expect(source).toMatch(/isImageLoading/);
  expect(source).toMatch(/setIsImageLoading\(true\)/);
  expect(source).toMatch(/onLoad=\{\(\) => setIsImageLoading\(false\)\}/);
  expect(source).toMatch(/onError=\{\(\) => setIsImageLoading\(false\)\}/);
  expect(source).toMatch(/skeleton-line/);
  expect(source).toMatch(/opacity: isImageLoading \? 0\.45 : 1/);
});
