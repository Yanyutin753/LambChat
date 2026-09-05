import { gzipSync } from "node:zlib";
import { describe, expect, test } from "vitest";
import {
  collectRouteShellUrls,
  combinePrecacheBudgetEntries,
  createPerformanceManifestTransform,
  extractEagerJavaScriptUrls,
  filterPrecacheEntries,
  sumGzipBytes,
  sumRawBytes,
} from "../../scripts/performanceBudget";

describe("frontend performance budgets", () => {
  test("extracts and deduplicates the module entry and modulepreloads", () => {
    const html = `
      <script type="module" src="/assets/index.js"></script>
      <link rel="modulepreload" href="/assets/vendor.js">
      <link rel="modulepreload" href="/assets/vendor.js">
    `;

    expect(extractEagerJavaScriptUrls(html)).toEqual([
      "assets/index.js",
      "assets/vendor.js",
    ]);
  });

  test("collects static closure and one level of route shells only", () => {
    const manifest = {
      "index.html": {
        file: "assets/index.js",
        isEntry: true,
        imports: ["vendor"],
        dynamicImports: ["app", "auth"],
        css: ["assets/index.css"],
      },
      vendor: { file: "assets/vendor.js" },
      app: {
        file: "assets/app.js",
        imports: ["chat-static"],
        dynamicImports: ["mermaid"],
      },
      "chat-static": { file: "assets/chat-static.js" },
      auth: { file: "assets/auth.js" },
      mermaid: { file: "assets/mermaid.js" },
    };

    expect(collectRouteShellUrls(manifest, "index.html")).toEqual(
      new Set([
        "assets/index.js",
        "assets/index.css",
        "assets/vendor.js",
        "assets/app.js",
        "assets/chat-static.js",
        "assets/auth.js",
      ]),
    );
  });

  test("rejects missing manifest entries", () => {
    expect(() => collectRouteShellUrls({}, "index.html")).toThrow(
      "missing Vite manifest entry",
    );
    expect(() =>
      collectRouteShellUrls(
        {
          "index.html": {
            file: "assets/index.js",
            imports: ["missing"],
          },
        },
        "index.html",
      ),
    ).toThrow("missing Vite manifest entry");
  });

  test("filters Workbox entries and budgets configured additions once", () => {
    const filtered = filterPrecacheEntries(
      [
        { url: "assets/index.js", revision: null },
        { url: "assets/index.js", revision: "duplicate" },
        { url: "assets/mermaid.js", revision: null },
        { url: "index.html", revision: "a" },
      ],
      new Set(["assets/index.js", "index.html"]),
    );

    expect(filtered.map((entry) => entry.url)).toEqual([
      "assets/index.js",
      "index.html",
    ]);
    expect(
      combinePrecacheBudgetEntries(filtered, [
        { url: "offline.html", revision: "b" },
      ]).map((entry) => entry.url),
    ).toEqual(["assets/index.js", "index.html", "offline.html"]);
  });

  test("sums unique raw and level-nine gzip bytes", () => {
    const assets = new Map([
      ["assets/a.js", Buffer.from("alpha")],
      ["assets/b.js", Buffer.from("beta beta beta")],
    ]);
    const read = (url: string) => {
      const value = assets.get(url);
      if (!value) throw new Error(`missing asset: ${url}`);
      return value;
    };

    expect(
      sumRawBytes(["assets/a.js", "/assets/a.js", "assets/b.js"], read),
    ).toBe(
      assets.get("assets/a.js")!.byteLength +
        assets.get("assets/b.js")!.byteLength,
    );
    expect(sumGzipBytes(["assets/a.js"], read)).toBe(
      gzipSync(assets.get("assets/a.js")!, { level: 9 }).byteLength,
    );
  });

  test.each(["../secret", "assets/../../secret", "/../secret", "", "."])(
    "rejects unsafe artifact URL %j",
    (url) => {
      expect(() => sumRawBytes([url], () => Buffer.alloc(0))).toThrow(
        "unsafe artifact URL",
      );
    },
  );

  test("fails when an artifact is missing", () => {
    expect(() =>
      sumRawBytes(["assets/missing.js"], (url) => {
        throw new Error(`missing asset: ${url}`);
      }),
    ).toThrow("missing asset: assets/missing.js");
  });

  test("filters to the eager graph, route shells, offline shell, and icons", async () => {
    const files = new Map<string, Buffer>([
      [
        "/dist/index.html",
        Buffer.from(
          '<script type="module" src="/assets/index.js"></script><link rel="modulepreload" href="/assets/vendor.js">',
        ),
      ],
      [
        "/dist/.vite/manifest.json",
        Buffer.from(
          JSON.stringify({
            "src/main.tsx": {
              file: "assets/index.js",
              isEntry: true,
              imports: ["vendor"],
              dynamicImports: ["app"],
              assets: ["assets/font.woff2"],
            },
            vendor: { file: "assets/vendor.js" },
            app: {
              file: "assets/app.js",
              dynamicImports: ["mermaid"],
            },
            mermaid: { file: "assets/mermaid.js" },
          }),
        ),
      ],
      ["/dist/assets/index.js", Buffer.from("entry")],
      ["/dist/assets/vendor.js", Buffer.from("vendor")],
      ["/dist/assets/app.js", Buffer.from("app")],
      ["/dist/assets/mermaid.js", Buffer.from("mermaid")],
      ["/dist/assets/font.woff2", Buffer.from("font")],
      ["/dist/offline.html", Buffer.from("offline")],
      [
        "/dist/manifest.json",
        Buffer.from(
          JSON.stringify({
            icons: [{ src: "/icons/icon-192.png" }],
            shortcuts: [{ icons: [{ src: "/icons/icon-192.png" }] }],
          }),
        ),
      ],
      ["/dist/favicon.ico", Buffer.from("icon")],
      ["/dist/icons/icon-192.png", Buffer.from("pwa icon")],
      ["/dist/icons/og-image.png", Buffer.from("social image")],
    ]);
    const logs: string[] = [];
    const readBytes = (filePath: string) => {
      const value = files.get(filePath);
      if (!value) throw new Error(`missing test file: ${filePath}`);
      return value;
    };
    files.set(
      "/dist/index.html",
      Buffer.from(
        '<script type="module" src="/assets/index.js"></script><link rel="modulepreload" href="/assets/vendor.js">',
      ),
    );

    const transform = createPerformanceManifestTransform({
      distDir: "/dist",
      readText: (filePath) => readBytes(filePath).toString("utf8"),
      readBytes,
      log: (message) => logs.push(message),
    });
    const result = await transform([
      { url: "assets/index.js", revision: null, size: 5 },
      { url: "assets/vendor.js", revision: null, size: 6 },
      { url: "assets/app.js", revision: null, size: 3 },
      { url: "assets/mermaid.js", revision: null, size: 7 },
      { url: "assets/font.woff2", revision: null, size: 4 },
      { url: "index.html", revision: "html", size: 100 },
      { url: "offline.html", revision: "offline", size: 7 },
      { url: "manifest.json", revision: "manifest", size: 8 },
      { url: "favicon.ico", revision: "favicon", size: 4 },
      { url: "icons/icon-192.png", revision: "icon", size: 8 },
      { url: "icons/og-image.png", revision: "social", size: 12 },
    ]);

    expect(result.manifest.map((entry) => entry.url)).toEqual([
      "assets/index.js",
      "assets/vendor.js",
      "assets/app.js",
      "index.html",
      "offline.html",
      "manifest.json",
      "favicon.ico",
      "icons/icon-192.png",
    ]);
    expect(result.warnings).toEqual([]);
    expect(logs).toHaveLength(1);
    expect(logs[0]).toMatch(/eager JavaScript: \d+\/514048 bytes/);
    expect(logs[0]).toMatch(/precache: 8 entries, \d+\/5242880 bytes/);
  });

  test("fails deterministic eager and precache budgets", async () => {
    const deterministicNoise = (length: number) => {
      const value = Buffer.allocUnsafe(length);
      let state = 0x12345678;
      for (let index = 0; index < length; index += 1) {
        state ^= state << 13;
        state ^= state >>> 17;
        state ^= state << 5;
        value[index] = state & 0xff;
      }
      return value;
    };
    const baseFiles = new Map<string, Buffer>([
      [
        "/dist/index.html",
        Buffer.from('<script type="module" src="/assets/index.js"></script>'),
      ],
      [
        "/dist/.vite/manifest.json",
        Buffer.from(
          JSON.stringify({
            "index.html": { file: "assets/index.js", isEntry: true },
          }),
        ),
      ],
      ["/dist/assets/index.js", Buffer.from("entry")],
      ["/dist/manifest.json", Buffer.from('{"icons":[]}')],
    ]);
    const makeTransform = (readBytes: (filePath: string) => Uint8Array) =>
      createPerformanceManifestTransform({
        distDir: "/dist",
        readText: (filePath) =>
          Buffer.from(readBytes(filePath)).toString("utf8"),
        readBytes,
        log: () => undefined,
      });

    await expect(
      makeTransform((filePath) =>
        filePath === "/dist/assets/index.js"
          ? deterministicNoise(600_000)
          : baseFiles.get(filePath)!,
      )([{ url: "assets/index.js", size: 600_000 }]),
    ).rejects.toThrow(/eager JavaScript budget exceeded: \d+ > 514048 bytes/);

    await expect(
      makeTransform((filePath) =>
        filePath === "/dist/assets/index.js"
          ? Buffer.alloc(5 * 1024 * 1024 + 1, 0)
          : baseFiles.get(filePath)!,
      )([{ url: "assets/index.js", size: 5 * 1024 * 1024 + 1 }]),
    ).rejects.toThrow(/precache budget exceeded: 5242881 > 5242880 bytes/);
  });
});
