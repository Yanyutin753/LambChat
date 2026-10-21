import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  routes: [] as Array<(...args: unknown[]) => unknown>,
  handle: vi.fn(),
  matchPrecache: vi.fn(),
  cacheMatch: vi.fn(),
  navigationOptions: {} as {
    plugins: Array<{
      fetchDidSucceed?: (options: { response: Response }) => Promise<Response>;
    }>;
  },
}));

vi.mock("workbox-cacheable-response", () => ({
  CacheableResponsePlugin: class {},
}));
vi.mock("workbox-core", () => ({ clientsClaim: vi.fn() }));
vi.mock("workbox-expiration", () => ({ ExpirationPlugin: class {} }));
vi.mock("workbox-precaching", () => ({
  cleanupOutdatedCaches: vi.fn(),
  precacheAndRoute: vi.fn(),
  matchPrecache: mocks.matchPrecache,
}));
vi.mock("workbox-routing", () => ({
  registerRoute: (_match: unknown, handler: (...args: unknown[]) => unknown) =>
    mocks.routes.push(handler),
}));
vi.mock("workbox-strategies", () => ({
  NetworkFirst: class {
    constructor(options: typeof mocks.navigationOptions) {
      mocks.navigationOptions = options;
    }
    handle = mocks.handle;
  },
  CacheFirst: class {},
  StaleWhileRevalidate: class {},
}));

beforeEach(async () => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.routes.length = 0;
  mocks.matchPrecache.mockResolvedValue(undefined);
  mocks.cacheMatch.mockResolvedValue(undefined);
  vi.stubGlobal("self", {
    addEventListener: vi.fn(),
    location: { origin: "https://lambchat.com" },
    __WB_MANIFEST: [],
  });
  vi.stubGlobal("caches", { match: mocks.cacheMatch });
  await import("../sw");
});

test("a deployment connection failure opens the precached app shell before the offline page", async () => {
  mocks.handle.mockRejectedValue(new TypeError("network changed"));
  const shell = new Response("<html>chat shell</html>");
  mocks.matchPrecache.mockImplementation(async (url: string) =>
    url === "/index.html" ? shell : new Response("offline"),
  );
  const response = (await mocks.routes[0]({})) as Response;
  expect(await response.text()).toContain("chat shell");
  expect(mocks.matchPrecache).toHaveBeenCalledWith("/index.html");
});

test("the offline page remains available when the app shell is unavailable", async () => {
  mocks.handle.mockRejectedValue(new TypeError("offline"));
  mocks.matchPrecache.mockImplementation(async (url: string) =>
    url === "/offline.html" ? new Response("offline page") : undefined,
  );
  expect(await ((await mocks.routes[0]({})) as Response).text()).toBe(
    "offline page",
  );
});

test.each([502, 503, 504])(
  "deployment HTTP %s enters the app shell fallback instead of replacing the app",
  async (status) => {
    const plugin = mocks.navigationOptions.plugins.find(
      (p) => p.fetchDidSucceed,
    );
    expect(plugin).toBeDefined();
    await expect(
      plugin!.fetchDidSucceed!({
        response: new Response("upstream unavailable", { status }),
      }),
    ).rejects.toThrow();
  },
);

test("navigation keeps real auth and not-found responses", async () => {
  const plugin = mocks.navigationOptions.plugins.find((p) => p.fetchDidSucceed);
  expect(plugin).toBeDefined();
  for (const status of [200, 401, 403, 404]) {
    const response = new Response("response", { status });
    expect(await plugin!.fetchDidSucceed!({ response })).toBe(response);
  }
});
