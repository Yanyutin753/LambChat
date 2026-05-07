import { defineConfig } from "vitepress";

export default defineConfig({
  title: "LambChat Docs",
  base: process.env.VITEPRESS_BASE ?? "/",
  lastUpdated: true,
  cleanUrls: true,
  srcExclude: ["plans/**", "superpowers/**", "images/**"],
  outDir: ".vitepress/dist",

  locales: {
    root: {
      lang: "en",
      label: "English",
      description: "LambChat Documentation",
      themeConfig: {
        nav: [{ text: "Home", link: "/en/" }],
      },
    },
    en: {
      lang: "en",
      label: "English",
      link: "/en/",
      description: "Open-source AI Agent platform documentation",
      themeConfig: {
        nav: [
          { text: "Home", link: "/en/" },
          { text: "Guide", link: "/en/getting-started" },
          { text: "Config", link: "/en/env/app" },
        ],
        sidebar: {
          "/en/": [
            {
              text: "Guide",
              items: [
                { text: "Getting Started", link: "/en/getting-started" },
                { text: "Docker Deployment", link: "/en/deploy/docker" },
                { text: "Kubernetes Deployment", link: "/en/deploy/kubernetes" },
              ],
            },
            {
              text: "Environment Variables",
              items: [
                { text: "Application", link: "/en/env/app" },
                { text: "LLM", link: "/en/env/llm" },
                { text: "Session", link: "/en/env/session" },
                { text: "Database", link: "/en/env/database" },
                { text: "Storage", link: "/en/env/storage" },
                { text: "Sandbox", link: "/en/env/sandbox" },
                { text: "MCP & Tools", link: "/en/env/mcp" },
                { text: "Security", link: "/en/env/security" },
                { text: "OAuth", link: "/en/env/oauth" },
                { text: "Email", link: "/en/env/email" },
                { text: "Memory", link: "/en/env/memory" },
                { text: "Tracing", link: "/en/env/tracing" },
                { text: "Frontend", link: "/en/env/frontend" },
              ],
            },
          ],
        },
      },
    },
    zh: {
      lang: "zh-CN",
      label: "简体中文",
      link: "/zh/",
      description: "开源 AI Agent 平台文档",
      themeConfig: {
        nav: [
          { text: "首页", link: "/zh/" },
          { text: "指南", link: "/zh/getting-started" },
          { text: "配置", link: "/zh/env/app" },
        ],
        sidebar: {
          "/zh/": [
            {
              text: "指南",
              items: [
                { text: "快速开始", link: "/zh/getting-started" },
                { text: "Docker 部署", link: "/zh/deploy/docker" },
                { text: "Kubernetes 部署", link: "/zh/deploy/kubernetes" },
              ],
            },
            {
              text: "环境变量",
              items: [
                { text: "应用配置", link: "/zh/env/app" },
                { text: "LLM 配置", link: "/zh/env/llm" },
                { text: "会话配置", link: "/zh/env/session" },
                { text: "数据库配置", link: "/zh/env/database" },
                { text: "存储配置", link: "/zh/env/storage" },
                { text: "沙箱配置", link: "/zh/env/sandbox" },
                { text: "MCP 与工具", link: "/zh/env/mcp" },
                { text: "安全配置", link: "/zh/env/security" },
                { text: "OAuth", link: "/zh/env/oauth" },
                { text: "邮件配置", link: "/zh/env/email" },
                { text: "记忆系统", link: "/zh/env/memory" },
                { text: "链路追踪", link: "/zh/env/tracing" },
                { text: "前端配置", link: "/zh/env/frontend" },
              ],
            },
          ],
        },
      },
    },
  },

  themeConfig: {
    search: { provider: "local" },
    socialLinks: [
      { icon: "github", link: "https://github.com/Yanyutin753/LambChat" },
    ],
  },
});
