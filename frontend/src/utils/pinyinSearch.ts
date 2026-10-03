import type { ToolInfo } from "../types/tool";

type PinyinFn = (
  text: string,
  options: { toneType: "none"; separator: string },
) => string;

let pinyinFn: PinyinFn | null = null;
let preloading: Promise<void> | null = null;

/**
 * pinyin-pro is a ~440KB dictionary; only tool-search matching needs it, so
 * it loads on demand (when the selector opens) instead of the first-paint
 * shell. Until it resolves, toPinyin degrades to the original text.
 */
export function preloadPinyin(): Promise<void> {
  preloading ??= import("pinyin-pro").then((m) => {
    pinyinFn = m.pinyin as PinyinFn;
  });
  return preloading;
}

/**
 * Convert Chinese text to space-separated pinyin.
 * Non-Chinese characters are preserved as-is.
 */
export function toPinyin(text: string): string {
  return pinyinFn ? pinyinFn(text, { toneType: "none", separator: "" }) : text;
}

/**
 * Build a flat searchable text string from a tool's fields.
 */
function buildSearchableText(
  tool: ToolInfo,
  getCategoryLabel: (key: string) => string,
): string {
  const parts: (string | undefined)[] = [
    tool.name,
    tool.description,
    tool.server,
    getCategoryLabel(`tools.categories.${tool.category}`),
    ...(tool.parameters?.flatMap((param) => [
      param.name,
      param.type,
      param.description,
    ]) ?? []),
  ];
  return parts
    .filter((p): p is string => Boolean(p))
    .join(" ")
    .toLowerCase();
}

/**
 * Tokenize a query into whitespace-separated terms.
 */
function tokenize(query: string): string[] {
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

/**
 * Check if a tool matches a search query with pinyin support.
 *
 * Tokenizes the query into terms (OR semantics: any term matching is enough).
 * Each term is checked against both the original text and its pinyin equivalent,
 * supporting:
 * - Direct substring match (e.g. "search" matches "web_search_tool")
 * - Chinese characters (e.g. "搜索" matches "搜索工具")
 * - Pinyin (e.g. "sousuo" matches "搜索工具")
 * - Mixed (e.g. "web 搜索" or "web sousuo")
 */
export function matchTool(
  query: string,
  tool: ToolInfo,
  getCategoryLabel: (key: string) => string,
): boolean {
  const terms = tokenize(query);
  if (terms.length === 0) return true;

  const text = buildSearchableText(tool, getCategoryLabel);
  const textPinyin = toPinyin(text);

  // OR semantics: any term matching is enough
  return terms.some((term) => text.includes(term) || textPinyin.includes(term));
}
