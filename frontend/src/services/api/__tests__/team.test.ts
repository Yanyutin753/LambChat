import {
  buildTeamCloneUrl,
  buildTeamCollectionUrl,
  buildTeamItemUrl,
  buildTeamPreferenceUrl,
  teamApi,
} from "../team.ts";

test("buildTeamCollectionUrl uses the backend collection route", () => {
  expect(buildTeamCollectionUrl()).toBe("/api/teams/");
});

test("buildTeamCollectionUrl includes pagination params", () => {
  expect(buildTeamCollectionUrl(10, 25)).toBe("/api/teams/?skip=10&limit=25");
});

test("buildTeamCollectionUrl includes filters", () => {
  expect(
    buildTeamCollectionUrl({
      skip: 10,
      limit: 25,
      q: "research",
      tag: "analysis",
      pinned: true,
    }),
  ).toBe("/api/teams/?skip=10&limit=25&q=research&tag=analysis&pinned=true");
});

test("buildTeamItemUrl encodes team ids", () => {
  expect(buildTeamItemUrl("team/1")).toBe("/api/teams/team%2F1");
});

test("buildTeamCloneUrl encodes team ids", () => {
  expect(buildTeamCloneUrl("team/1")).toBe("/api/teams/team%2F1/clone");
});

test("buildTeamPreferenceUrl matches the backend preference route", () => {
  expect(buildTeamPreferenceUrl("team/1")).toBe(
    "/api/teams/team%2F1/preference",
  );
});

test("teamApi.list reuses in-flight and fresh identical list requests", async () => {
  const previousFetch = globalThis.fetch;
  const previousLocalStorage = globalThis.localStorage;
  const previousWindow = globalThis.window;
  let fetchCount = 0;

  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  } as unknown as Storage;
  globalThis.window = {
    dispatchEvent: () => true,
    location: { pathname: "/chat", search: "" },
  } as unknown as Window & typeof globalThis;
  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(
      JSON.stringify({
        teams: [],
        total: 0,
        skip: 0,
        limit: 50,
      }),
      { status: 200 },
    );
  };

  try {
    const [first, second] = await Promise.all([
      teamApi.list(0, 50),
      teamApi.list(0, 50),
    ]);
    const third = await teamApi.list(0, 50);

    expect(fetchCount).toBe(1);
    expect(first.total).toBe(0);
    expect(second.total).toBe(0);
    expect(third.total).toBe(0);
  } finally {
    globalThis.fetch = previousFetch;
    globalThis.localStorage = previousLocalStorage;
    globalThis.window = previousWindow;
  }
});
