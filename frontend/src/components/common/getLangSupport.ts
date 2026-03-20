import type { Extension } from "@codemirror/state";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { json } from "@codemirror/lang-json";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { sql } from "@codemirror/lang-sql";

// Map a language name (from markdown fenced code blocks) or file extension to a CodeMirror language support.
// Returns `undefined` for unknown languages (CodeMirror will use plain text).
export function getLangSupport(
  language?: string,
  filePath?: string,
): Extension | undefined {
  // Prefer explicit language name from code blocks
  const lang = language?.toLowerCase() || "";
  const ext = filePath
    ? filePath.split(".").pop()?.toLowerCase() ?? ""
    : "";

  // Map language names from markdown fences (e.g. ```typescript, ```py)
  const langMap: Record<string, () => Extension> = {
    js: () => javascript({ jsx: true }),
    jsx: () => javascript({ jsx: true }),
    javascript: () => javascript({ jsx: true }),
    ts: () => javascript({ jsx: true, typescript: true }),
    tsx: () => javascript({ jsx: true, typescript: true }),
    typescript: () => javascript({ jsx: true, typescript: true }),
    py: () => python(),
    python: () => python(),
    md: () => markdown({ base: markdownLanguage }),
    markdown: () => markdown({ base: markdownLanguage }),
    yaml: () => yaml(),
    yml: () => yaml(),
    json: () => json(),
    html: () => html(),
    htm: () => html(),
    css: () => css(),
    scss: () => css(),
    less: () => css(),
    sql: () => sql(),
  };

  // Also map by file extension when no explicit language is given
  if (!lang && ext) {
    return langMap[ext]?.();
  }

  return langMap[lang]?.();
}
