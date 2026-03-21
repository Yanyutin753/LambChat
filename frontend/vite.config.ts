import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Available agents (sync with backend)
const AGENT_IDS = ["default", "api", "data_pipeline", "simple_workflow"];

export default defineConfig({
  plugins: [react()],
  esbuild: {
    drop: process.env.NODE_ENV === "production" ? ["console", "debugger"] : [],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-codemirror": [
            "@uiw/react-codemirror",
            "@codemirror/lang-css",
            "@codemirror/lang-html",
            "@codemirror/lang-javascript",
            "@codemirror/lang-json",
            "@codemirror/lang-markdown",
            "@codemirror/lang-python",
            "@codemirror/lang-sql",
            "@codemirror/lang-yaml",
          ],
          "vendor-markdown": [
            "react-markdown",
            "remark-gfm",
            "remark-breaks",
            "remark-math",
            "rehype-katex",
            "rehype-highlight",
          ],
          "vendor-sandpack": ["@codesandbox/sandpack-react"],
          "vendor-mermaid": ["mermaid"],
          "vendor-katex": ["katex"],
          "vendor-i18n": ["i18next", "react-i18next"],
        },
      },
    },
  },
  server: {
    host: true, // 监听所有地址 (0.0.0.0)，允许 127.0.0.1 和 localhost 访问
    port: 3001,
    proxy: {
      // API routes (including /api/chat for SSE)
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
        ws: true, // Enable WebSocket/SSE support for streaming
        timeout: 300000, // 5 minutes timeout for SSE
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
            target: "http://127.0.0.1:8000",
            changeOrigin: true,
            secure: false,
            ws: true, // Enable WebSocket/SSE support for streaming
            timeout: 300000, // 5 minutes timeout for SSE
            proxyTimeout: 300000, // 5 minutes proxy timeout
          },
        ]),
      ),
      "/tools": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      "/human": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      "/services": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
