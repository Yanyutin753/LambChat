from src.infra.session.conversation_history_index import (
    CONVERSATION_SEARCH_INDEX_VERSION,
    build_conversation_search_payload,
    extract_conversation_turn,
    merge_source_refs,
)
from src.kernel.schemas.conversation_history import ConversationSourceRef


def test_extract_conversation_turn_keeps_only_user_and_main_final_text() -> None:
    events = [
        {"event_type": "user:message", "data": {"content": "查一下 parser"}},
        {"event_type": "thinking", "data": {"content": "internal"}},
        {"event_type": "message:chunk", "data": {"content": "子代理", "depth": 1}},
        {"event_type": "tool:end", "data": {"content": "secret result"}},
        {"event_type": "message:chunk", "data": {"content": "最终", "depth": 0}},
        {"event_type": "message:chunk", "data": {"content": "答案"}},
    ]

    turn = extract_conversation_turn(events)

    assert turn.user_text == "查一下 parser"
    assert turn.assistant_final_text == "最终答案"


def test_build_conversation_search_payload_indexes_both_sides() -> None:
    payload = build_conversation_search_payload(
        [
            {"event_type": "user:message", "data": {"content": "compile failure"}},
            {"event_type": "message:chunk", "data": {"content": "修复编译错误"}},
        ]
    )

    assert payload.version == CONVERSATION_SEARCH_INDEX_VERSION
    assert "com" in payload.user_terms
    assert "编译" in payload.assistant_terms
    assert set(payload.terms) == set(payload.user_terms + payload.assistant_terms)


def test_merge_source_refs_deduplicates_and_keeps_newest_twenty() -> None:
    existing = [ConversationSourceRef(session_id="s", run_id=f"old-{i}") for i in range(15)]
    incoming = [
        ConversationSourceRef(session_id="s", run_id="old-14"),
        *[ConversationSourceRef(session_id="s", run_id=f"new-{i}") for i in range(10)],
    ]

    merged = merge_source_refs(existing, incoming)

    assert len(merged) == 20
    assert len({(item.session_id, item.run_id) for item in merged}) == 20
    assert merged[-1].run_id == "new-9"
