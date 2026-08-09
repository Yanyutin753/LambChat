# Frontend Bundle and PWA Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the cross-chunk cycle, keep optional heavy features lazy, and reduce deterministic eager-JavaScript and PWA-precache budgets without weakening offline navigation.

**Architecture:** Extract pure artifact-budget and Vite-manifest graph helpers into a Node-only frontend script tested by Vitest. Use the Vite manifest to retain the eager graph and first-level route shells in Workbox precache while nested optional feature chunks use the existing runtime cache, and remove manual chunking that promotes Mermaid into the eager preload graph.

**Tech Stack:** React 19, TypeScript, Vite 6, Rollup, Vitest, vite-plugin-pwa, Workbox, Node zlib

---

## File structure

- Create `frontend/scripts/performanceBudget.ts`: Node-only pure helpers for eager HTML assets, Vite route-shell graph traversal, gzip totals, manifest filtering, and byte budgets.
- Create `frontend/src/__tests__/performanceBudget.test.ts`: deterministic helper tests with synthetic HTML/manifests and in-memory file readers.
- Modify `frontend/vite.config.ts`: enable Vite manifest, filter Workbox precache through the helpers, enforce budgets, and stop manually promoting Mermaid.
- Modify `frontend/src/__tests__/serviceWorkerSource.test.ts`: source guard for app-shell filtering and unchanged Workbox runtime behavior.
- Create `frontend/src/__tests__/vitePerformanceConfigSource.test.ts`: source guards for manifest/budget integration and Mermaid chunk configuration.
- Modify `frontend/src/components/layout/AppContent/useMessageScroll.externalNavigation.ts`: direct import that removes the barrel cycle.
- Modify `frontend/src/components/chat/ChatMessage/__tests__/subagentBlocks.test.ts`: retain barrel behavior for public consumers.
- Create `frontend/src/components/layout/AppContent/__tests__/externalNavigationImports.test.ts`: direct-import regression guard.
- Modify `docs/performance-audit-2026-08-09.md`: before/after artifact evidence and dispositions.

## Task 1: Build deterministic artifact-budget helpers

**Files:**
- Create: `frontend/scripts/performanceBudget.ts`
- Create: `frontend/src/__tests__/performanceBudget.test.ts`

- [ ] **Step 1: Write failing helper tests**

Add synthetic fixtures and these behaviors:

```typescript
import {
  collectRouteShellUrls,
  combinePrecacheBudgetEntries,
  extractEagerJavaScriptUrls,
  filterPrecacheEntries,
  sumGzipBytes,
  sumRawBytes,
} from "../../scripts/performanceBudget";

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

test("filters Workbox entries and budgets configured additions once", () => {
  const filtered = filterPrecacheEntries(
    [
      { url: "assets/index.js", revision: null },
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
  ).toEqual([
    "assets/index.js",
    "index.html",
    "offline.html",
  ]);
});
```

Add tests that `sumRawBytes` deduplicates URLs, rejects `..`/absolute filesystem escapes, and fails on a missing file. Test `sumGzipBytes` against `gzipSync(Buffer.from(value), { level: 9 }).byteLength`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/__tests__/performanceBudget.test.ts
```

Expected: FAIL because `scripts/performanceBudget.ts` does not exist.

- [ ] **Step 3: Implement the pure helper module**

Create these exported types and functions:

```typescript
import { gzipSync } from "node:zlib";
import { posix } from "node:path";

export interface ViteManifestChunk {
  file: string;
  isEntry?: boolean;
  imports?: string[];
  dynamicImports?: string[];
  css?: string[];
  assets?: string[];
}

export type ViteManifest = Record<string, ViteManifestChunk>;
export interface PrecacheEntry {
  url: string;
  revision?: string | null;
  integrity?: string;
}

export type ReadAsset = (url: string) => Uint8Array;

