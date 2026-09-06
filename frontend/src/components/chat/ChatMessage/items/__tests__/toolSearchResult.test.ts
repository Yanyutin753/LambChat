import { describe, expect, test } from "vitest";
import { parseToolSearchResult } from "../toolSearchResult";

const realisticResult = [
  "Found 3 tool(s). Loaded 2 new; 1 already available. Returned schemas are callable; call it directly next.",
  "",
  "## mcp__github__create_issue",
  "Description: Create a GitHub issue in the specified repository with title and body.",
  "Schema:",
  "```json",
  '{"type":"object","properties":{"owner":{"type":"string"},"repo":{"type":"string"},"title":{"type":"string"}},"required":["owner","repo","title"]}',
  "```",
  "",
  "## mcp__github__list_prs",
  "Description: List pull requests for a repository with filters.",
  "Schema:",
  "```json",
  '{"type":"object","properties":{"state":{"type":"string"}}}',
  "```",
  "",
  "## mcp__slack__post_message",
  "Description: Post a message to a Slack channel.",
  "Schema:",
  "```json",
  '{"type":"object","properties":{"channel":{"type":"string"}}}',
  "```",
].join("\n");

describe("parseToolSearchResult", () => {
  test("parses header counts and tool blocks from realistic output", () => {
    const summary = parseToolSearchResult(realisticResult);
    expect(summary).not.toBeNull();
    expect(summary?.total).toBe(3);
    expect(summary?.newlyLoaded).toBe(2);
    expect(summary?.alreadyAvailable).toBe(1);
    expect(summary?.matches.map((m) => m.name)).toEqual([
      "mcp__github__create_issue",
      "mcp__github__list_prs",
      "mcp__slack__post_message",
    ]);
    expect(summary?.matches[0].description).toBe(
      "Create a GitHub issue in the specified repository with title and body.",
    );
  });

  test("returns null for the no-tools message", () => {
    expect(
      parseToolSearchResult(
        "No tools found matching 'draw'. Try different keywords or check the available tool list.",
      ),
    ).toBeNull();
  });

  test("returns null for empty or undefined result", () => {
    expect(parseToolSearchResult(undefined)).toBeNull();
    expect(parseToolSearchResult("")).toBeNull();
  });

  test("tolerates blocks without a description line", () => {
    const summary = parseToolSearchResult(
      [
        "Found 1 tool(s). Loaded 1 new; 0 already available.",
        "",
        "## lonely_tool",
        "Schema:",
        "```json",
        '{"type":"object"}',
        "```",
      ].join("\n"),
    );
    expect(summary?.total).toBe(1);
    expect(summary?.matches).toHaveLength(1);
    expect(summary?.matches[0].name).toBe("lonely_tool");
    expect(summary?.matches[0].description).toBe("");
  });

  test("keeps header counts when no blocks are parseable", () => {
    const summary = parseToolSearchResult(
      "Found 5 tool(s). Loaded 3 new; 2 already available.",
    );
    expect(summary?.total).toBe(5);
    expect(summary?.newlyLoaded).toBe(3);
    expect(summary?.alreadyAvailable).toBe(2);
    expect(summary?.matches).toEqual([]);
  });
});
