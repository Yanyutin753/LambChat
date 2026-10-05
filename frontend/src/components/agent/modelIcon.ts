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
import kimi from "@lobehub/icons-static-svg/icons/moonshot.svg?url";
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
import openrouter from "@lobehub/icons-static-svg/icons/openrouter.svg?url";
import together from "@lobehub/icons-static-svg/icons/together-color.svg?url";
import fireworks from "@lobehub/icons-static-svg/icons/fireworks-color.svg?url";
import deepinfra from "@lobehub/icons-static-svg/icons/deepinfra-color.svg?url";
import novita from "@lobehub/icons-static-svg/icons/novita-color.svg?url";
import nvidia from "@lobehub/icons-static-svg/icons/nvidia-color.svg?url";
import cerebras from "@lobehub/icons-static-svg/icons/cerebras.svg?url";
import sambanova from "@lobehub/icons-static-svg/icons/sambanova-color.svg?url";
import nebius from "@lobehub/icons-static-svg/icons/nebius.svg?url";
import hyperbolic from "@lobehub/icons-static-svg/icons/hyperbolic-color.svg?url";
import lambda from "@lobehub/icons-static-svg/icons/lambda.svg?url";
import github from "@lobehub/icons-static-svg/icons/github.svg?url";
import azure from "@lobehub/icons-static-svg/icons/azure.svg?url";
import siliconcloud from "@lobehub/icons-static-svg/icons/siliconcloud-color.svg?url";
import baidu from "@lobehub/icons-static-svg/icons/baidu-color.svg?url";
import modelscope from "@lobehub/icons-static-svg/icons/modelscope-color.svg?url";
import gitee from "@lobehub/icons-static-svg/icons/giteeai.svg?url";

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
  kimi,
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
  gemini,
  zai: zhipu,
  alibaba: qwen,
  aliyun: qwen,
  hunyuan: tencent,
  openrouter,
  together,
  fireworks,
  deepinfra,
  novita,
  nvidia,
  cerebras,
  sambanova,
  nebius,
  hyperbolic,
  lambda,
  github,
  azure,
  siliconflow: siliconcloud,
  baidu,
  modelscope,
  gitee,
};

export const modelIconSlugs = Object.keys(providerMap);

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
  kimi: "kimi",
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
  "openrouter",
  "cerebras",
  "nebius",
  "lambda",
  "github",
  "azure",
  "gitee",
]);

export function isMonochromeIcon(model: string, provider?: string): boolean {
  if (provider && monochromeProviders.has(provider)) return true;
  const lower = model.toLowerCase();
  const slashIdx = lower.indexOf("/");
  if (slashIdx !== -1) {
    const p = lower.slice(0, slashIdx);
    if (monochromeProviders.has(p)) return true;
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

export function getModelIconUrl(
  model: string,
  provider?: string,
  explicitIcon?: string,
): string | null {
  if (explicitIcon && providerMap[explicitIcon])
    return providerMap[explicitIcon];
  if (provider && providerMap[provider]) return providerMap[provider];
  return resolveIcon(model);
}
