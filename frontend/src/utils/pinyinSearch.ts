import { pinyin } from "pinyin-pro";
import type { ToolInfo } from "../types/tool";

/**
 * Convert Chinese text to space-separated pinyin.
 * Non-Chinese characters are preserved as-is.
 */
export function toPinyin(text: string): string {
  return pinyin(text, { toneType: "none", separator: "" });
}

/**
 * Build a flat searchable text string from a tool's fields.
 */
function buildSearchableText(
  tool: ToolInfo,
  getCategoryLabel: (key: string) => string,
): string {
  const parts: string[] = [
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
  return parts.filter(Boolean).join(" ").toLowerCase();
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
