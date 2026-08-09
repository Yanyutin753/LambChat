import { gzipSync } from "node:zlib";
import { describe, expect, test } from "vitest";
import {
  collectRouteShellUrls,
  combinePrecacheBudgetEntries,
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
});
