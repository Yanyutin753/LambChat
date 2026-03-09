import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Available agents (sync with backend)
const AGENT_IDS = ["default", "api", "data_pipeline", "simple_workflow"];

export default defineConfig({
  plugins: [react()],
  esbuild: {
    drop: process.env.NODE_ENV === "production" ? ["console", "debugger"] : [],
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
      "/agents": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
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
