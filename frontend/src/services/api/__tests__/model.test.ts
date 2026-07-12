import { modelApi } from "../model.ts";

test("modelApi.list reuses in-flight and fresh identical list requests", async () => {
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
    location: { pathname: "/settings", search: "" },
  } as unknown as Window & typeof globalThis;
  globalThis.fetch = async () => {
    fetchCount += 1;
    return new Response(JSON.stringify({ models: [] }), { status: 200 });
  };

  try {
    const [first, second] = await Promise.all([
      modelApi.list(true),
      modelApi.list(true),
    ]);
    const third = await modelApi.list(true);

    expect(fetchCount).toBe(1);
    expect(first).toEqual({ models: [] });
    expect(second).toEqual({ models: [] });
    expect(third).toEqual({ models: [] });
  } finally {
    globalThis.fetch = previousFetch;
    globalThis.localStorage = previousLocalStorage;
    globalThis.window = previousWindow;
  }
});
