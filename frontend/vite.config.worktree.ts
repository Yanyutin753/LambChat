import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import {
  createPerformanceManifestTransform,
  EAGER_JAVASCRIPT_BUDGET_BYTES,
  PRECACHE_ADDITIONAL_ENTRIES,
  PRECACHE_BUDGET_BYTES,
} from "./scripts/performanceBudget";

// Available agents (sync with backend)
const AGENT_IDS = ["default", "api", "data_pipeline", "simple_workflow"];
const ICONS_DIR = path.resolve(__dirname, "public/icons");

function getStaticIconContentType(filePath: string): string {
  if (filePath.endsWith(".svg")) return "image/svg+xml";
  if (filePath.endsWith(".png")) return "image/png";
  if (filePath.endsWith(".jpg") || filePath.endsWith(".jpeg")) {
    return "image/jpeg";
  }
  if (filePath.endsWith(".webp")) return "image/webp";
  if (filePath.endsWith(".ico")) return "image/x-icon";
  return "application/octet-stream";
}

const cacheStableIconsPlugin = {
  name: "cache-stable-icons",
  configureServer(server: {
    middlewares: {
      use: (
        handler: (
          req: { method?: string; url?: string },
          res: {
            statusCode?: number;
            setHeader: (name: string, value: string) => void;
            end: (body: Buffer) => void;
          },
          next: () => void,
        ) => void,
      ) => void;
    };
  }) {
    server.middlewares.use((req, res, next) => {
      if (req.method !== "GET" && req.method !== "HEAD") {
        next();
        return;
      }

      const requestPath = req.url?.split("?")[0];
      if (!requestPath?.startsWith("/icons/")) {
        next();
        return;
      }

      const relativePath = requestPath.slice("/icons/".length);
      if (
        !relativePath ||
        relativePath.includes("..") ||
        relativePath.includes("\\")
      ) {
        next();
        return;
      }

      const filePath = path.join(ICONS_DIR, relativePath);
      if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
        next();
        return;
      }

      const fileBuffer = fs.readFileSync(filePath);
      res.statusCode = 200;
      res.setHeader("Content-Type", getStaticIconContentType(filePath));
      res.setHeader("Content-Length", String(fileBuffer.length));
      res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
      if (req.method === "HEAD") {
        res.end(Buffer.alloc(0));
        return;
      }
      res.end(fileBuffer);
    });
  },
};

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectRegister: false,
      manifest: false,
      injectManifest: {
        globPatterns: [
          "**/*.{js,css,html,ico,png,svg,webp,avif,woff,woff2,json}",
        ],
        maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
        additionalManifestEntries: PRECACHE_ADDITIONAL_ENTRIES,
        manifestTransforms: [
          createPerformanceManifestTransform({
            distDir: path.resolve(__dirname, "dist"),
            readText: (filePath) => fs.readFileSync(filePath, "utf8"),
            readBytes: (filePath) => fs.readFileSync(filePath),
            log: (message) => console.info(message),
            eagerJavaScriptBudgetBytes: EAGER_JAVASCRIPT_BUDGET_BYTES,
            precacheBudgetBytes: PRECACHE_BUDGET_BYTES,
          }),
        ],
      },
      includeManifestIcons: false,
      devOptions: {
        enabled: false,
      },
    }),
    cacheStableIconsPlugin,
  ],
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
  esbuild: {
    drop: process.env.NODE_ENV === "production" ? ["console", "debugger"] : [],
  },
  build: {
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-markdown": [
            "react-markdown",
            "remark-gfm",
            "remark-breaks",
            "remark-math",
            "rehype-katex",
            "rehype-highlight",
          ],
          "vendor-katex": ["katex"],
          "vendor-i18n": ["i18next", "react-i18next"],
        },
      },
    },
  },
  server: {
    host: true, // 监听所有地址 (0.0.0.0)，允许 127.0.0.1 和 localhost 访问
    port: 3011,
    proxy: {
      // Long-running chat event stream
      "^/api/chat/sessions/[^/]+/stream$": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
        ws: true,
        timeout: 86400000, // 24 hours timeout for long-running chat streams
        proxyTimeout: 86400000, // 24 hours proxy timeout
      },
      // API routes (including /api/chat for SSE)
      "/api": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
        ws: true, // Enable WebSocket/SSE support for streaming
        timeout: 300000, // 5 minutes timeout for regular API requests
        proxyTimeout: 300000, // 5 minutes proxy timeout
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            // 保留原始 host 到 X-Forwarded-Host 头，用于 OAuth redirect_uri
            const host = req.headers.host;
            if (host) {
              proxyReq.setHeader("X-Forwarded-Host", host);
            }
          });
        },
      },
      // Agent routes (/{agent_id}/chat, /{agent_id}/stream, /{agent_id}/skills)
      ...Object.fromEntries(
        AGENT_IDS.map((id) => [
          `/${id}`,
          {
            target: "http://127.0.0.1:8110",
            changeOrigin: true,
            secure: false,
            ws: true, // Enable WebSocket/SSE support for streaming
            timeout: 86400000, // 24 hours timeout for long-running chat streams
            proxyTimeout: 86400000, // 24 hours proxy timeout
          },
        ]),
      ),
      "/tools": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
      },
      "/human": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
      },
      "/health": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      "/services": {
        target: "http://127.0.0.1:8110",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
