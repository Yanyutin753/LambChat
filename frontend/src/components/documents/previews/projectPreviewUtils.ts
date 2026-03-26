export type SandpackTemplate =
  | "react"
  | "vue"
  | "vanilla"
  | "angular"
  | "svelte"
  | "solid"
  | "node"
  | "nextjs"
  | "static";

const TEMPLATE_MAP: Record<string, SandpackTemplate> = {
  react: "react",
  vue: "vue",
  vanilla: "vanilla",
  angular: "angular",
  svelte: "svelte",
  solid: "solid",
  nextjs: "nextjs",
  static: "static",
};

const ENTRY_CANDIDATES = [
  "/pages/index.tsx",
  "/pages/index.jsx",
  "/pages/_app.tsx",
  "/pages/_app.jsx",
  "/index.html",
  "/src/index.html",
  "/public/index.html",
  "/src/main.ts",
  "/src/index.ts",
  "/src/index.tsx",
  "/src/index.jsx",
  "/src/main.tsx",
  "/src/main.jsx",
  "/src/main.js",
  "/main.ts",
  "/index.ts",
  "/index.tsx",
  "/index.jsx",
  "/index.js",
  "/main.tsx",
  "/main.jsx",
  "/main.js",
  "/src/main.vue",
  "/src/App.svelte",
  "/App.tsx",
  "/App.jsx",
] as const;

function hasAnyFile(
  files: Record<string, string>,
  candidates: readonly string[],
): boolean {
  return candidates.some((path) => path in files);
}

function hasReactEntrypoint(files: Record<string, string>): boolean {
  return hasAnyFile(files, [
    "/src/main.jsx",
    "/src/main.tsx",
    "/src/index.jsx",
    "/src/index.tsx",
    "/main.jsx",
    "/main.tsx",
    "/index.jsx",
    "/index.tsx",
    "/App.jsx",
    "/App.tsx",
  ]);
}

function hasVueEntrypoint(files: Record<string, string>): boolean {
  return hasAnyFile(files, ["/src/main.vue", "/src/App.vue", "/App.vue"]);
}

function hasSvelteEntrypoint(files: Record<string, string>): boolean {
  return hasAnyFile(files, [
    "/src/App.svelte",
    "/App.svelte",
    "/src/main.svelte",
    "/main.svelte",
  ]);
}

function hasNextJsEntrypoint(files: Record<string, string>): boolean {
  return hasAnyFile(files, [
    "/pages/index.tsx",
    "/pages/index.jsx",
    "/pages/_app.tsx",
    "/pages/_app.jsx",
  ]);
}

function hasAngularEntrypoint(files: Record<string, string>): boolean {
  return (
    "/angular.json" in files &&
    hasAnyFile(files, ["/src/main.ts", "/src/main.js", "/main.ts", "/main.js"])
  );
}

function hasSolidEntrypoint(files: Record<string, string>): boolean {
  return Object.values(files).some(
    (content) =>
      content.includes("solid-js") ||
      content.includes("solid-app-router") ||
      content.includes("from 'solid-js/web'") ||
      content.includes('from "solid-js/web"'),
  );
}

export function resolveSandpackTemplate(
  template: string,
  files: Record<string, string>,
): SandpackTemplate {
  if (template === "static") {
    return "static";
  }

  if (template === "angular") {
    return "angular";
  }

  if (template === "svelte") {
    return "svelte";
  }

  if (template === "solid") {
    return "solid";
  }

  if (template === "nextjs") {
    return "nextjs";
  }

  if (hasNextJsEntrypoint(files)) {
    return "nextjs";
  }

  if (hasAngularEntrypoint(files)) {
    return "angular";
  }

  if (hasSvelteEntrypoint(files)) {
    return "svelte";
  }

  if (hasSolidEntrypoint(files)) {
    return "solid";
  }

  if (hasReactEntrypoint(files)) {
    return "react";
  }

  if (hasVueEntrypoint(files)) {
    return "vue";
  }

  if ("/index.html" in files) {
    return "static";
  }

  return TEMPLATE_MAP[template] || "vanilla";
}

export function resolveEntryFile(
  files: Record<string, string>,
  entry?: string,
): string {
  if (entry) {
    return entry.startsWith("/") ? entry : `/${entry}`;
  }

  const matched = ENTRY_CANDIDATES.find((path) => path in files);
  return matched || Object.keys(files)[0] || "/index.js";
}

/** normalizePaths: 确保所有文件路径以 / 开头 */
function normalizePaths(
  files: Record<string, string>,
): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [path, content] of Object.entries(files)) {
    result[path.startsWith("/") ? path : `/${path}`] = content;
  }
  return result;
}

export interface SandpackConfig {
  /** 传给 SandpackProvider 的 template（static 模板时为 undefined） */
  template?: SandpackTemplate;
  /** 传给 SandpackProvider 的 customSetup（仅 static 模板使用） */
  customSetup?: { entry: string; environment: "static" };
  /** 规范化后的用户文件 */
  files: Record<string, string>;
  /** 入口文件路径 */
  entryFile: string;
  /** 文件浏览器可见的文件列表 */
  visibleFiles: string[];
}

/**
 * 构建完整的 Sandpack 配置
 *
 * 核心设计：
 * - static 模板：不使用 Sandpack 内置模板，改用 customSetup 避免模板默认文件
 *   （Hello world、/styles.css、/package.json）通过 Object.assign 污染用户项目
 * - 框架模板（react/vue 等）：正常使用内置模板以获取依赖和构建配置
 */
export function buildSandpackConfig(
  template: string,
  files: Record<string, string>,
  entry?: string,
): SandpackConfig {
  const normalized = normalizePaths(files);
  const detected = resolveSandpackTemplate(template, normalized);
  const entryFile = resolveEntryFile(normalized, entry);
  const visibleFiles = Object.keys(normalized);

  if (detected === "static") {
    return {
      customSetup: { entry: entryFile, environment: "static" },
      files: normalized,
      entryFile,
      visibleFiles,
    };
  }

  return {
    template: detected,
    files: normalized,
    entryFile,
    visibleFiles,
  };
}
