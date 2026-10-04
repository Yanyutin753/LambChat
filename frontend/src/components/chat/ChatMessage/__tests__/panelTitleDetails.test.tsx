/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ThinkingBlock } from "../ThinkingBlock";
import { SummaryItem } from "../SummaryItem";
import { ToolCallItem } from "../ToolCallItem";
import { EvalItem } from "../items/EvalItem";
import { EnvVarItem } from "../items/EnvVarItem";
import { MemoryStoreItem } from "../items/MemoryStoreItem";
import { ImageAnalyzeItem } from "../items/ImageAnalyzeItem";
import { VideoAnalyzeItem } from "../items/VideoAnalyzeItem";
import { openSubagentPanelByAgentId } from "../SubagentBlock";
import { subagentPanelStore } from "../subagentPanelStore";
import { toolCallPanelStore } from "../toolCallPanelStore";
import { BlockPreviewPortal } from "../items/McpBlockPreview";
import {
  clearBlockPreviews,
  openBlockPreview,
} from "../items/blockPreviewStore";
import {
  closeAllPersistentToolPanels,
  getPersistentToolPanelState,
  PersistentToolPanelHost,
} from "../items/persistentToolPanelState";
import { resetRightPanelCoordinator } from "../../../common/rightPanelCoordinator";

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
  clearBlockPreviews();
  subagentPanelStore.clear();
  toolCallPanelStore.clear();
  resetRightPanelCoordinator();
});

test.each([
  {
    name: "thinking",
    node: <ThinkingBlock content="检查内存占用" panelKey="thought:1" />,
    summary: "检查内存占用",
  },
  {
    name: "summary",
    node: <SummaryItem content="性能排查结论" panelKey="summary:1" />,
    summary: "性能排查结论",
  },
  {
    name: "MCP",
    node: (
      <ToolCallItem
        id="mcp:1"
        name="browser:search"
        args={{ query: "React hooks" }}
        success
      />
    ),
    summary: "React hooks",
  },
  {
    name: "eval",
    node: (
      <EvalItem
        id="eval:1"
        args={{ code: "print(42)", language: "python" }}
        success
      />
    ),
    summary: "print(42)",
  },
  {
    name: "environment",
    node: (
      <EnvVarItem
        id="env:1"
        toolName="set_env_var"
        args={{ key: "API_TOKEN", value: "secret-value" }}
        success
      />
    ),
    summary: "API_TOKEN",
  },
  {
    name: "memory delete",
    node: (
      <MemoryStoreItem
        id="memory:1"
        toolName="memory_delete"
        args={{ memory_id: "memory-123" }}
        success
      />
    ),
    summary: "memory-123",
  },
  {
    name: "image analysis",
    node: (
      <ImageAnalyzeItem
        id="image:1"
        args={{
          image_urls: ["https://example.com/chart.png"],
          prompt: "分析季度趋势",
        }}
        success
      />
    ),
    summary: "分析季度趋势",
  },
  {
    name: "video analysis",
    node: (
      <VideoAnalyzeItem
        id="video:1"
        args={{
          video_urls: ["https://example.com/demo.mp4"],
          prompt: "检查操作步骤",
        }}
        success
      />
    ),
    summary: "检查操作步骤",
  },
])(
  "$name panels include identifying content in their tabs",
  ({ node, summary }) => {
    const view = render(node);
    fireEvent.click(view.container.querySelector("button")!);
    const panel = getPersistentToolPanelState();
    expect(panel?.subtitle ?? "").toContain(summary);
    expect(panel?.subtitle).not.toContain("secret-value");

    render(<PersistentToolPanelHost />);
    expect(view.getByRole("tab")).toHaveTextContent(summary);
  },
);

test.each([
  { name: "thinking", Component: ThinkingBlock },
  { name: "summary", Component: SummaryItem },
])("$name panel summaries follow content updates", ({ Component }) => {
  const view = render(<Component content="检查内存" panelKey="content:1" />);
  fireEvent.click(view.container.querySelector("button")!);
  view.rerender(
    <Component content={"检查内存\n并确认进程占用"} panelKey="content:1" />,
  );
  expect(getPersistentToolPanelState()?.subtitle).toBe(
    "检查内存 并确认进程占用",
  );
});

test("subagent tabs identify the task and follow durable input updates", () => {
  subagentPanelStore.set({
    agentId: "worker-1",
    agentName: "worker",
    input: "检查前端布局",
    status: "complete",
  });
  act(() => {
    openSubagentPanelByAgentId("worker-1");
  });
  const view = render(<PersistentToolPanelHost />);
  expect(view.getByRole("tab")).toHaveTextContent("检查前端布局");
  act(() => {
    subagentPanelStore.set({
      agentId: "worker-1",
      agentName: "worker",
      input: "检查移动端布局",
      status: "complete",
    });
  });
  expect(view.getByRole("tab")).toHaveTextContent("检查移动端布局");
});

test("text output previews identify their contents", () => {
  openBlockPreview({ type: "text", text: "CPU usage: 15%" });
  const view = render(<BlockPreviewPortal />);
  expect(view.getByRole("tab")).toHaveTextContent("CPU usage: 15%");
});

test("image output previews identify the source without exposing inline data", () => {
  openBlockPreview({ type: "image", src: "https://example.com/chart.png" });
  const view = render(<BlockPreviewPortal />);
  expect(view.getByRole("tab")).toHaveTextContent("chart.png");
  act(() => {
    openBlockPreview({
      type: "image",
      src: "data:image/png;base64,private-image-data",
    });
  });
  const selected = view.getByRole("tab", { selected: true });
  expect(selected).toHaveTextContent("2");
  expect(selected.getAttribute("title")).not.toContain("private-image-data");
});
