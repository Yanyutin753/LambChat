import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

const fromFrontend = (path: string) =>
  readFileSync(resolve(process.cwd(), path), "utf8");

describe("Sandbox MCP removal", () => {
  test("MCP types and form expose only HTTP transports", () => {
    const typeSource = fromFrontend("src/types/mcp.ts");
    const formSource = fromFrontend("src/components/mcp/MCPServerForm.tsx");
    const sidebarSource = fromFrontend(
      "src/components/mcp/MCPServerToolsSidebar.tsx",
    );

    expect(typeSource).not.toContain('"sandbox"');
    expect(typeSource).not.toContain("env_keys");
    expect(sidebarSource).not.toContain("server.command");
    expect(formSource).not.toContain('value: "sandbox"');
    expect(formSource).not.toContain("MCP_WRITE_SANDBOX");
    expect(typeSource).toContain('"sse"');
    expect(typeSource).toContain('"streamable_http"');
  });

  test("chat renderer and panel do not expose Sandbox MCP controls", () => {
    const authSource = fromFrontend("src/types/auth.ts");
    const rendererSource = fromFrontend(
      "src/components/chat/ChatMessage/MessagePartRenderer.tsx",
    );
    const exportSource = fromFrontend(
      "src/components/chat/ChatMessage/ToolCallItem.tsx",
    );
    const panelSource = fromFrontend("src/components/panels/MCPPanel.tsx");

    expect(authSource).not.toContain("MCP_WRITE_SANDBOX");
    expect(rendererSource).not.toContain("SandboxMcpItem");
    expect(exportSource).not.toContain("SandboxMcpItem");
    expect(panelSource).not.toContain("MCP_WRITE_SANDBOX");
  });
});
