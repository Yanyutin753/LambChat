import openai from "@lobehub/icons-static-svg/icons/openai.svg?url";
import claude from "@lobehub/icons-static-svg/icons/claude-color.svg?url";
import gemini from "@lobehub/icons-static-svg/icons/gemini-color.svg?url";

import deepseek from "@lobehub/icons-static-svg/icons/deepseek-color.svg?url";
import meta from "@lobehub/icons-static-svg/icons/meta-color.svg?url";
import mistral from "@lobehub/icons-static-svg/icons/mistral-color.svg?url";
import qwen from "@lobehub/icons-static-svg/icons/qwen-color.svg?url";
import groq from "@lobehub/icons-static-svg/icons/groq.svg?url";
import grok from "@lobehub/icons-static-svg/icons/grok.svg?url";
import cohere from "@lobehub/icons-static-svg/icons/cohere-color.svg?url";
import zhipu from "@lobehub/icons-static-svg/icons/zhipu-color.svg?url";
import moonshot from "@lobehub/icons-static-svg/icons/moonshot.svg?url";
import ollama from "@lobehub/icons-static-svg/icons/ollama.svg?url";
import perplexity from "@lobehub/icons-static-svg/icons/perplexity-color.svg?url";
import minimax from "@lobehub/icons-static-svg/icons/minimax-color.svg?url";
import stepfun from "@lobehub/icons-static-svg/icons/stepfun-color.svg?url";
import doubao from "@lobehub/icons-static-svg/icons/doubao-color.svg?url";
import spark from "@lobehub/icons-static-svg/icons/spark-color.svg?url";
import yi from "@lobehub/icons-static-svg/icons/yi.svg?url";
import baichuan from "@lobehub/icons-static-svg/icons/baichuan-color.svg?url";
import internlm from "@lobehub/icons-static-svg/icons/internlm-color.svg?url";
import tencent from "@lobehub/icons-static-svg/icons/tencent-color.svg?url";
import zeroone from "@lobehub/icons-static-svg/icons/zeroone.svg?url";
import azureIcon from "@lobehub/icons-static-svg/icons/azure-color.svg?url";

// Note: AWS icon requires separate SVG file or use text fallback
// For now, we'll use a placeholder approach for bedrock

// provider name → icon
const providerMap: Record<string, string> = {
  openai,
  anthropic: claude,
  google: gemini,
  deepseek,
  meta,
  mistral,
  qwen,
  groq,
  xai: grok,
  cohere,
  zhipu,
  moonshot,
  ollama,
  perplexity,
  minimax,
  stepfun,
  doubao,
  spark,
  yi,
  baichuan,
  internlm,
  tencent,
  zeroone,
  alibaba: qwen,
  aliyun: qwen,
  hunyuan: tencent,
  azure: azureIcon,
  bedrock: openai, // Bedrock uses various model providers, use OpenAI as generic fallback
};

// model name prefix → provider icon (fallback when no provider prefix)
const modelPrefixMap: Record<string, string> = {
  gpt: "openai",
  o1: "openai",
  o3: "openai",
  o4: "openai",
  chatgpt: "openai",
  claude: "anthropic",
  gemini: "google",
  gemma: "google",
  deepseek: "deepseek",
  llama: "meta",
  mistral: "mistral",
  mixtral: "mistral",
  qwen: "qwen",
  grok: "xai",
  command: "cohere",
  glm: "zhipu",
  chatglm: "zhipu",
  moonshot: "moonshot",
  kimi: "moonshot",
  sonar: "perplexity",
  abab: "minimax",
  minimax: "minimax",
  step: "stepfun",
  doubao: "doubao",
  spark: "spark",
  yi: "yi",
  baichuan: "baichuan",
  internlm: "internlm",
  hunyuan: "tencent",
  zero: "zeroone",
};

// Provider colors for UI accents (Cherry-Studio style)
const providerColors: Record<string, string> = {
  anthropic: "#FF6B6B",
  google: "#4285F4",
  openai: "#10A37F",
  azure: "#0078D4",
  bedrock: "#FF9900",
  groq: "#FF4B4B",
  deepseek: "#0055FF",
  mistral: "#FF6B35",
  cohere: "#FF6B35",
  ollama: "#800000",
  minimax: "#F5A623",
  zai: "#8B5CF6",
  meta: "#0668BD",
  qwen: "#FB6F23",
  xai: "#F97316",
  zhipu: "#00C896",
  moonshot: "#6366F1",
  perplexity: "#20BDF8",
  stepfun: "#FF6B9D",
  doubao: "#3B82F6",
  spark: "#FF6B00",
  yi: "#FFD000",
  baichuan: "#A855F7",
  internlm: "#F59E0B",
  tencent: "#30A0FF",
  zeroone: "#00D9A5",
  alibaba: "#FF6B00",
  aliyun: "#FF6B00",
  hunyuan: "#30A0FF",
};

export function getProviderColor(provider: string): string | null {
  return providerColors[provider.toLowerCase()] || null;
}

export function getProviderGradient(provider: string): string | null {
  const color = getProviderColor(provider);
  if (!color) return null;
  return `linear-gradient(135deg, ${color}, ${color}80)`;
}

// Providers whose icons are monochrome (use currentColor, need dark-mode invert)
const monochromeProviders = new Set([
  "openai",
  "groq",
  "xai",
  "ollama",
  "yi",
  "zeroone",
  "moonshot",
  "azure",
  "bedrock",
]);

export function isMonochromeIcon(model: string): boolean {
  const lower = model.toLowerCase();
  const slashIdx = lower.indexOf("/");
  if (slashIdx !== -1) {
    const provider = lower.slice(0, slashIdx);
    if (monochromeProviders.has(provider)) return true;
  }
  for (const [prefix, slug] of Object.entries(modelPrefixMap)) {
    if (
      lower.startsWith(prefix) ||
      (slashIdx !== -1 && lower.slice(slashIdx + 1).startsWith(prefix))
    ) {
      return monochromeProviders.has(slug);
    }
  }
  return false;
}

function resolveIcon(model: string): string | null {
  const lower = model.toLowerCase();

  // format: "provider/model-name" — try provider part first
  const slashIdx = lower.indexOf("/");
  if (slashIdx !== -1) {
    const provider = lower.slice(0, slashIdx);
    if (providerMap[provider]) return providerMap[provider];
    // fall through to model-name matching
    const modelName = lower.slice(slashIdx + 1);
    for (const [prefix, slug] of Object.entries(modelPrefixMap)) {
      if (modelName.startsWith(prefix)) return providerMap[slug] ?? null;
    }
    return null;
  }

  // no slash — match by model name prefix
  for (const [prefix, slug] of Object.entries(modelPrefixMap)) {
    if (lower.startsWith(prefix)) return providerMap[slug] ?? null;
  }
  return null;
}

export function getModelIconUrl(model: string): string | null {
  return resolveIcon(model);
}
