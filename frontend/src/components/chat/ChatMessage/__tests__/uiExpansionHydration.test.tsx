/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { RunStepsCollapse } from "../RunStepsCollapse";
import { TodoBlock } from "../TodoBlock";
import { clearUiExpansions } from "../uiExpansionStore";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: unknown) => {
      const templates: Record<string, string> = {
        "chat.message.runStepsSummary": "Worked for {{duration}}",
        "chat.message.runStepsCount": "{{count}} steps",
        "chat.message.runStepsWorking": "Working… {{duration}}",
        "chat.message.runStepsWorkingNoTimer": "Working…",
        "chat.todo.progress": "{{completed}}/{{total}}",
      };
      let out = templates[key] ?? key;
      if (opts && typeof opts === "object") {
        for (const [k, v] of Object.entries(opts as Record<string, unknown>)) {
          out = out.split(`{{${k}}}`).join(String(v));
        }
      }
      return out;
    },
    i18n: { language: "en" },
  }),
}));

afterEach(() => {
  cleanup();
  clearUiExpansions();
});

test("active run row shows details without a toggle, surviving unmount/remount", () => {
  const { unmount } = render(
    <RunStepsCollapse
      active
      stateKey="msg-1"
      steps={1}
      durationMs={null}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  // 工作中无展开收起控件，详情直接可见
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getByText("step-details")).toBeTruthy();

  // 模拟虚拟列表卸载再滚回重挂：行为不变
  unmount();
  render(
    <RunStepsCollapse
      active
      stateKey="msg-1"
      steps={1}
      durationMs={null}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getByText("step-details")).toBeTruthy();
});

test("run-steps history remount keeps expanded state after completion", () => {
  const { rerender, unmount } = render(
    <RunStepsCollapse
      active
      stateKey="msg-2"
      steps={1}
      durationMs={null}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  // 结束后用户重新展开
  rerender(
    <RunStepsCollapse
      stateKey="msg-2"
      steps={1}
      durationMs={60000}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  expect(screen.queryByText("step-details")).toBeNull();
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  expect(screen.getByText("step-details")).toBeTruthy();

  // 卸载重挂（历史消息）：保持展开，不被"完成自动收起"误伤
  unmount();
  render(
    <RunStepsCollapse
      stateKey="msg-2"
      steps={1}
      durationMs={60000}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  expect(screen.getByText("step-details")).toBeTruthy();
});

test("todo block collapse survives virtualized unmount/remount", () => {
  const items = [
    { content: "task-a", status: "completed" as const },
    { content: "task-b", status: "in_progress" as const },
  ];

  const { unmount } = render(<TodoBlock items={items} stateKey="msg-3:2" />);
  expect(screen.getByText("task-a")).toBeTruthy();

  // 收起整块
  fireEvent.click(screen.getByRole("button", { expanded: true }));
  expect(screen.queryByText("task-a")).toBeNull();

  unmount();
  render(<TodoBlock items={items} stateKey="msg-3:2" />);
  expect(screen.queryByText("task-a")).toBeNull();

  // 再点开
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  expect(screen.getByText("task-a")).toBeTruthy();
});
