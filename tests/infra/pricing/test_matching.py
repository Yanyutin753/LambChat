"""Pricing matching 纯函数测试：models.dev 数据 → 价格索引 → 模型匹配。"""

from src.infra.pricing.matching import build_price_index, normalize_model_key

MODELS_DEV_SAMPLE = {
    "anthropic": {
        "id": "anthropic",
        "name": "Anthropic",
        "models": {
            "claude-sonnet-4-5": {
                "name": "Claude Sonnet 4.5",
                "cost": {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75},
            },
            "claude-3-5-sonnet-20241022": {
                "name": "Claude 3.5 Sonnet (old)",
                "cost": {"input": 3, "output": 15},
            },
        },
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "models": {
            "gpt-4o": {
                "name": "GPT-4o",
                "cost": {"input": 2.5, "output": 10, "cache_read": 1.25},
            },
        },
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "models": {
            "deepseek-chat": {
                "name": "DeepSeek Chat",
                "cost": {"input": 0.27, "output": 1.1, "cache_read": 0.07},
            },
        },
    },
}


class TestNormalizeModelKey:
    def test_strips_provider_prefix(self):
        assert normalize_model_key("anthropic/claude-sonnet-4-5") == normalize_model_key(
            "claude-sonnet-4-5"
        )

    def test_lowercases_and_collapses(self):
        assert normalize_model_key("GPT-4o") == normalize_model_key("gpt4o")

    def test_strips_date_suffix(self):
        assert normalize_model_key("gpt-4o-2024-08-13") == normalize_model_key("gpt-4o")
        assert normalize_model_key("claude-3-5-sonnet-20241022") == normalize_model_key(
            "claude-3-5-sonnet"
        )

    def test_strips_latest_suffix(self):
        assert normalize_model_key("claude-sonnet-4-5-latest") == normalize_model_key(
            "claude-sonnet-4-5"
        )

    def test_empty_and_garbage_safe(self):
        assert normalize_model_key("") == ""
        assert normalize_model_key("///") == ""


class TestBuildPriceIndex:
    def test_index_only_keeps_priced_models(self):
        api_json = {
            "prov": {
                "id": "prov",
                "name": "Prov",
                "models": {
                    "priced": {"name": "Priced", "cost": {"input": 1, "output": 2}},
                    "unpriced": {"name": "Unpriced"},
                },
            }
        }
        index = build_price_index(api_json)
        assert index.entry_count == 1

    def test_entry_count_counts_priced_entries(self):
        index = build_price_index(MODELS_DEV_SAMPLE)
        assert index.entry_count == 4

    def test_to_snapshot_entries_is_json_serializable(self):
        import json

        index = build_price_index(MODELS_DEV_SAMPLE)
        dumped = json.dumps(index.to_snapshot_entries())
        assert "claude-sonnet-4-5" in dumped

    def test_restore_from_snapshot_roundtrip(self):
        from src.infra.pricing.matching import restore_price_index

        index = build_price_index(MODELS_DEV_SAMPLE)
        restored = restore_price_index(index.to_snapshot_entries())
        assert restored.match("gpt-4o") is not None
        assert restored.match("deepseek/deepseek-chat") is not None


class TestPriceIndexMatch:
    def setup_method(self):
        from src.infra.pricing.matching import build_price_index

        self.index = build_price_index(MODELS_DEV_SAMPLE)

    def test_exact_provider_qualified_value(self):
        entry = self.index.match("anthropic/claude-sonnet-4-5")
        assert entry is not None
        assert entry.provider == "anthropic"
        assert entry.model_id == "claude-sonnet-4-5"
        assert entry.rates.input == 3
        assert entry.rates.cache_write == 3.75

    def test_bare_model_id_with_provider_hint(self):
        entry = self.index.match("gpt-4o", provider="openai")
        assert entry is not None
        assert entry.provider == "openai"

    def test_bare_model_id_without_provider(self):
        entry = self.index.match("gpt-4o")
        assert entry is not None
        assert entry.model_id == "gpt-4o"

    def test_date_suffixed_value_matches_base_model(self):
        entry = self.index.match("gpt-4o-2024-08-13")
        assert entry is not None
        assert entry.model_id == "gpt-4o"

    def test_dated_snapshot_model_matches_exact(self):
        entry = self.index.match("claude-3-5-sonnet-20241022")
        assert entry is not None
        assert entry.model_id == "claude-3-5-sonnet-20241022"

    def test_latest_alias_matches_base(self):
        entry = self.index.match("claude-sonnet-4-5-latest")
        assert entry is not None
        assert entry.model_id == "claude-sonnet-4-5"

    def test_case_insensitive(self):
        entry = self.index.match("OpenAI/GPT-4o")
        assert entry is not None

    def test_unknown_model_returns_none(self):
        assert self.index.match("totally-unknown-model") is None
        assert self.index.match("") is None

    def test_provider_hint_loses_to_exact_value_prefix(self):
        # value 自带前缀时以前缀为准
        entry = self.index.match("deepseek/deepseek-chat", provider="openai")
        assert entry is not None
        assert entry.provider == "deepseek"