function normalizeUrl(value: string): string {
  const clean = value.split(/[?#]/, 1)[0].replace(/^\/+/, "");
  const normalized = posix.normalize(clean);
  if (!normalized || normalized === "." || normalized.startsWith("../")) {
    throw new Error(`unsafe artifact URL: ${value}`);
  }
  return normalized;
}
```

Implement `extractEagerJavaScriptUrls(html)` by matching module scripts and modulepreload links, normalizing URLs, retaining only `.js`/`.mjs`, and preserving first-seen order.

Implement `collectRouteShellUrls(manifest, entryKey)` with this traversal:

1. Add the entry's `file`, `css`, and `assets`.
2. Recursively add every `imports` dependency and its static dependencies.
3. For each first-level `dynamicImports` entry, add that chunk and its static `imports` closure.
4. Do not follow dynamic imports from a route shell.
5. Throw when the entry or a referenced manifest key is absent.

Implement exact budget functions:

```typescript
export function sumRawBytes(urls: Iterable<string>, read: ReadAsset): number {
  return [...new Set([...urls].map(normalizeUrl))].reduce(
    (total, url) => total + read(url).byteLength,
    0,
  );
}

export function sumGzipBytes(urls: Iterable<string>, read: ReadAsset): number {
  return [...new Set([...urls].map(normalizeUrl))].reduce(
    (total, url) => total + gzipSync(read(url), { level: 9 }).byteLength,
    0,
  );
}
```

Implement `filterPrecacheEntries(entries, allowedUrls)` by deduplicating and retaining only allowed
glob entries while preserving the original entry object. Implement
`combinePrecacheBudgetEntries(filtered, additionalEntries)` separately; it returns a deduplicated
union used only for byte/count calculation. The custom transform must return `filtered`, because
Workbox 7.4.1 applies its own `additionalManifestEntries` transform afterward and injects those
entries exactly once.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same Vitest command. Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/performanceBudget.ts frontend/src/__tests__/performanceBudget.test.ts
git commit -m "test: add deterministic frontend artifact budgets"
```

## Task 2: Remove the cross-chunk barrel cycle

**Files:**
- Create: `frontend/src/components/layout/AppContent/__tests__/externalNavigationImports.test.ts`
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.externalNavigation.ts`

- [ ] **Step 1: Write the failing source import test**

```typescript
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("external navigation imports the subagent opener from its defining module", () => {
  const source = readFileSync(
    resolve(
      import.meta.dirname,
      "../useMessageScroll.externalNavigation.ts",
    ),
    "utf8",
  );
  expect(source).toMatch(
    /from "\.\.\/\.\.\/chat\/ChatMessage\/SubagentBlock"/,
  );
  expect(source).not.toMatch(/ChatMessage\/SubagentBlocks/);
});
```

- [ ] **Step 2: Run test and verify RED**

```bash
cd frontend && pnpm exec vitest run \
  src/components/layout/AppContent/__tests__/externalNavigationImports.test.ts
```

Expected: FAIL because the source imports through `SubagentBlocks`.

- [ ] **Step 3: Make the direct import**

Change only:

```typescript
import { openSubagentPanelByAgentId } from "../../chat/ChatMessage/SubagentBlock";
```

Keep the barrel re-export so existing public imports and `subagentBlocks.test.ts` remain compatible.

- [ ] **Step 4: Run focused tests and verify GREEN**

```bash
cd frontend && pnpm exec vitest run \
  src/components/layout/AppContent/__tests__/externalNavigationImports.test.ts \
  src/components/chat/ChatMessage/__tests__/subagentBlocks.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  frontend/src/components/layout/AppContent/useMessageScroll.externalNavigation.ts \
  frontend/src/components/layout/AppContent/__tests__/externalNavigationImports.test.ts
git commit -m "perf: remove subagent navigation chunk cycle"
```

## Task 3: Integrate route-shell precaching and deterministic build budgets

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/__tests__/serviceWorkerSource.test.ts`
- Create: `frontend/src/__tests__/vitePerformanceConfigSource.test.ts`
- Modify: `frontend/scripts/performanceBudget.ts`
- Modify: `frontend/src/__tests__/performanceBudget.test.ts`

- [ ] **Step 1: Write failing Vite/PWA source guards**

Assert the Vite config:

```typescript
expect(source).toMatch(/manifest:\s*true/);
expect(source).toMatch(/manifestTransforms/);
expect(source).toMatch(/createPerformanceManifestTransform/);
expect(source).toMatch(/EAGER_JAVASCRIPT_BUDGET_BYTES/);
expect(source).toMatch(/PRECACHE_BUDGET_BYTES/);
expect(source).not.toMatch(/"vendor-mermaid":\s*\["mermaid"\]/);
```

Extend the service-worker source test only to preserve `precacheAndRoute(self.__WB_MANIFEST)`, `cleanupOutdatedCaches`, navigation `NetworkFirst`, and static `StaleWhileRevalidate`; filtering belongs to build configuration, not runtime service-worker code.

- [ ] **Step 2: Run source tests and verify RED**

```bash
cd frontend && pnpm exec vitest run \
  src/__tests__/vitePerformanceConfigSource.test.ts \
  src/__tests__/serviceWorkerSource.test.ts
```

Expected: the new config test FAILS because no performance transform exists.

- [ ] **Step 3: Add the Node integration helper**

In `performanceBudget.ts`, add:

```typescript
export const EAGER_JAVASCRIPT_BUDGET_BYTES = 500 * 1024;
export const PRECACHE_BUDGET_BYTES = 4 * 1024 * 1024;
export const PRECACHE_ADDITIONAL_ENTRIES: PrecacheEntry[] = [];

export interface PerformanceManifestTransformOptions {
  distDir: string;
  readText: (path: string) => string;
  readBytes: (path: string) => Uint8Array;
  log: (message: string) => void;
}
```

Implement `createPerformanceManifestTransform(options)` as an async Workbox manifest transform that:

1. Reads `dist/index.html` and `dist/.vite/manifest.json`.
2. Finds the single manifest entry with `isEntry === true` when `index.html` is not the key.
3. Builds the route-shell URL allowlist and adds `index.html`, `offline.html`, `manifest.json`, `favicon.ico`, and `icons/` manifest URLs.
4. Filters the provided Workbox entries, combines `PRECACHE_ADDITIONAL_ENTRIES` only in a separate budget list so future additions cannot bypass the budget, and returns only the filtered glob entries; Workbox injects configured additions afterward.
5. Computes eager gzip and precache raw bytes using safe `dist`-relative readers.
6. Throws a message containing the actual and budget byte counts when either budget is exceeded.
7. Logs one stable summary and returns `{ manifest: filteredEntries, warnings: [] }`.

Add pure integration tests with a temporary in-memory reader; do not write real `dist` files in unit tests.

- [ ] **Step 4: Wire the transform into Vite**

In `vite.config.ts`:

```typescript
import {
  createPerformanceManifestTransform,
  PRECACHE_ADDITIONAL_ENTRIES,
} from "./scripts/performanceBudget";
```

Set `build.manifest = true`. Under `injectManifest`, keep the current glob and maximum-size safety guard, add:

```typescript
additionalManifestEntries: PRECACHE_ADDITIONAL_ENTRIES,
manifestTransforms: [
  createPerformanceManifestTransform({
    distDir: path.resolve(__dirname, "dist"),
    readText: (filePath) => fs.readFileSync(filePath, "utf8"),
    readBytes: (filePath) => fs.readFileSync(filePath),
    log: (message) => console.info(message),
  }),
],
```

If the plugin types expose `manifestTransforms` at `injectManifest` but `additionalManifestEntries` at the PWA root, follow the installed type definitions while passing the same exported additions constant to both the plugin and helper. Do not duplicate the list.

- [ ] **Step 5: Remove only the Mermaid manual chunk override**

Delete:

```typescript
"vendor-mermaid": ["mermaid"],
```

Keep other manual chunks until measured evidence shows another override violates the approved budget. Mermaid already uses dynamic `import("mermaid")`; removing the override lets Rollup keep it outside the eager preload graph.

- [ ] **Step 6: Run helper and source tests and verify GREEN**

```bash
cd frontend && pnpm exec vitest run \
  src/__tests__/performanceBudget.test.ts \
  src/__tests__/vitePerformanceConfigSource.test.ts \
  src/__tests__/serviceWorkerSource.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run the production build as the integration test**

```bash
cd frontend && /usr/bin/time -v pnpm run build
```

Expected:

- exit 0;
- no SubagentBlock/SubagentBlocks circular-chunk warning;
- stable performance summary reports eager JavaScript at or below 512,000 bytes gzip;
- Workbox manifest is at or below 4,194,304 raw bytes;
- Mermaid is absent from `dist/index.html` modulepreloads;
- offline shell entries and first-level route chunks remain in the Workbox manifest.

If a target fails, inspect `dist/index.html` and `.vite/manifest.json`, add a failing synthetic graph test reproducing the unexpected edge, and make the smallest chunk/allowlist correction. Do not raise the approved budgets.

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/vite.config.ts \
  frontend/scripts/performanceBudget.ts \
  frontend/src/__tests__/performanceBudget.test.ts \
  frontend/src/__tests__/vitePerformanceConfigSource.test.ts \
  frontend/src/__tests__/serviceWorkerSource.test.ts
git commit -m "perf: budget frontend shell and PWA precache"
```

## Task 4: Verify offline/cache compatibility and record results

**Files:**
- Modify: `docs/performance-audit-2026-08-09.md`
- Verify: `frontend/src/sw.ts`
- Verify: `frontend/src/pwaRouting.ts`
- Verify: all files above

- [ ] **Step 1: Run all PWA and routing tests**

```bash
cd frontend && pnpm exec vitest run \
  src/__tests__/pwaGuards.test.ts \
  src/__tests__/pwaRouting.test.ts \
  src/__tests__/pwaStatus.test.ts \
  src/__tests__/pwaStatusSource.test.ts \
  src/__tests__/serviceWorkerSource.test.ts \
  src/__tests__/pwaNginxCache.test.ts
```

Expected: PASS; API/SSE requests remain outside runtime caches, navigation keeps offline fallback, and lazy static assets still use runtime `StaleWhileRevalidate`.

- [ ] **Step 2: Run full frontend verification**

```bash
(cd frontend && pnpm test)
(cd frontend && pnpm run lint)
(cd frontend && pnpm run build)
```

Expected: all exit 0 and budget integration still passes.

- [ ] **Step 3: Update the audit ledger with exact before/after evidence**

Record:

- eager gzip: baseline about 644 KiB and final exact bytes;
- precache: baseline 309 entries/18,153.33 KiB and final exact totals;
- circular warning removed;
- build wall time and peak RSS trend;
- preserved offline/runtime cache tests;
- any remaining large lazy chunks as `deferred` when they do not affect eager or precache budgets.

- [ ] **Step 4: Commit report update**

```bash
git add docs/performance-audit-2026-08-09.md
git commit -m "docs: record frontend performance results"
```
