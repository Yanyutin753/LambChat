// MCP content block 类型 (后端 _normalize_content 返回)
export interface McpContentBlock {
  type: "text" | "image" | "file";
  text?: string;
  base64?: string;
  url?: string;
  mime_type?: string;
}

// MCP 多模态结果格式
export interface McpMultiModalResult {
  text?: string;
  blocks?: McpContentBlock[];
}

// 检测文本是否可能是 markdown 格式
export function isMarkdownText(text: string): boolean {
  const markdownPatterns = [
    /^#{1,6}\s/m,
    /^\*\s/m,
    /^-{1,3}\s/m,
    /^\d+\.\s/m,
    /\[.+\]\(.+\)/,
    /\*\*.+\*\*/,
    /\*.+\*/,
    /`[^`]+`/,
    /^```[\s\S]*?^```/m,
    /^\s*>/m,
    /\|.+\|/,
  ];

  let matchCount = 0;
  for (const pattern of markdownPatterns) {
    if (pattern.test(text)) {
      matchCount++;
      if (matchCount >= 2) return true;
    }
  }
  return false;
}

// 去除 cat -n 格式的行号前缀 (如 "  201\tcontent"、"201→content"、continuation markers "  201.1\t...")
export function stripLineNumbers(text: string): string {
  return text.replace(/^\s*\d+(?:\.\d+)?[→\t]/gm, "");
}

// 从工具结果中提取纯文本（兼容 LangChain 原生格式）
export function extractText(
  result: string | Record<string, unknown> | undefined,
): string {
  if (!result) return "";
  if (typeof result === "string") return result;

  const content = result.content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (b: Record<string, unknown>) =>
          b.type === "text" && typeof b.text === "string",
      )
      .map((b: Record<string, unknown>) => b.text as string)
      .join("\n");
  }
  if (typeof content === "string") return content;

  if (typeof result.text === "string") return result.text;

  return JSON.stringify(result, null, 2);
}

// 从工具结果中提取路径列表（兼容 deepagents ls 工具返回的 Python 列表字符串格式）
export function extractPaths(
  result: string | Record<string, unknown> | undefined,
): string[] {
  const text = extractText(result);
  if (!text) return [];

  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed
        .map((item: unknown) =>
          typeof item === "string" ? item : String(item),
        )
        .filter(Boolean);
    }
  } catch {
    // 非 JSON
  }

  const pythonListMatch = text.match(/^\[([\s\S]*)\]$/);
  if (pythonListMatch) {
    try {
      const jsonStr = pythonListMatch[1]
        .replace(/\\'/g, "\\'")
        .replace(/'/g, '"');
      const parsed = JSON.parse(`[${jsonStr}]`);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item: unknown) =>
            typeof item === "string" ? item : String(item),
          )
          .filter(Boolean);
      }
    } catch {
      // 解析失败，按行处理
    }
  }

  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
