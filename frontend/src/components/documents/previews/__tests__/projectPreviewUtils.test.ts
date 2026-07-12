import {
  buildSandpackConfig,
  resolveProjectPreviewLayout,
  resolveEntryFile,
  resolveSandpackTemplate,
} from "../projectPreviewUtils.ts";

test("uses react template for Vite-style React projects with index.html and main.jsx", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/index.html": '<script type="module" src="/src/main.jsx"></script>',
    "/src/main.jsx": "import React from 'react';",
  });

  expect(template).toBe("react");
});

test("uses react template for Vite-style React projects with index.html and main.tsx", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/index.html": '<script type="module" src="/src/main.tsx"></script>',
    "/src/main.tsx": "import React from 'react';",
  });

  expect(template).toBe("react");
});

test("keeps static template for plain static sites", () => {
  const template = resolveSandpackTemplate("static", {
    "/index.html": "<h1>Hello</h1>",
    "/styles.css": "body { color: red; }",
  });

  expect(template).toBe("static");
});

test("uses src main tsx as default entry when no explicit entry is provided", () => {
  const entry = resolveEntryFile({
    "/src/main.tsx": "import React from 'react';",
    "/src/App.tsx": "export default function App() { return null; }",
  });

  expect(entry).toBe("/src/main.tsx");
});

test("normalizes explicit entry paths", () => {
  const entry = resolveEntryFile(
    {
      "/src/main.jsx": "import React from 'react';",
    },
    "src/main.jsx",
  );

  expect(entry).toBe("/src/main.jsx");
});

test("uses svelte template when App.svelte is present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/src/App.svelte": "<script>let count = 0;</script>",
    "/src/main.js": "import App from '../App.svelte';",
  });

  expect(template).toBe("svelte");
});

test("uses solid template when solid entry files are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/src/index.tsx": "import { render } from 'solid-js/web';",
    "/src/App.tsx": "export default function App() { return <div />; }",
  });

  expect(template).toBe("solid");
});

test("uses nextjs template when next pages router files are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/pages/index.tsx": "export default function Page() { return <main />; }",
    "/pages/_app.tsx":
      "export default function App({ Component, pageProps }) { return <Component {...pageProps} />; }",
  });

  expect(template).toBe("nextjs");
});

test("uses angular template when angular config and main entry are present", () => {
  const template = resolveSandpackTemplate("vanilla", {
    "/angular.json": "{}",
    "/src/main.ts": "bootstrapApplication(AppComponent);",
  });

  expect(template).toBe("angular");
});

test("uses svelte main js as default entry when available", () => {
  const entry = resolveEntryFile({
    "/src/main.js": "import App from '../App.svelte';",
    "/src/App.svelte": "<script></script>",
  });

  expect(entry).toBe("/src/main.js");
});

test("uses nextjs pages index as default entry when available", () => {
  const entry = resolveEntryFile({
    "/pages/index.tsx": "export default function Page() { return null; }",
    "/pages/_app.tsx":
      "export default function App({ Component, pageProps }) { return <Component {...pageProps} />; }",
  });

  expect(entry).toBe("/pages/index.tsx");
});

test("keeps Vue template default bundler entry when only App.vue is provided", () => {
  const config = buildSandpackConfig("vanilla", {
    "/src/App.vue": "<template><div>Hello</div></template>",
  });

  expect(config.template).toBe("vue");
  expect(config.entryFile).toBe("/src/App.vue");
  expect(config.customSetup).toEqual({});
});

test("uses vue-ts template when Vue project includes TypeScript entry", () => {
  const config = buildSandpackConfig("vanilla", {
    "/src/App.vue":
      "<template><div>Hello</div></template><script setup lang=\"ts\">const msg: string = 'hi'</script>",
    "/src/main.ts": "import { createApp } from 'vue';",
  });

  expect(config.template).toBe("vue-ts");
  expect(config.customSetup).toEqual({ entry: "/src/main.ts" });
});

test("uses vue template for Vite-based Vue projects to avoid Sandpack node runtime issues", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from '../App.vue'; createApp(App).mount('#app');",
    "/src/App.vue": "<template><div>Hello</div></template>",
    "/vite.config.js":
      "import { defineConfig } from 'vite'; import vue from '@vitejs/plugin-vue'; export default defineConfig({ plugins: [vue()] });",
    "/package.json": '{"dependencies":{"vue":"^3.4.0"}}',
  });

  expect(config.template).toBe("vue");
  expect(config.customSetup).toEqual({ entry: "/src/main.js" });
});

test("preserves required Vue runtime deps when user package.json overrides template package", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from '../App.vue'; createApp(App).mount('#app');",
    "/src/App.vue": "<template><div>Hello</div></template>",
    "/vite.config.js":
      "import { defineConfig } from 'vite'; import vue from '@vitejs/plugin-vue'; export default defineConfig({ plugins: [vue()] });",
    "/package.json": JSON.stringify({
      name: "vue-blog",
      dependencies: { vue: "^3.4.0" },
    }),
  });

  const packageJson = JSON.parse(config.files["/package.json"]);

  expect(packageJson.name).toBe("vue-blog");
  expect(packageJson.dependencies.vue).toBe("^3.4.0");
  expect(packageJson.dependencies["core-js"]).toBe("^3.26.1");
  expect(packageJson.devDependencies["@vue/cli-service"]).toBe("^5.0.8");
  expect(packageJson.devDependencies["@vue/cli-plugin-babel"]).toBe("^5.0.8");
});

test("does not rely on Rollup WASM fallbacks for Vite-based Vue previews", () => {
  const config = buildSandpackConfig("vanilla", {
    "/index.html":
      '<!doctype html><html><body><div id="app"></div><script type="module" src="/src/main.js"></script></body></html>',
    "/src/main.js":
      "import { createApp } from 'vue'; import App from '../App.vue'; createApp(App).mount('#app');",
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

  expect(config.template).toBe("vue");
  expect(packageJson.devDependencies["@rollup/wasm-node"]).toBe(undefined);
  expect(packageJson.devDependencies.rollup).toBe(undefined);
  expect(packageJson.overrides).toBe(undefined);
  expect(config.files["/node_modules/rollup/dist/native.js"]).toBe(undefined);
});

test("injects a patched vfile entry that uses browser shims instead of package imports", () => {
  const config = buildSandpackConfig("static", {
    "/index.html": "<h1>Hello</h1>",
  });

  const vfileIndex = config.files["/node_modules/vfile/lib/index.js"];

  expect(vfileIndex).toBeTruthy();
  expect(vfileIndex).toMatch(/from 'vfile-message'/);
  expect(vfileIndex).toMatch(/from '\.\/minpath\.browser\.js'/);
  expect(vfileIndex).toMatch(/from '\.\/minproc\.browser\.js'/);
  expect(vfileIndex).toMatch(/from '\.\/minurl\.browser\.js'/);
  expect(vfileIndex).not.toMatch(/#minpath|#minproc|#minurl/);
});

test("uses code-first layout for folder previews", () => {
  const layout = resolveProjectPreviewLayout("folder");

  expect(layout).toEqual({
    initialTab: "code",
    showExplorer: true,
    showPreview: false,
  });
});

test("keeps preview-first layout for runnable project previews", () => {
  const layout = resolveProjectPreviewLayout("project");

  expect(layout).toEqual({
    initialTab: "preview",
    showExplorer: false,
    showPreview: true,
  });
});
