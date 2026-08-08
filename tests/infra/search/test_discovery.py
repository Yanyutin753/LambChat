from __future__ import annotations

from src.infra.search import discovery
from src.infra.search.discovery import DiscoveryRecord, search_records


def names(query: str, records: list[DiscoveryRecord]) -> list[str]:
    return [match.name for match in search_records(query, records)]


def test_search_normalizes_common_name_separators() -> None:
    records = [DiscoveryRecord(name="web_search")]

    assert names("web-search", records) == ["web_search"]
    assert names("web search", records) == ["web_search"]


def test_search_selects_exact_names_case_insensitively() -> None:
    records = [
        DiscoveryRecord(name="Alpha:Create"),
        DiscoveryRecord(name="beta:list"),
    ]

    assert names("select:alpha:create,beta:list", records) == [
        "Alpha:Create",
        "beta:list",
    ]


def test_search_matches_full_pinyin_spaced_pinyin_and_initials() -> None:
    records = [DiscoveryRecord(name="小红书发布", text="发布图文内容")]

    assert names("xiaohongshufabu", records) == ["小红书发布"]
    assert names("xiao hong shu fa bu", records) == ["小红书发布"]
    assert names("xhsfb", records) == ["小红书发布"]


def test_search_matches_pinyin_from_description() -> None:
    records = [DiscoveryRecord(name="publish_content", text="发布小红书内容")]

    assert names("xiaohongshu", records) == ["publish_content"]


def test_required_term_matches_pinyin_alias() -> None:
    records = [
        DiscoveryRecord(name="小红书发布", text="publish content"),
        DiscoveryRecord(name="普通发布", text="publish content"),
    ]

    assert names("+xiaohongshu publish", records) == ["小红书发布"]


def test_search_sorts_equal_scores_by_canonical_name() -> None:
    records = [
        DiscoveryRecord(name="zeta_lookup", text="database query"),
        DiscoveryRecord(name="alpha_lookup", text="database query"),
    ]

    assert names("database", records) == ["alpha_lookup", "zeta_lookup"]


def test_typo_matching_is_conservative() -> None:
    records = [DiscoveryRecord(name="小红书")]

    assert names("xiaohognshu", records) == ["小红书"]
    assert names("xhb", records) == []
    assert names("xiaolanshu", records) == []


def test_pinyin_failure_falls_back_to_normalized_text_search(monkeypatch) -> None:
    def fail_pinyin(_value: str) -> tuple[str, str]:
        raise RuntimeError("pinyin unavailable")

    monkeypatch.setattr(discovery, "_pinyin_aliases", fail_pinyin)

    records = [DiscoveryRecord(name="web_search", text="search the web")]

    assert names("web-search", records) == ["web_search"]
