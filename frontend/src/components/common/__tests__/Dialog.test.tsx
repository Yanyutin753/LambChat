/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { Dialog } from "../Dialog";

afterEach(cleanup);

test("renders portal content with title, body and footer", () => {
  render(
    <Dialog
      open
      onClose={() => undefined}
      title="通用弹窗"
      footer={<button>确定</button>}
    >
      <p>内容</p>
    </Dialog>,
  );
  expect(screen.getByText("通用弹窗")).toBeTruthy();
  expect(screen.getByText("内容")).toBeTruthy();
  expect(screen.getByText("确定")).toBeTruthy();
});

test("escape and backdrop click close when dismissible", () => {
  const onClose = vi.fn();
  render(
    <Dialog open onClose={onClose} title="标题">
      <p>内容</p>
    </Dialog>,
  );
  fireEvent.click(document.querySelector("[data-dialog-backdrop]")!);
  expect(onClose).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(2);
});

test("non-dismissible dialog ignores escape, backdrop and hides close button", () => {
  const onClose = vi.fn();
  render(
    <Dialog open onClose={onClose} title="下载中" dismissible={false}>
      <p>内容</p>
    </Dialog>,
  );
  fireEvent.click(document.querySelector("[data-dialog-backdrop]")!);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).not.toHaveBeenCalled();
  // 关闭按钮隐藏（下载中不允许关闭）
  expect(screen.queryByRole("button", { name: /关闭|close/i })).toBeNull();
});

test("closed dialog renders nothing", () => {
  render(
    <Dialog open={false} onClose={() => undefined} title="标题">
      <p>内容</p>
    </Dialog>,
  );
  expect(screen.queryByText("内容")).toBeNull();
});
