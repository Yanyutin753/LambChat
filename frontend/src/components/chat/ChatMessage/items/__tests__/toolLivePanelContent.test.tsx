/** @vitest-environment jsdom */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test } from "vitest";

import {
  ToolLivePanelContent,
  openToolLivePanel,
  shouldStickPanelOutputToBottom,
  toolDetailPropsFromPanelData,
} from "../ToolLivePanelContent";
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

function panelData(
  overrides: Partial<Parameters<typeof toolCallPanelStore.set>[0]> = {},
) {
  return {
    toolCallId: "tool-live-1",
    toolName: "read_file",
    formattedToolName: "Read File",
    args: { file_path: "/tmp/a.txt" },
    status: "loading" as const,
    ...overrides,
  };
}

test("renders the fallback snapshot until the store knows the tool", () => {
  const view = render(
    <ToolLivePanelContent
      toolCallId="tool-live-1"
      build={(data) => <div>live:{String(data.result)}</div>}
      fallback={<div>snapshot</div>}
    />,
  );

  expect(view.getByText("snapshot")).toBeTruthy();

  toolCallPanelStore.set(panelData({ result: "streamed" }));

  return waitFor(() => {
    expect(view.getByText("live:streamed")).toBeTruthy();
  });
});

test("re-renders live content when the streamed result updates", async () => {
  toolCallPanelStore.set(panelData({ result: "first" }));

  const view = render(
    <ToolLivePanelContent
      toolCallId="tool-live-1"
      build={(data) => <div>live:{String(data.result)}</div>}
    />,
  );

  expect(view.getByText("live:first")).toBeTruthy();

  toolCallPanelStore.set(panelData({ result: "second", status: "success" }));

  await waitFor(() => {
    expect(view.getByText("live:second")).toBeTruthy();
  });
});

test("keeps inner component state across live updates (no remount)", async () => {
  toolCallPanelStore.set(panelData({ result: "first" }));

  function Detail({ result }: { result?: string | Record<string, unknown> }) {
    const [clicks, setClicks] = useState(0);
    return (
      <div>
        <span>live:{String(result)}</span>
        <button type="button" onClick={() => setClicks((n) => n + 1)}>
          count:{clicks}
        </button>
      </div>
    );
  }

  const view = render(
    <ToolLivePanelContent
      toolCallId="tool-live-1"
      build={(data) => <Detail result={data.result} />}
    />,
  );

  view.getByText("count:0").click();
  await waitFor(() => view.getByText("count:1"));

  toolCallPanelStore.set(panelData({ result: "second" }));

  await waitFor(() => {
    expect(view.getByText("live:second")).toBeTruthy();
  });
  // 详情组件不应因流式更新被重挂载（CodeMirror 等重内容不能闪烁）
  expect(view.getByText("count:1")).toBeTruthy();
});

test("openToolLivePanel wires a live panel keyed by the tool call id", async () => {
  openToolLivePanel({
    id: "tool-live-1",
    title: "Read File",
    status: "loading",
    fallback: <div>snapshot</div>,
    buildDetail: (data) => <div>live:{String(data.result)}</div>,
    footer: <div>footer</div>,
  });

  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBe("tool:tool-live-1");
  expect(state?.children).toBeTruthy();

  // 供 PersistentToolPanelHost 的 useLiveToolPanelData 实时刷新状态/页脚
  expect(state?.status).toBe("loading");

  render(state!.children as React.ReactElement);
  expect(screen.getByText("snapshot")).toBeTruthy();

  toolCallPanelStore.set(panelData({ result: "arrived" }));
  await waitFor(() => {
    expect(screen.getByText("live:arrived")).toBeTruthy();
  });
});

test("openToolLivePanel without id falls back to the static snapshot", () => {
  openToolLivePanel({
    title: "Read File",
    status: "success",
    fallback: <div>snapshot-only</div>,
    buildDetail: () => <div>unused</div>,
  });

  const state = getPersistentToolPanelState();
  expect(state?.panelKey).toBeUndefined();
  expect(state?.children).toBeTruthy();
  render(state!.children as React.ReactElement);
  expect(screen.getByText("snapshot-only")).toBeTruthy();
});

test("toolDetailPropsFromPanelData maps store data onto tool item props", () => {
  expect(
    toolDetailPropsFromPanelData(
      panelData({
        result: "ok",
        success: true,
        isPending: false,
        startedAt: "2026-08-29T10:00:00.000Z",
        completedAt: "2026-08-29T10:00:02.000Z",
      }),
    ),
  ).toEqual({
    args: { file_path: "/tmp/a.txt" },
    result: "ok",
    success: true,
    isPending: false,
    cancelled: undefined,
    startedAt: "2026-08-29T10:00:00.000Z",
    completedAt: "2026-08-29T10:00:02.000Z",
  });
});

test("shouldStickPanelOutputToBottom only sticks when near the bottom", () => {
  const el = document.createElement("div");
  Object.defineProperties(el, {
    scrollHeight: { value: 400, configurable: true },
    clientHeight: { value: 200, configurable: true },
  });
  Object.defineProperty(el, "scrollTop", {
    value: 190,
    writable: true,
    configurable: true,
  });

  expect(shouldStickPanelOutputToBottom(el)).toBe(true);

  el.scrollTop = 0;
  expect(shouldStickPanelOutputToBottom(el)).toBe(false);
});

test("live updates keep the panel body pinned to the bottom when already near it", async () => {
  const scroller = document.createElement("div");
  scroller.setAttribute("data-sidebar-snapshot-key", "panel-body");
  document.body.appendChild(scroller);
  Object.defineProperties(scroller, {
    scrollHeight: { value: 500, configurable: true },
    clientHeight: { value: 300, configurable: true },
  });
  Object.defineProperty(scroller, "scrollTop", {
    value: 180,
    writable: true,
    configurable: true,
  });

  const view = render(
    <ToolLivePanelContent
      toolCallId="tool-live-1"
      build={(data) => <div>live:{String(data.result)}</div>}
    />,
    { container: document.body.appendChild(document.createElement("div")) },
  );
  // 把内容挂进 scroller，closest 才能找到滚动容器
  scroller.appendChild(view.container);

  toolCallPanelStore.set(panelData({ result: "grow" }));
  await waitFor(() => {
    expect(view.getByText("live:grow")).toBeTruthy();
  });

  expect(scroller.scrollTop).toBe(500);

  // 用户在面板内上滑后，更新不再强行拉底
  scroller.scrollTop = 0;
  toolCallPanelStore.set(panelData({ result: "more" }));
  await waitFor(() => {
    expect(view.getByText("live:more")).toBeTruthy();
  });
  expect(scroller.scrollTop).toBe(0);

  scroller.remove();
});
