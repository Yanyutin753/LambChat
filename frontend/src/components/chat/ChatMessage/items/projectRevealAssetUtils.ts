const URL_LIKE_PREFIX = /^(?:[a-z]+:)?\/\//i;

function normalizeProjectPath(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/");
  const resolved: string[] = [];

  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") {
      resolved.pop();
      continue;
    }
    resolved.push(part);
  }

  return `/${resolved.join("/")}`;
}

function getDirectoryPath(path: string): string {
  const normalized = normalizeProjectPath(path);
  const lastSlash = normalized.lastIndexOf("/");
  if (lastSlash <= 0) {
    return "/";
  }
  return normalized.slice(0, lastSlash);
}

function resolveAssetPath(
  sourcePath: string,
  rawReference: string,
): string | null {
  const reference = rawReference.trim();

  if (
    !reference ||
    reference.startsWith("#") ||
    reference.startsWith("data:") ||
    reference.startsWith("blob:") ||
    URL_LIKE_PREFIX.test(reference)
  ) {
    return null;
  }

  const [pathWithoutHash] = reference.split("#", 1);
  const [pathWithoutQuery] = pathWithoutHash.split("?", 1);

  if (!pathWithoutQuery) {
    return null;
  }

  if (pathWithoutQuery.startsWith("/")) {
    return normalizeProjectPath(pathWithoutQuery);
  }

  return normalizeProjectPath(
    `${getDirectoryPath(sourcePath)}/${pathWithoutQuery}`,
  );
}

function jsonString(value: string): string {
  return JSON.stringify(value);
}

function rewriteHtmlAndCssRefs(
  sourcePath: string,
  content: string,
  binaryUrlMap: Record<string, string>,
): string {
  let rewritten = content;

  rewritten = rewritten.replace(
    /(url\(\s*['"]?)([^'")]+)(['"]?\s*\))/g,
    (match, prefix: string, rawRef: string, suffix: string) => {
      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return `${prefix}${fullUrl}${suffix}`;
    },
  );

  rewritten = rewritten.replace(
    /((?:src|href)=['"])([^'"]+)(['"])/g,
    (match, prefix: string, rawRef: string, suffix: string) => {
      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return `${prefix}${fullUrl}${suffix}`;
    },
  );

  return rewritten;
}

function rewriteStaticAssetImports(
  sourcePath: string,
  content: string,
  binaryUrlMap: Record<string, string>,
): string {
  let rewritten = content;

  rewritten = rewritten.replace(
    /^(\s*)import\s+([A-Za-z_$][\w$]*)\s+from\s+(['"])([^'"]+)\3;?$/gm,
    (
      match,
      indent: string,
      binding: string,
      _quote: string,
      rawRef: string,
    ) => {
      // 跳过 .vue, .jsx, .tsx, .svelte 等组件文件
      if (/\.(vue|jsx|tsx|svelte)$/i.test(rawRef)) {
        return match;
      }

      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return `${indent}const ${binding} = ${jsonString(fullUrl)};`;
    },
  );

  rewritten = rewritten.replace(
    /^(\s*)import\s+\{\s*default\s+as\s+([A-Za-z_$][\w$]*)\s*\}\s+from\s+(['"])([^'"]+)\3;?$/gm,
    (
      match,
      indent: string,
      binding: string,
      _quote: string,
      rawRef: string,
    ) => {
      // 跳过 .vue, .jsx, .tsx, .svelte 等组件文件
      if (/\.(vue|jsx|tsx|svelte)$/i.test(rawRef)) {
        return match;
      }

      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return `${indent}const ${binding} = ${jsonString(fullUrl)};`;
    },
  );

  rewritten = rewritten.replace(
    /new\s+URL\(\s*(['"])([^'"]+)\1\s*,\s*import\.meta\.url\s*\)\.href/g,
    (match, _quote: string, rawRef: string) => {
      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return jsonString(fullUrl);
    },
  );

  rewritten = rewritten.replace(
    /new\s+URL\(\s*(['"])([^'"]+)\1\s*,\s*import\.meta\.url\s*\)/g,
    (match, _quote: string, rawRef: string) => {
      const resolvedPath = resolveAssetPath(sourcePath, rawRef);
      if (!resolvedPath) return match;

      const fullUrl = binaryUrlMap[resolvedPath];
      if (!fullUrl) return match;

      return `new URL(${jsonString(fullUrl)})`;
    },
  );

  return rewritten;
}

export function rewriteProjectFileContent(
  sourcePath: string,
  content: string,
  binaryUrlMap: Record<string, string>,
): string {
  const withAssetImports = rewriteStaticAssetImports(
    sourcePath,
    content,
    binaryUrlMap,
  );

  return rewriteHtmlAndCssRefs(sourcePath, withAssetImports, binaryUrlMap);
}

export function rewriteProjectTextFiles(
  files: Record<string, string>,
  binaryUrlMap: Record<string, string>,
): Record<string, string> {
  const rewritten: Record<string, string> = {};

  for (const [path, content] of Object.entries(files)) {
    rewritten[path] = rewriteProjectFileContent(path, content, binaryUrlMap);
  }

  return rewritten;
}
