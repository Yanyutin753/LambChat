/** @vitest-environment jsdom */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { ReadFileItem } from "../ReadFileItem";
import { ExecuteItem } from "../ExecuteItem";
import { toolCallPanelStore } from "../../toolCallPanelStore";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
  toolCallPanelStore.clear();
});

test("ReadFileItem can open its panel while the tool is still running", () => {
  const view = render(
    <ReadFileItem
      id="read-1"
      args={{ file_path: "/tmp/a.txt" }}
      isPending
      startedAt="2026-08-29T10:00:00.000Z"
    />,
  );

  const pill = view.container.querySelector("button");
  expect(pill).toBeTruthy();
  // pending（result 未到）也允许打开面板实时等待结果
  expect(pill?.getAttribute("class")).toContain("cursor-pointer");
  pill?.click();

  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBe("tool:read-1");
});

test("ExecuteItem opens a live panel keyed by the tool call id", () => {
  const view = render(
    <ExecuteItem
      id="exec-1"
      args={{ command: "long-running" }}
      isPending
      startedAt="2026-08-29T10:00:00.000Z"
    />,
  );
  view.container.querySelector("button")?.click();

  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBe("tool:exec-1");
});

test("ExecuteItem panel content refreshes when the streamed result lands", async () => {
  const view = render(
    <ExecuteItem
      id="exec-2"
      args={{ command: "stream-me" }}
      isPending
      startedAt="2026-08-29T10:00:00.000Z"
    />,
  );
  view.container.querySelector("button")?.click();

  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBe("tool:exec-2");

  // 面板内容必须是订阅 store 的活组件，而非打开时刻的静态快照
  const rendered = render(state!.children as React.ReactElement);
  expect(rendered.getByText("stream-me")).toBeTruthy();
  expect(rendered.container.querySelector("pre")).toBe(null);

  toolCallPanelStore.set({
    toolCallId: "exec-2",
    toolName: "execute",
    formattedToolName: "Execute",
    args: { command: "stream-me" },
    result: "streamed output\n[Command succeeded with exit code 0]",
    success: true,
    isPending: false,
    startedAt: "2026-08-29T10:00:00.000Z",
    completedAt: "2026-08-29T10:00:02.000Z",
    status: "success",
  });

  await waitFor(() => {
    expect(rendered.getByText(/streamed output/)).toBeTruthy();
  });
  // 状态行被解析为退出码徽标而非留在输出正文里
  expect(rendered.queryByText(/Command succeeded/)).toBe(null);
  expect(rendered.container.querySelector("pre")?.textContent).toContain(
    "streamed output",
  );
});

test("ReadFileItem pill shows the line range so chunked reads are distinguishable", () => {
  const view = render(
    <ReadFileItem
      id="read-range-1"
      args={{ file_path: "/tmp/a.txt", offset: 99, limit: 200 }}
      isPending
      startedAt="2026-08-29T10:00:00.000Z"
    />,
  );
  // 折叠态的 pill 上就能看出读取的是哪一段
  expect(view.getByText(":L100-299")).toBeTruthy();
});

test("ReadFileItem pill omits the line range when reading without offset or limit", () => {
  const view = render(
    <ReadFileItem
      id="read-range-2"
      args={{ file_path: "/tmp/a.txt" }}
      isPending
      startedAt="2026-08-29T10:00:00.000Z"
    />,
  );
  expect(view.queryByText(/:L\d/)).toBe(null);
});
