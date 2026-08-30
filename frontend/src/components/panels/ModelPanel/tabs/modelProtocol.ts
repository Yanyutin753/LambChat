// 模型协议推断（与后端 src/infra/llm/client.py 的 PROVIDER_REGISTRY/_parse_provider 语义对齐）：
// 值前缀 > 显式 provider > 模型名前缀；未注册一律视为 OpenAI 兼容。
// 「API 格式」（chat_completions / responses）仅对 OpenAI 协议有意义，
// Claude/Gemini 原生协议应隐藏该选择器。

export interface ProviderInfo {
  value: string;
  protocol: string;
  prefixes: string[];
}

export function resolveModelProtocol(opts: {
  value: string;
  provider?: string;
  providers: ProviderInfo[];
}): string {
  const raw = (opts.value || "").trim();
  const providers = opts.providers || [];

  let slug = "";
  if (raw.includes("/")) {
    slug = raw.split("/", 1)[0].trim().toLowerCase();
  } else if (opts.provider) {
    slug = opts.provider.trim().toLowerCase();
  }

  if (slug) {
    const hit = providers.find((p) => p.value === slug);
    return hit ? hit.protocol : "openai";
  }

  const lower = raw.toLowerCase();
  for (const provider of providers) {
    for (const prefix of provider.prefixes || []) {
      if (prefix && lower.startsWith(prefix)) {
        return provider.protocol;
      }
    }
  }
  return "openai";
}

/** API 格式选择器是否应该显示（仅 OpenAI 兼容协议） */
export function showsApiFormat(protocol: string): boolean {
  return protocol === "openai";
}
