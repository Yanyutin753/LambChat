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

// Providers whose icons are monochrome (use currentColor, need dark-mode invert)
const monochromeProviders = new Set([
  "openai",
  "groq",
  "xai",
  "ollama",
  "yi",
  "zeroone",
  "moonshot",
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
