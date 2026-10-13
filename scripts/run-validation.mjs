import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const windows = process.platform === "win32";
const runner = fileURLToPath(new URL("./run_validation.py", import.meta.url));
const command = process.argv.slice(2);
const shell = command[0] === "--shell";
if (shell) command.shift();
// Only compound scripts need a shell; ordinary test arguments stay literal.
const args = windows
  ? [process.env.ComSpec || "cmd.exe", "/d", "/s", "/c", ...command]
  : shell
    ? ["/bin/sh", "-c", `${command[0]} "$@"`, "validation", ...command.slice(1)]
    : command;
const result = spawnSync(windows ? "python" : "python3", [runner, ...args], {
  stdio: "inherit",
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
