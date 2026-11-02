/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { FormField } from "../../../types";
import {
  loadApprovalFormDraft,
  removeApprovalFormDraft,
  saveApprovalFormDraft,
} from "../approvalDraftStore";

const fields: FormField[] = [
  { name: "title", label: "标题", type: "text", required: true },
  { name: "detail", label: "详情", type: "textarea", required: false },
  { name: "count", label: "数量", type: "number", required: false },
  { name: "agree", label: "同意", type: "checkbox", required: false },
  {
    name: "platform",
    label: "平台",
    type: "radio",
    required: false,
    options: ["桌面端", "移动端"],
  },
  {
    name: "stack",
    label: "技术栈",
    type: "multi_select",
    required: false,
    options: ["react", "vue"],
  },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("round-trips values for every field type", () => {
  saveApprovalFormDraft("approval-1", {
    title: "发布 2.16",
    detail: "",
    count: 0,
    agree: false,
    platform: "桌面端",
    stack: ["react", "vue"],
  });

  expect(loadApprovalFormDraft("approval-1", fields)).toEqual({
    title: "发布 2.16",
    detail: "",
    count: 0,
    agree: false,
    platform: "桌面端",
    stack: ["react", "vue"],
  });
});

test("returns null when no draft was saved", () => {
  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("only restores values whose field still exists with a matching type", () => {
  saveApprovalFormDraft("approval-1", {
    title: "保留",
    count: "不是数字",
    agree: "yes",
    removed_field: "已删除的字段",
  });

  expect(loadApprovalFormDraft("approval-1", fields)).toEqual({
    title: "保留",
  });
});

test("drops choice values that are no longer offered as options", () => {
  saveApprovalFormDraft("approval-1", {
    platform: "已下线的选项",
    stack: ["react", "svelte"],
  });

  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("ignores corrupt storage entries", () => {
  localStorage.setItem("approvalFormDraft:approval-1", "{not json");

  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("ignores drafts stored with a different envelope version", () => {
  localStorage.setItem(
    "approvalFormDraft:approval-1",
    JSON.stringify({
      version: 2,
      savedAt: Date.now(),
      values: { title: "未来版本" },
    }),
  );

  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("drops drafts older than a week", () => {
  const weekAgo = Date.now() - 8 * 24 * 60 * 60 * 1000;
  localStorage.setItem(
    "approvalFormDraft:approval-1",
    JSON.stringify({
      version: 1,
      savedAt: weekAgo,
      values: { title: "旧草稿" },
    }),
  );

  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("remove deletes the stored draft", () => {
  saveApprovalFormDraft("approval-1", { title: "待清理" });
  removeApprovalFormDraft("approval-1");

  expect(loadApprovalFormDraft("approval-1", fields)).toBeNull();
});

test("save stays silent when the storage quota is exhausted", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("QuotaExceededError");
  });

  expect(() =>
    saveApprovalFormDraft("approval-1", { title: "存不下" }),
  ).not.toThrow();
});
