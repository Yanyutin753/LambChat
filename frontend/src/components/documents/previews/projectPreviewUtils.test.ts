import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSandpackConfig,
  resolveEntryFile,
  resolveSandpackTemplate,
} from "./projectPreviewUtils.ts";

test("uses react template for Vite-style React projects with index.html and main.jsx", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/index.html": '<script type="module" src="/src/main.jsx"></script>',
    "/src/main.jsx": "import React from 'react';",
  });

  assert.equal(template, "react");
});

test("uses react template for Vite-style React projects with index.html and main.tsx", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/index.html": '<script type="module" src="/src/main.tsx"></script>',
    "/src/main.tsx": "import React from 'react';",
  });

  assert.equal(template, "react");
});

test("keeps static template for plain static sites", () => {
  const template = resolveSandpackTemplate("static", {
    "/index.html": "<h1>Hello</h1>",
    "/styles.css": "body { color: red; }",
  });

  assert.equal(template, "static");
});

test("uses src main tsx as default entry when no explicit entry is provided", () => {
  const entry = resolveEntryFile({
    "/src/main.tsx": "import React from 'react';",
    "/src/App.tsx": "export default function App() { return null; }",
  });

  assert.equal(entry, "/src/main.tsx");
});

test("normalizes explicit entry paths", () => {
  const entry = resolveEntryFile(
    {
      "/src/main.jsx": "import React from 'react';",
    },
    "src/main.jsx",
  );

  assert.equal(entry, "/src/main.jsx");
});

test("uses svelte template when App.svelte is present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/src/App.svelte": "<script>let count = 0;</script>",
    "/src/main.js": "import App from './App.svelte';",
  });

  assert.equal(template, "svelte");
});

test("uses solid template when solid entry files are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/src/index.tsx": "import { render } from 'solid-js/web';",
    "/src/App.tsx": "export default function App() { return <div />; }",
  });

  assert.equal(template, "solid");
});

test("uses nextjs template when next pages router files are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/pages/index.tsx": "export default function Page() { return <main />; }",
    "/pages/_app.tsx":
      "export default function App({ Component, pageProps }) { return <Component {...pageProps} />; }",
  });

  assert.equal(template, "nextjs");
});

test("uses angular template when angular config and main entry are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/angular.json": "{}",
    "/src/main.ts": "bootstrapApplication(AppComponent);",
  });

  assert.equal(template, "angular");
});

test("uses svelte main js as default entry when available", () => {
  const entry = resolveEntryFile({
    "/src/main.js": "import App from './App.svelte';",
    "/src/App.svelte": "<script></script>",
  });

  assert.equal(entry, "/src/main.js");
});

test("uses nextjs pages index as default entry when available", () => {
  const entry = resolveEntryFile({
    "/pages/index.tsx": "export default function Page() { return null; }",
    "/pages/_app.tsx":
      "export default function App({ Component, pageProps }) { return <Component {...pageProps} />; }",
  });

  assert.equal(entry, "/pages/index.tsx");
});

test("keeps Vue template default bundler entry when only App.vue is provided", () => {
  const config = buildSandpackConfig("vanilla", {
    "/src/App.vue": "<template><div>Hello</div></template>",
  });

  assert.equal(config.template, "vue");
  assert.equal(config.entryFile, "/src/App.vue");
  assert.deepEqual(config.customSetup, {});
});

test("uses vue-ts template when Vue project includes TypeScript entry", () => {
  const config = buildSandpackConfig("vanilla", {
    "/src/App.vue":
      "<template><div>Hello</div></template><script setup lang=\"ts\">const msg: string = 'hi'</script>",
    "/src/main.ts": "import { createApp } from 'vue';",
  });

  assert.equal(config.template, "vue-ts");
  assert.deepEqual(config.customSetup, { entry: "/src/main.ts" });
});

test("uses vue template for Vite-based Vue projects to avoid Sandpack node runtime issues", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from './App.vue'; createApp(App).mount('#app');",
    "/src/App.vue": "<template><div>Hello</div></template>",
    "/vite.config.js":
      "import { defineConfig } from 'vite'; import vue from '@vitejs/plugin-vue'; export default defineConfig({ plugins: [vue()] });",
    "/package.json": '{"dependencies":{"vue":"^3.4.0"}}',
  });

  assert.equal(config.template, "vue");
  assert.deepEqual(config.customSetup, { entry: "/src/main.js" });
});

test("preserves required Vue runtime deps when user package.json overrides template package", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from './App.vue'; createApp(App).mount('#app');",
    "/src/App.vue": "<template><div>Hello</div></template>",
    "/vite.config.js":
      "import { defineConfig } from 'vite'; import vue from '@vitejs/plugin-vue'; export default defineConfig({ plugins: [vue()] });",
    "/package.json": JSON.stringify({
      name: "vue-blog",
      dependencies: { vue: "^3.4.0" },
    }),
  });

  const packageJson = JSON.parse(config.files["/package.json"]);

  assert.equal(packageJson.name, "vue-blog");
  assert.equal(packageJson.dependencies.vue, "^3.4.0");
  assert.equal(packageJson.dependencies["core-js"], "^3.26.1");
  assert.equal(packageJson.devDependencies["@vue/cli-service"], "^5.0.8");
  assert.equal(packageJson.devDependencies["@vue/cli-plugin-babel"], "^5.0.8");
});

test("does not rely on Rollup WASM fallbacks for Vite-based Vue previews", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from './App.vue'; createApp(App).mount('#app');",
    "/src/App.vue": "<template><div>Hello</div></template>",
    "/vite.config.js":
      "import { defineConfig } from 'vite'; import vue from '@vitejs/plugin-vue'; export default defineConfig({ plugins: [vue()] });",
    "/package.json": JSON.stringify({
      name: "vue-blog",
      dependencies: { vue: "^3.4.0" },
      devDependencies: { vite: "^5.4.9", "@vitejs/plugin-vue": "^5.1.4" },
    }),
  });

  const packageJson = JSON.parse(config.files["/package.json"]);

  assert.equal(config.template, "vue");
  assert.equal(packageJson.devDependencies["@rollup/wasm-node"], undefined);
  assert.equal(packageJson.devDependencies.rollup, undefined);
  assert.equal(packageJson.overrides, undefined);
  assert.equal(config.files["/node_modules/rollup/dist/native.js"], undefined);
});

test("injects a patched vfile entry that uses browser shims instead of package imports", () => {
  const config = buildSandpackConfig("static", {
    "/index.html": "<h1>Hello</h1>",
  });

  const vfileIndex = config.files["/node_modules/vfile/lib/index.js"];

  assert.ok(vfileIndex);
  assert.match(vfileIndex, /from 'vfile-message'/);
  assert.match(vfileIndex, /from '\.\/minpath\.browser\.js'/);
  assert.match(vfileIndex, /from '\.\/minproc\.browser\.js'/);
  assert.match(vfileIndex, /from '\.\/minurl\.browser\.js'/);
  assert.doesNotMatch(vfileIndex, /#minpath|#minproc|#minurl/);
});
