"""Provider 注册表与官方默认端点。

纯数据 + 纯函数模块（不依赖 client.py 的 SDK/设置链），供
``LLMClient`` 与 ``/providers/list`` 路由共用。新增渠道时在
``PROVIDER_REGISTRY`` 注册 slug（+ 裸模型名前缀，若有），官方
OpenAI 兼容渠道再补 ``PROVIDER_DEFAULTS`` 默认端点。
"""

from typing import Optional

# ── Provider 注册表 ──
# 每个条目: provider_slug → (协议类型, 模型名前缀列表)
# 协议类型: "anthropic" | "google" | "openai" | "azure"
# 不在此注册表的 provider 统一走 OpenAI 兼容接口
PROVIDER_REGISTRY: dict[str, tuple[str, list[str]]] = {
    # Anthropic 协议
    "anthropic": ("anthropic", ["claude"]),
    "minimax": ("anthropic", ["abab", "minimax"]),
    # zai 在 _resolve_protocol 中动态路由：coding plan → anthropic，其余 → openai
    # Google 协议
    "google": ("google", ["gemini", "gemma"]),
    "gemini": ("google", ["gemini", "gemma"]),
    # OpenAI 兼容协议（显式列出，保持完整性）
    "openai": ("openai", ["gpt", "o1", "o3", "o4", "chatgpt"]),
    "deepseek": ("openai", ["deepseek"]),
    "meta": ("openai", ["llama"]),
    "mistral": ("openai", ["mistral", "mixtral"]),
    "qwen": ("openai", ["qwen"]),
    "groq": ("openai", ["groq"]),
    "xai": ("openai", ["grok"]),
    "cohere": ("openai", ["command"]),
    "zhipu": ("openai", ["glm", "chatglm"]),
    "moonshot": ("openai", ["moonshot"]),
    "ollama": ("openai", []),
    "perplexity": ("openai", ["sonar"]),
    "stepfun": ("openai", ["step"]),
    "doubao": ("openai", ["doubao"]),
    "spark": ("openai", ["spark"]),
    "yi": ("openai", ["yi"]),
    "baichuan": ("openai", ["baichuan"]),
    "internlm": ("openai", ["internlm"]),
    "tencent": ("openai", ["hunyuan"]),
    "zeroone": ("openai", ["zero"]),
    # zai coding plan → Claude 协议
    "zai": ("anthropic", []),
    # Kimi → Claude (Anthropic) 协议
    "kimi": ("anthropic", []),
    # Azure OpenAI：endpoint/deployment/api-version 语义独立成协议分支
    "azure": ("azure", []),
    # ── 国际聚合 / 推理托管（模型 ID 普遍为 vendor/model 形式，slug 由表单
    #    显式指定，裸名前缀无法可靠区分，不注册前缀）──
    "openrouter": ("openai", []),
    "together": ("openai", []),
    "fireworks": ("openai", []),
    "deepinfra": ("openai", []),
    "novita": ("openai", []),
    "nvidia": ("openai", []),
    "cerebras": ("openai", []),
    "sambanova": ("openai", []),
    "nebius": ("openai", []),
    "hyperbolic": ("openai", []),
    "lambda": ("openai", []),
    "github": ("openai", []),
    # ── 国内 OpenAI 兼容渠道 ──
    "siliconflow": ("openai", []),
    "baidu": ("openai", ["ernie"]),
    "modelscope": ("openai", []),
    "gitee": ("openai", []),
}

# 官方默认端点：仅当模型配置未填 api_base 时兜底（显式配置/中转优先）。
# 未列出的渠道（自定义中转、google/gemini、azure）返回 None：
# - Google 协议 base_url 语义与 openai 兼容端点不同，交由 SDK；
# - Azure 端点是每账号资源 URL，无统一默认值。
PROVIDER_DEFAULTS: dict[str, str] = {
    # Anthropic 协议
    "anthropic": "https://api.anthropic.com",
    "zai": "https://api.z.ai/api/anthropic",
    "kimi": "https://api.moonshot.ai/anthropic",
    "minimax": "https://api.minimaxi.com/anthropic",
    # OpenAI 兼容协议
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "cohere": "https://api.cohere.com/compatibility/v1",
    "mistral": "https://api.mistral.ai/v1",
    "perplexity": "https://api.perplexity.ai",
    "stepfun": "https://api.stepfun.com/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "spark": "https://spark-api-open.xf-yun.com/v1",
    "yi": "https://api.lingyiwanwu.com/v1",
    "zeroone": "https://api.lingyiwanwu.com/v1",
    "baichuan": "https://api.baichuan-ai.com/v1",
    "internlm": "https://internlm-chat.intern-ai.org.cn/puyu/api/v1",
    "tencent": "https://api.hunyuan.cloud.tencent.com/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "novita": "https://api.novita.ai/v3/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "nebius": "https://api.studio.nebius.ai/v1",
    "hyperbolic": "https://api.hyperbolic.xyz/v1",
    "lambda": "https://api.lambda.ai/v1",
    "github": "https://models.github.ai/inference",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "baidu": "https://qianfan.baidubce.com/v2",
    "modelscope": "https://api-inference.modelscope.cn/v1",
    "gitee": "https://ai.gitee.com/v1",
}


def normalize_provider(provider: Optional[str]) -> str:
    """归一 provider slug：去空白 + 小写。

    注册表键全为小写；配置侧存进来的大小写变体（生产 2026-10-10 实录
    provider="ZAI"）直接查表会 miss 并静默兜底到 openai 协议——GLM 思考
    模型因此走错线格式，历史回传缺 reasoning 即 400。未注册 slug 原样
    返回小写形态，维持「不认识的 provider 走 OpenAI 兼容」的既有语义。
    """
    return (provider or "").strip().lower()


# zhipu hybrid-reasoning GLM families that accept the `thinking` request-body
# field (via model_kwargs). glm-4.7 未核实，不发送。
ZHIPU_THINKING_MODEL_PREFIXES = (
    "glm-4.5",
    "glm-4-5",
    "glm-4.6",
    "glm-4-6",
    "glm-5",
)


def is_zhipu_thinking_model(name: str) -> bool:
    """GLM 思考系模型（glm-4.5+/glm-5），与托管渠道无关，按模型名判断。"""
    lowered = (name or "").lower()
    return any(lowered.startswith(prefix) for prefix in ZHIPU_THINKING_MODEL_PREFIXES)


def _resolve_default_api_base(provider: str) -> Optional[str]:
    """未填 api_base 时按 provider 兜底官方端点；未注册渠道返回 None。"""
    return PROVIDER_DEFAULTS.get(normalize_provider(provider))


def _resolve_protocol(provider: str) -> str:
    """解析 provider 对应的协议类型（slug 大小写/空白不敏感）。"""
    entry = PROVIDER_REGISTRY.get(normalize_provider(provider))
    return entry[0] if entry else "openai"


def _parse_provider(model: str) -> tuple[str, str]:
    """从模型标识解析 provider 和 model_name。

    支持格式:
      - "provider/model-name"  → 直接取 provider 部分（归一为小写 slug）
      - "model-name" (无 /)  → 按前缀推断 provider

    Returns:
        (provider, model_name)，如 ("anthropic", "claude-3-5-sonnet-20241022")
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return normalize_provider(provider), model_name

    # 无 / 时按模型名前缀推断
    lower = model.lower()
    for slug, (_, prefixes) in PROVIDER_REGISTRY.items():
        for prefix in prefixes:
            if lower.startswith(prefix):
                return slug, model

    return "openai", model
