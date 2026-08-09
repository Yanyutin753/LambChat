import { spawnSync } from "node:child_process";

const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const appUrl = process.env.LAMBCHAT_APP_URL || process.env.VITE_API_BASE || "";

if (!appUrl) {
  console.error(
    "Missing LAMBCHAT_APP_URL. Example: LAMBCHAT_APP_URL=https://chat.example.com pnpm packaged:build",
  );
  process.exit(1);
}

const normalizedAppUrl = appUrl.replace(/\/+$/, "");

const result = spawnSync(pnpmCommand, ["build"], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    LAMBCHAT_APP_URL: normalizedAppUrl,
    VITE_API_BASE: normalizedAppUrl,
    NODE_OPTIONS: [
      process.env.NODE_OPTIONS,
      "--max-old-space-size=4096",
    ]
      .filter(Boolean)
      .join(" "),
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
