import { spawnSync } from "node:child_process";

const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
// LAMBCHAT_APP_URL 可选：提供则构建期烘焙为默认服务器；缺省打「运行时
// 配置」包（安装后首启设置屏填 base_url，见 serverConfig/ServerSetupScreen）
const appUrl = process.env.LAMBCHAT_APP_URL || process.env.VITE_API_BASE || "";

const normalizedAppUrl = appUrl.replace(/\/+$/, "");
if (!normalizedAppUrl) {
  console.log(
    "LAMBCHAT_APP_URL not set: building runtime-configured package (first-run server setup)",
  );
}

const result = spawnSync(pnpmCommand, ["build"], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    LAMBCHAT_APP_URL: normalizedAppUrl,
    VITE_API_BASE: normalizedAppUrl,
    NODE_OPTIONS: [process.env.NODE_OPTIONS, "--max-old-space-size=4096"]
      .filter(Boolean)
      .join(" "),
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
