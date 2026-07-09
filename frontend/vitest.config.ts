import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    // Default to node environment — most tests are pure-function / source-string tests.
    // Component tests that need DOM should add: // @vitest-environment jsdom
    environment: "node",
    include: ["src/**/__tests__/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/__tests__/**",
        "src/test-setup.ts",
        "src/sw.ts",
        "src/vite-env.d.ts",
        "src/**/*.d.ts",
      ],
    },
  },
  resolve: {
    alias: [
      {
        find: /^opentype\.js$/,
        replacement: path.resolve(
          __dirname,
          "node_modules/opentype.js/dist/opentype.js",
        ),
      },
      {
        find: /^stream$/,
        replacement: path.resolve(__dirname, "node_modules/stream-browserify"),
      },
      {
        find: /^events$/,
        replacement: path.resolve(__dirname, "node_modules/events"),
      },
      {
        find: /^util$/,
        replacement: path.resolve(__dirname, "node_modules/util"),
      },
      {
        find: /^process$/,
        replacement: path.resolve(__dirname, "node_modules/process/browser"),
      },
    ],
  },
});
