/** @vitest-environment jsdom */
import { beforeEach, expect, test, vi } from "vitest";
import {
  getUpdateChannel,
  setUpdateChannel,
  setUpdateBusy,
  getUpdateRevision,
} from "../updateChannel";
beforeEach(() => {
  setUpdateBusy(false);
  setUpdateChannel("stable");
  localStorage.clear();
});
test("defaults to stable and persists explicit dev opt-in", () => {
  expect(getUpdateChannel()).toBe("stable");
  expect(setUpdateChannel("dev")).toBe(true);
  expect(getUpdateChannel()).toBe("dev");
  expect(localStorage.getItem("lambchat:update-channel")).toBe("dev");
});
test("refuses channel switch while downloading and invalidates prior checks after switching", () => {
  const revision = getUpdateRevision();
  setUpdateBusy(true);
  expect(setUpdateChannel("dev")).toBe(false);
  expect(getUpdateRevision()).toBe(revision);
  setUpdateBusy(false);
  expect(setUpdateChannel("dev")).toBe(true);
  expect(getUpdateRevision()).not.toBe(revision);
});

test("keeps the selected channel for this session when storage writes fail", () => {
  const write = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw new Error("quota");
    });
  setUpdateChannel("dev");
  expect(getUpdateChannel()).toBe("dev");
  write.mockRestore();
  setUpdateChannel("stable");
});
