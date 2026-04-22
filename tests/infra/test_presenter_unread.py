from src.infra.writer.present import should_increment_unread_for_trace_status


def test_terminal_success_and_error_traces_increment_unread() -> None:
    assert should_increment_unread_for_trace_status("completed") is True
    assert should_increment_unread_for_trace_status("error") is True


def test_non_terminal_or_unknown_traces_do_not_increment_unread() -> None:
    assert should_increment_unread_for_trace_status("running") is False
    assert should_increment_unread_for_trace_status("") is False
