import { extractText } from "./toolUtils";

export interface ToolSearchMatch {
  name: string;
  description: string;
}

export interface ToolSearchSummary {
  total: number;
  newlyLoaded: number;
  alreadyAvailable: number;
  matches: ToolSearchMatch[];
}

// search_tools 返回头：`Found 3 tool(s). Loaded 2 new; 1 already available. …`
const HEADER_RE =
  /^Found (\d+) tool\(s\)\. Loaded (\d+) new; (\d+) already available\./;

/**
 * 解析 search_tools 的文本结果：头部计数 + `## 工具名` 块。
 * 解析不出头部与任何块时返回 null（调用方回退原始文本展示）。
 */
export function parseToolSearchResult(
  result: unknown,
): ToolSearchSummary | null {
  const text = extractText(result as never);
  if (!text) return null;

  const header = text.match(HEADER_RE);

  const matches: ToolSearchMatch[] = [];
  const blocks = text.split(/\n(?=## )/g);
  for (const block of blocks) {
    if (!block.startsWith("## ")) continue;
    const name = block.slice(3).split("\n")[0].trim();
    if (!name) continue;
    const descMatch = block.match(/^Description: (.*)$/m);
    matches.push({
      name,
      description: (descMatch?.[1] || "").trim(),
    });
  }

  if (!header && matches.length === 0) return null;

  return {
    total: header ? Number(header[1]) : matches.length,
    newlyLoaded: header ? Number(header[2]) : 0,
    alreadyAvailable: header ? Number(header[3]) : 0,
    matches,
  };
}
