import { VFILE_SHIMS } from "./vfileShims";

export type SandpackTemplate =
  | "react"
  | "vue"
  | "vue-ts"
  | "vite-vue"
  | "vite-vue-ts"
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
  "vue-ts": "vue-ts",
  "vite-vue": "vite-vue",
  "vite-vue-ts": "vite-vue-ts",
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
  "/index.html",
  "/src/index.html",
  "/public/index.html",
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

function hasVueTsSignals(files: Record<string, string>): boolean {
  if (
    hasAnyFile(files, [
      "/src/main.ts",
      "/main.ts",
      "/tsconfig.json",
      "/src/shims-vue.d.ts",
      "/shims-vue.d.ts",
    ])
  ) {
    return true;
  }

  return Object.entries(files).some(
    ([path, content]) =>
      path.endsWith(".vue") &&
      (content.includes('lang="ts"') || content.includes("lang='ts'")),
  );
}

function hasViteConfig(files: Record<string, string>): boolean {
  return hasAnyFile(files, [
    "/vite.config.js",
    "/vite.config.ts",
    "/vite.config.mjs",
    "/vite.config.mts",
    "/vite.config.cjs",
    "/vite.config.cts",
  ]);
}

function isViteVueProject(files: Record<string, string>): boolean {
  if (!("/index.html" in files) || !hasVueEntrypoint(files)) {
    return false;
  }

  return (
    hasViteConfig(files) ||
    "/src/main.js" in files ||
    "/src/main.ts" in files ||
    "/main.js" in files ||
    "/main.ts" in files
  );
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

  if (template === "vue-ts") {
    return "vue-ts";
  }

  if (template === "vite-vue") {
    return "vue";
  }

  if (template === "vite-vue-ts") {
    return "vue-ts";
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

  if (isViteVueProject(files)) {
    return hasVueTsSignals(files) ? "vue-ts" : "vue";
  }

  if (hasVueTsSignals(files)) {
    return "vue-ts";
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
function normalizePaths(files: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [path, content] of Object.entries(files)) {
    result[path.startsWith("/") ? path : `/${path}`] = content;
  }
  return result;
}

type PackageJsonLike = {
  scripts?: Record<string, string>;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  overrides?: Record<string, string>;
  [key: string]: unknown;
};

const VUE_PACKAGE_PATCHES: Partial<Record<SandpackTemplate, PackageJsonLike>> =
  {
    vue: {
      scripts: {
        serve: "vue-cli-service serve",
        build: "vue-cli-service build",
      },
      dependencies: {
        "core-js": "^3.26.1",
        vue: "^3.2.45",
      },
      devDependencies: {
        "@vue/cli-plugin-babel": "^5.0.8",
        "@vue/cli-service": "^5.0.8",
      },
    },
    "vue-ts": {
      scripts: {
        serve: "vue-cli-service serve",
        build: "vue-cli-service build",
      },
      dependencies: {
        "core-js": "^3.26.1",
        vue: "^3.2.47",
      },
      devDependencies: {
        "@vue/cli-plugin-babel": "^5.0.8",
        "@vue/cli-plugin-typescript": "^5.0.8",
        "@vue/cli-service": "^5.0.8",
        typescript: "^4.9.5",
      },
    },
  };

function mergePackageJsonForTemplate(
  template: SandpackTemplate,
  files: Record<string, string>,
): Record<string, string> {
  const patch = VUE_PACKAGE_PATCHES[template];
  const packageJson = files["/package.json"];

  if (!patch || !packageJson) {
    return files;
  }

  try {
    const parsed = JSON.parse(packageJson) as PackageJsonLike;
    const merged: PackageJsonLike = {
      ...patch,
      ...parsed,
      scripts: {
        ...patch.scripts,
        ...parsed.scripts,
      },
      dependencies: {
        ...patch.dependencies,
        ...parsed.dependencies,
      },
      devDependencies: {
        ...patch.devDependencies,
        ...parsed.devDependencies,
      },
      overrides: {
        ...patch.overrides,
        ...parsed.overrides,
      },
    };

    if (merged.overrides && Object.keys(merged.overrides).length === 0) {
      delete merged.overrides;
    }

    return {
      ...files,
      "/package.json": JSON.stringify(merged, null, 2),
    };
  } catch {
    return files;
  }
}

export interface SandpackConfig {
  /** 传给 SandpackProvider 的 template（static 模板时为 undefined） */
  template?: SandpackTemplate;
  /** 传给 SandpackProvider 的 customSetup（static 模板或框架模板需要覆盖入口时使用） */
  customSetup?: {
    entry?: string;
    environment?: "static" | "node" | "parcel";
  };
  /** 规范化后的用户文件 */
  files: Record<string, string>;
  /** 入口文件路径 */
  entryFile: string;
  /** 文件浏览器可见的文件列表 */
  visibleFiles: string[];
}

function shouldUseTemplateEntrypoint(
  detected: SandpackTemplate,
  entryFile: string,
  files: Record<string, string>,
): boolean {
  return (
    (detected === "vue" || detected === "vue-ts") &&
    (entryFile === "/src/App.vue" || entryFile === "/App.vue") &&
    !("/src/main.js" in files) &&
    !("/src/main.ts" in files) &&
    !("/main.js" in files) &&
    !("/main.ts" in files)
  );
}

function ensureVueIndexHtml(
  files: Record<string, string>,
): Record<string, string> {
  const indexHtml = files["/index.html"];
  if (!indexHtml) return files;

  // 检查是否已有 id="app" 的元素
  if (indexHtml.includes('id="app"') || indexHtml.includes("id='app'")) {
    return files;
  }

  // 替换 id="root" 为 id="app"，或在 body 后添加
  let fixed = indexHtml.replace(/id=["']root["']/gi, 'id="app"');

  if (!fixed.includes('id="app"')) {
    fixed = fixed.replace(/(<body[^>]*>)/i, '$1\n    <div id="app"></div>');
  }

  return { ...files, "/index.html": fixed };
}

export function buildSandpackConfig(
  template: string,
  files: Record<string, string>,
  entry?: string,
): SandpackConfig {
  const normalized = normalizePaths(files);
  const detected = resolveSandpackTemplate(template, normalized);
  let patchedFiles = mergePackageJsonForTemplate(detected, normalized);

  // 确保 Vue 项目的 index.html 有挂载点
  if (detected === "vue" || detected === "vue-ts") {
    patchedFiles = ensureVueIndexHtml(patchedFiles);
  }

  const entryFile = resolveEntryFile(patchedFiles, entry);
  const visibleFiles = Object.keys(patchedFiles);

  // shim 文件仅供打包器解析用，不出现在文件浏览器中
  const sandpackFiles = { ...VFILE_SHIMS, ...patchedFiles };

  if (detected === "static") {
    return {
      customSetup: { entry: entryFile, environment: "static" },
      files: sandpackFiles,
      entryFile,
      visibleFiles,
    };
  }

  // 框架模板：使用 customSetup.entry 覆盖 Sandpack 模板默认入口，
  // 防止模板的 Hello World 默认文件污染用户项目
  return {
    template: detected,
    customSetup: shouldUseTemplateEntrypoint(detected, entryFile, normalized)
      ? {}
      : { entry: entryFile },
    files: sandpackFiles,
    entryFile,
    visibleFiles,
  };
}
