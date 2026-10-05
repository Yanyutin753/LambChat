import type { ChannelRuntimeConfig } from "../../../types/channel";

export function defaultChannelRuntime(): ChannelRuntimeConfig {
  return { sandbox: "default", sandbox_machine_id: "", enable_thinking: "",
    enable_code_interpreter: null, response_language: "", env_vars: {} };
}

export function formatChannelEnv(env?: Record<string, string>): string {
  return Object.entries(env || {}).map(([key, value]) => `${key}=${value}`).join("\n");
}

export function parseChannelEnv(text: string): Record<string, string> {
  const entries = new Map<string, string>();
  let total = 0;
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1);
    if (separator < 1 || !/^[A-Za-z_][A-Za-z0-9_]{0,255}$/.test(key) || entries.has(key) || value.includes("\0")) {
      throw new Error("channel.runtime.envInvalid");
    }
    if (key === "LAMBCHAT_WORKSPACE" || key === "LAMBCHAT_SHARED") {
      throw new Error("channel.runtime.envProtected");
    }
    total += key.length + value.length;
    if (value.length > 16000 || entries.size >= 50 || total > 64000) {
      throw new Error("channel.runtime.envTooLarge");
    }
    entries.set(key, value);
  }
  return Object.fromEntries(entries);
}
