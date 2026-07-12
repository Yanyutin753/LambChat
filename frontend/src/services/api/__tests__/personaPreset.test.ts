import {
  buildPersonaPresetListUrl,
  buildPersonaPresetPreferenceUrl,
  personaPresetApi,
} from "../personaPreset.ts";

test("buildPersonaPresetPreferenceUrl encodes preset ids", () => {
  expect(buildPersonaPresetPreferenceUrl("preset/1")).toBe(
    "/api/persona-presets/preset%2F1/preference",
  );
});

test("buildPersonaPresetListUrl keeps page-sized pagination params", () => {
  expect(buildPersonaPresetListUrl({ skip: 12, limit: 12, q: "planner" })).toBe(
    "/api/persona-presets/?q=planner&skip=12&limit=12",
  );
});

test("personaPresetApi.list reuses in-flight and fresh identical list requests", async () => {
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
        presets: [],
        total: 0,
        skip: 0,
        limit: 20,
      }),
      { status: 200 },
    );
  };

  try {
    const params = { skip: 0, limit: 20 };
    const [first, second] = await Promise.all([
      personaPresetApi.list(params),
      personaPresetApi.list(params),
    ]);
    const third = await personaPresetApi.list(params);

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
