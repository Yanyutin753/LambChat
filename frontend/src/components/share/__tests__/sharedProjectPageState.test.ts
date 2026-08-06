import { computeProjectHasMore } from "../sharedProjectPageState";
import type { SharedProjectContentResponse } from "../../../types";

function buildManifest(
  overrides: Partial<SharedProjectContentResponse> = {},
): SharedProjectContentResponse {
  return {
    share_scope: "project",
    share_type: "full",
    project: { id: "p1", name: "Project" },
    sessions: [],
    owner: { username: "owner" },
    visibility: "public",
    sessions_total: 0,
    ...overrides,
  };
}

test("returns false when manifest is null", () => {
  expect(computeProjectHasMore(null)).toBe(false);
});

test("uses explicit has_more=true even if all sessions are loaded", () => {
  const manifest = buildManifest({
    has_more: true,
    sessions_total: 2,
    sessions: [
      { id: "s1", name: "a" },
      { id: "s2", name: "b" },
    ],
  });
  expect(computeProjectHasMore(manifest)).toBe(true);
});

test("uses explicit has_more=false even if sessions look incomplete", () => {
  // 后端明确表示没有更多时，不走 length 兜底
  const manifest = buildManifest({
    has_more: false,
    sessions_total: 5,
    sessions: [{ id: "s1", name: "a" }],
  });
  expect(computeProjectHasMore(manifest)).toBe(false);
});

test("falls back to length comparison when has_more is missing", () => {
  const manifest = buildManifest({
    sessions_total: 5,
    sessions: [{ id: "s1", name: "a" }],
  });
  expect(computeProjectHasMore(manifest)).toBe(true);
});

test("returns false via fallback when all sessions already loaded", () => {
  const manifest = buildManifest({
    sessions_total: 2,
    sessions: [
      { id: "s1", name: "a" },
      { id: "s2", name: "b" },
    ],
  });
  expect(computeProjectHasMore(manifest)).toBe(false);
});

test("returns false via fallback when sessions_total is zero", () => {
  const manifest = buildManifest({
    sessions_total: 0,
    sessions: [],
  });
  expect(computeProjectHasMore(manifest)).toBe(false);
});
