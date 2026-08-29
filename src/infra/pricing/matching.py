"""models.dev 价格数据解析与模型匹配。

models.dev api.json 结构：顶层按 provider 组织，每个 provider 含
``models`` 映射，模型条目的 ``cost`` 字段携带 USD / 每百万 token 单价。

匹配策略（从严到宽）：
1. value 自带前缀时，前缀作为 provider 精确匹配模型 ID；
2. provider 提示 + 裸模型 ID 精确匹配；
3. 归一化匹配（小写、去前缀、去日期/latest 后缀、去非字母数字）；
4. 全局裸模型 ID 精确匹配（任意 provider）；
5. 全局归一化匹配。
"""

import re
from dataclasses import dataclass

from src.infra.pricing.calculator import PriceRates

_DATE_SUFFIXES = (
    re.compile(r"-20\d{6}$"),  # claude-3-5-sonnet-20241022
    re.compile(r"-\d{4}-\d{2}-\d{2}$"),  # gpt-4o-2024-08-13
)
_LATEST_SUFFIX = re.compile(r"-latest$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_model_key(value: str) -> str:
    """归一化模型标识：小写、取最后一段前缀、去日期/latest 后缀、去非字母数字。"""
    if not value:
        return ""
    text = value.strip().lower()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = text.strip("/")
    for pattern in _DATE_SUFFIXES:
        text = pattern.sub("", text)
    text = _LATEST_SUFFIX.sub("", text)
    return _NON_ALNUM.sub("", text)


@dataclass(frozen=True)
class PriceEntry:
    """单个模型的价格条目。"""

    provider: str
    model_id: str
    rates: PriceRates
    name: str = ""

    def to_snapshot(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "name": self.name,
            "rates": {
                "input": self.rates.input,
                "output": self.rates.output,
                "cache_read": self.rates.cache_read,
                "cache_write": self.rates.cache_write,
            },
        }


def _entry_from_snapshot(doc: dict) -> PriceEntry:
    rates = doc.get("rates") or {}
    return PriceEntry(
        provider=str(doc.get("provider") or ""),
        model_id=str(doc.get("model_id") or ""),
        name=str(doc.get("name") or ""),
        rates=PriceRates(
            input=rates.get("input"),
            output=rates.get("output"),
            cache_read=rates.get("cache_read"),
            cache_write=rates.get("cache_write"),
        ),
    )


def _rates_from_cost(cost: dict | None) -> PriceRates | None:
    if not isinstance(cost, dict):
        return None
    rates = PriceRates(
        input=cost.get("input"),
        output=cost.get("output"),
        cache_read=cost.get("cache_read"),
        cache_write=cost.get("cache_write"),
    )
    # 完全没有价格信息（input/output 均缺失）的模型不收录
    if rates.input is None and rates.output is None:
        return None
    return rates


class PriceIndex:
    """价格索引：内存中的模型价格快照，支持多级匹配。"""

    def __init__(self, entries: list[PriceEntry]):
        self._entries = entries
        self._by_provider: dict[str, dict[str, PriceEntry]] = {}
        self._by_provider_normalized: dict[str, dict[str, PriceEntry]] = {}
        self._global: dict[str, PriceEntry] = {}
        self._global_normalized: dict[str, PriceEntry] = {}
        for entry in entries:
            self._by_provider.setdefault(entry.provider, {})[entry.model_id] = entry
            normalized = normalize_model_key(entry.model_id)
            if normalized:
                self._by_provider_normalized.setdefault(entry.provider, {}).setdefault(
                    normalized, entry
                )
                self._global.setdefault(entry.model_id, entry)
                self._global_normalized.setdefault(normalized, entry)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def to_snapshot_entries(self) -> list[dict]:
        """导出为可 JSON 序列化的快照（用于 Mongo 持久化）。"""
        return [entry.to_snapshot() for entry in self._entries]

    def _match_in_provider(self, provider: str, model: str) -> PriceEntry | None:
        exact = self._by_provider.get(provider, {}).get(model)
        if exact:
            return exact
        normalized = normalize_model_key(model)
        if normalized:
            return self._by_provider_normalized.get(provider, {}).get(normalized)
        return None

    def match(self, value: str, provider: str | None = None) -> PriceEntry | None:
        """按模型标识匹配价格条目；未匹配返回 None。"""
        value = (value or "").strip()
        if not value:
            return None

        if "/" in value:
            prefix, model = value.split("/", 1)
            entry = self._match_in_provider(prefix.strip().lower(), model.strip())
            if entry:
                return entry

        model = value.rsplit("/", 1)[-1].strip()
        if provider:
            entry = self._match_in_provider(provider.strip().lower(), model)
            if entry:
                return entry

        exact = self._global.get(model)
        if exact:
            return exact
        normalized = normalize_model_key(model)
        if normalized:
            return self._global_normalized.get(normalized)
        return None


def build_price_index(api_json: dict) -> PriceIndex:
    """解析 models.dev api.json 为价格索引。"""
    entries: list[PriceEntry] = []
    if not isinstance(api_json, dict):
        return PriceIndex(entries)
    for provider_doc in api_json.values():
        if not isinstance(provider_doc, dict):
            continue
        provider = str(provider_doc.get("id") or "")
        if not provider:
            continue
        models = provider_doc.get("models")
        if not isinstance(models, dict):
            continue
        for model_id, model_doc in models.items():
            rates = _rates_from_cost((model_doc or {}).get("cost"))
            if rates is None:
                continue
            entries.append(
                PriceEntry(
                    provider=provider,
                    model_id=str(model_id),
                    rates=rates,
                    name=str((model_doc or {}).get("name") or ""),
                )
            )
    return PriceIndex(entries)


def restore_price_index(snapshot_entries: list[dict]) -> PriceIndex:
    """从持久化快照还原价格索引。"""
    return PriceIndex([_entry_from_snapshot(doc) for doc in snapshot_entries or []])
