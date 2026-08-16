import { matchTool, toPinyin } from "../pinyinSearch";
import type { ToolInfo } from "../../types/tool";

const mockT = (key: string) => key;

function makeTool(overrides: Partial<ToolInfo> = {}): ToolInfo {
  return {
    name: "搜索工具",
    description: "搜索互联网内容",
    category: "mcp",
    server: "search_server",
    parameters: [
      {
        name: "query",
        type: "string",
        description: "搜索关键词",
        required: true,
      },
    ],
    ...overrides,
  };
}

describe("toPinyin", () => {
  it("converts Chinese characters to pinyin", () => {
    expect(toPinyin("搜索")).toBe("sousuo");
  });

  it("preserves non-Chinese characters", () => {
    expect(toPinyin("web_search")).toBe("web_search");
  });

  it("handles mixed content", () => {
    expect(toPinyin("web搜索")).toBe("websousuo");
  });
});

describe("matchTool", () => {
  it("returns true for empty query", () => {
    expect(matchTool("", makeTool(), mockT)).toBe(true);
    expect(matchTool("   ", makeTool(), mockT)).toBe(true);
  });

  it("matches by Chinese name", () => {
    expect(matchTool("搜索", makeTool(), mockT)).toBe(true);
  });

  it("matches by pinyin input", () => {
    expect(matchTool("sousuo", makeTool(), mockT)).toBe(true);
  });

  it("matches by server name", () => {
    expect(matchTool("search_server", makeTool(), mockT)).toBe(true);
  });

  it("matches by parameter name", () => {
    expect(matchTool("query", makeTool(), mockT)).toBe(true);
  });

  it("supports OR semantics with multiple terms", () => {
    const tool = makeTool({
      name: "alpha_tool",
      description: "does alpha things",
    });
    // "alpha" matches, "zzz" doesn't — but OR means it still matches
    expect(matchTool("alpha zzz", tool, mockT)).toBe(true);
  });

  it("returns false when no terms match", () => {
    expect(matchTool("nonexistent", makeTool(), mockT)).toBe(false);
  });

  it("handles English tool names with pinyin query", () => {
    const tool = makeTool({
      name: "xiaohongshu_publish",
      description: "publish to xiaohongshu",
    });
    expect(matchTool("xiaohongshu", tool, mockT)).toBe(true);
  });
});
