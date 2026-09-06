import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import type { RevealedFileItem } from "../../../services/api";
import { RevealedFileCard } from "../RevealedFileCard";

/* ═══════════════════════════════════════════════════════
   Dev-only gallery (/dev/covers) — renders the real
   RevealedFileCard with fixture files covering every cover
   kind. Never bundled into production builds.
   ═══════════════════════════════════════════════════════ */

const OSS_BASE = "http://127.0.0.1:8002/api/upload/file/demo/covers";

function file(
  overrides: Partial<RevealedFileItem> & { file_name: string },
): RevealedFileItem {
  return {
    id: overrides.file_name,
    file_key: `demo/${overrides.file_name}`,
    file_type: "other",
    mime_type: null,
    file_size: 1024 * 64,
    url: null,
    session_id: "demo-session",
    session_name: "Cover Gallery",
    trace_id: "demo-trace",
    project_id: null,
    user_id: "demo-user",
    source: "reveal_file",
    description: null,
    original_path: null,
    created_at: "2026-08-28T00:00:00.000Z",
    is_favorite: false,
    card_preview: null,
    project_meta: null,
    ...overrides,
  };
}

const DEMO_FILES: RevealedFileItem[] = [
  file({
    file_name: "hero-render.jpg",
    file_type: "image",
    mime_type: "image/jpeg",
    url: `${OSS_BASE}/hero.jpg`,
  }),
  file({
    file_name: "product-demo.mp4",
    file_type: "video",
    mime_type: "video/mp4",
    url: `${OSS_BASE}/clip.mp4`,
  }),
  file({
    file_name: "架构设计文档.pdf",
    file_type: "document",
    mime_type: "application/pdf",
    description: "LambChat v3 分层架构与演进路线",
    url: `${OSS_BASE}/architecture.pdf`,
  }),
  file({
    file_name: "api-client.ts",
    file_type: "code",
    mime_type: "text/typescript",
    description: "带重试的 OpenAPI 客户端",
  }),
  file({
    file_name: "data_pipeline.py",
    file_type: "code",
    mime_type: "text/x-python",
    description: "夜间增量索引任务",
  }),
  file({
    file_name: "2026产品规划.md",
    file_type: "document",
    mime_type: "text/markdown",
    description: "从工具到平台的三个里程碑",
  }),
  file({
    file_name: "用户增长数据.csv",
    file_type: "document",
    mime_type: "text/csv",
    description: "近 30 日注册与留存",
  }),
  file({
    file_name: "deploy-config.json",
    file_type: "document",
    mime_type: "application/json",
  }),
  file({
    file_name: "marketing-site",
    file_type: "project",
    source: "reveal_project",
    project_meta: {
      template: "react",
      entry: "/src/main.tsx",
      file_count: 14,
      files: { "/src/main.tsx": { url: "/f/main", size: 10 } },
    },
  }),
  file({
    file_name: "品牌视觉规范.zip",
    file_type: "other",
    mime_type: "application/zip",
  }),
  file({
    file_name: "季度财务报表.xlsx",
    file_type: "document",
    mime_type:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    url: `${OSS_BASE}/report.xlsx`,
  }),
  file({
    file_name: "load-test.rs",
    file_type: "code",
    mime_type: "text/rust",
    description: "网关压测脚本",
  }),
];

function noop() {}

export function CoverGalleryDemo() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
  };

  return (
    <div className="min-h-screen bg-theme-bg p-6 md:p-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-theme-text">
              Studio Covers · 16:9
            </h1>
            <p className="mt-1 text-xs text-theme-text-tertiary">
              dev-only gallery — 真实 RevealedFileCard，覆盖全部封面类型
            </p>
          </div>
          <button
            onClick={toggleTheme}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-theme-border text-theme-text-secondary transition-colors hover:bg-theme-bg-subtle"
          >
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {DEMO_FILES.map((f) => (
            <RevealedFileCard
              key={f.id}
              file={f}
              onPreview={noop}
              onGoToSession={noop}
              onToggleFavorite={noop}
            />
          ))}
        </div>

        <h2 className="mb-3 mt-10 text-sm font-semibold text-theme-text">
          List view · compact tiles
        </h2>
        <div className="space-y-2">
          {DEMO_FILES.slice(0, 6).map((f) => (
            <RevealedFileCard
              key={`list-${f.id}`}
              file={f}
              onPreview={noop}
              onGoToSession={noop}
              onToggleFavorite={noop}
              viewMode="list"
            />
          ))}
        </div>
      </div>
    </div>
  );
}
