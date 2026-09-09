import { expect, test } from "vitest";

import {
  isVersionSkipped,
  readSkippedUpdateVersions,
  shouldPromptUpdate,
} from "../useAutoUpdate";

function fakeStorage(initial: string | null) {
  return {
    getItem: (_k: string) => initial,
    setItem: (_k: string, _v: string) => undefined,
  };
}

test("readSkippedUpdateVersions tolerates missing and malformed data", () => {
  expect(readSkippedUpdateVersions(fakeStorage(null))).toEqual([]);
  expect(readSkippedUpdateVersions(fakeStorage("garbage"))).toEqual([]);
  expect(
    readSkippedUpdateVersions(fakeStorage('["2.10.1","2.11.0"]')),
  ).toEqual(["2.10.1", "2.11.0"]);
  // 非字符串成员过滤
  expect(
    readSkippedUpdateVersions(fakeStorage('[2.1,"2.11.0"]')),
  ).toEqual(["2.11.0"]);
});

test("isVersionSkipped matches exact versions only", () => {
  const skipped = ["2.10.1"];
  expect(isVersionSkipped("2.10.1", skipped)).toBe(true);
  expect(isVersionSkipped("2.10.10", skipped)).toBe(false);
  expect(isVersionSkipped(null, skipped)).toBe(false);
  expect(isVersionSkipped("2.11.0", [])).toBe(false);
});

test("shouldPromptUpdate: skipped version stays quiet unless manual check", () => {
  const skipped = ["2.11.0"];
  // 后台/启动检查：跳过过的版本不再打扰（标准开源更新器行为）
  expect(
    shouldPromptUpdate("2.11.0", skipped, { manual: false }),
  ).toBe(false);
  // 手动「检查更新」无视跳过列表——用户主动要看
  expect(shouldPromptUpdate("2.11.0", skipped, { manual: true })).toBe(true);
  // 新版本照常提示
  expect(shouldPromptUpdate("2.12.0", skipped, { manual: false })).toBe(true);
  expect(shouldPromptUpdate(null, skipped, { manual: false })).toBe(false);
});
