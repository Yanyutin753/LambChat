import { spawnSync } from "node:child_process";

const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";

function hasCommand(command) {
  return (
    spawnSync(command, ["--version"], {
      stdio: "ignore",
    }).status === 0
  );
}

// LAMBCHAT_APP_URL 可选：提供则构建期烘焙为默认服务器；缺省打「运行时
// 配置」包（安装后首启设置屏填 base_url，见 serverConfig/ServerSetupScreen）
const appUrl = process.env.LAMBCHAT_APP_URL || "";
const normalizedAppUrl = appUrl.replace(/\/+$/, "");
if (!normalizedAppUrl) {
  console.log(
    "LAMBCHAT_APP_URL not set: building runtime-configured package (first-run server setup)",
  );
}
const tauriCliPackage = "@tauri-apps/cli@2.11.2";

if (!hasCommand("rustc") || !hasCommand("cargo")) {
  console.error(
    "Rust is required for Tauri desktop builds. Install Rust and Tauri system prerequisites, then rerun this command.",
  );
  console.error("See: https://tauri.app/start/prerequisites/");
  process.exit(1);
}

const iconResult = spawnSync(
  pnpmCommand,
  ["dlx", tauriCliPackage, "icon", "public/icons/icon-512.png"],
  {
    stdio: "inherit",
    shell: process.platform === "win32",
  },
);

if (iconResult.error) {
  console.error(iconResult.error);
}

if (iconResult.status !== 0) {
  process.exit(iconResult.status ?? 1);
}

const args = ["dlx", tauriCliPackage, "build", "--ci", "--no-sign"];

const target = process.env.TAURI_TARGET || process.env.DESKTOP_TARGET || "";
if (target) {
  args.push("--target", target);
}

const bundles = process.env.TAURI_BUNDLES || process.env.DESKTOP_BUNDLES || "";
if (bundles) {
  args.push("--bundles", bundles);
}

if (process.env.TAURI_DEBUG === "1") {
  args.push("--debug");
}

const result = spawnSync(pnpmCommand, args, {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    LAMBCHAT_APP_URL: normalizedAppUrl,
    VITE_API_BASE: normalizedAppUrl,
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
