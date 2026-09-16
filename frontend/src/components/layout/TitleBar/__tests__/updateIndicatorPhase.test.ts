import { expect, test } from "vitest";

import { updateIndicatorPhase } from "../updateIndicatorPhase";
import type { UpdateState } from "../../../types";

function makeState(overrides: Partial<UpdateState> = {}): UpdateState {
  return {
    available: true,
    version: "99.0.0",
    releaseNotes: null,
    releaseUrl: null,
    releaseAssets: [],
    publishedAt: null,
    downloading: false,
    progress: 0,
    contentLength: 0,
    downloaded: 0,
    readyToInstall: false,
    error: null,
    linuxInstallSource: null,
    ...overrides,
  };
}

test("downloading takes precedence for the live progress phase", () => {
  expect(updateIndicatorPhase(makeState({ downloading: true }))).toBe(
    "downloading",
  );
  // 下载中即使残留 ready/error 字段也以进行中的下载为准
  expect(
    updateIndicatorPhase(
      makeState({ downloading: true, readyToInstall: true }),
    ),
  ).toBe("downloading");
});

test("ready-to-install outranks a stale error message", () => {
  expect(
    updateIndicatorPhase(
      makeState({ readyToInstall: true, error: "old failure" }),
    ),
  ).toBe("ready");
});

test("error and plain-available phases map directly", () => {
  expect(updateIndicatorPhase(makeState({ error: "boom" }))).toBe("error");
  expect(updateIndicatorPhase(makeState())).toBe("available");
});
