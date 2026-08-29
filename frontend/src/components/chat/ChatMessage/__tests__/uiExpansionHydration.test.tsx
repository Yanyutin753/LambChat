/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { RunStepsCollapse } from "../RunStepsCollapse";
import { TodoBlock } from "../TodoBlock";
import {
  clearUiExpansions,
  getUiExpansion,
} from "../uiExpansionStore";

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

test("run-steps collapse choice survives virtualized unmount/remount", () => {
  const { unmount } = render(
    <RunStepsCollapse
      active
      stateKey="msg-1"
      steps={1}
      durationMs={null}
      renderExpanded={() => <div>step-details</div>}
    />,
  );
  expect(screen.getByText("step-details")).toBeTruthy();

  // 流式中手动收起
  fireEvent.click(screen.getByRole("button", { expanded: true }));
  expect(screen.queryByText("step-details")).toBeNull();
  expect(getUiExpansion("msg-1:run-steps")).toBe(false);

  // 模拟虚拟列表卸载再滚回重挂
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
  // 复水：保持用户收起的选择，而不是回弹到默认展开
  expect(screen.queryByText("step-details")).toBeNull();
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

  const { unmount } = render(
    <TodoBlock items={items} stateKey="msg-3:2" />,
  );
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
