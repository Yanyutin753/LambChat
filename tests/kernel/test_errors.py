"""ErrorCode 枚举与 AppError 基类的行为测试。"""

from src.kernel.errors import AppError, ErrorCode


def test_error_code_properties():
    assert ErrorCode.SESSION_NOT_FOUND.code == "session_not_found"
    assert ErrorCode.SESSION_NOT_FOUND.status == 404


def test_error_codes_unique():
    codes = [member.code for member in ErrorCode]
    assert len(codes) == len(set(codes))


def test_all_codes_snake_case():
    for member in ErrorCode:
        assert member.code == member.code.lower()
        assert " " not in member.code and "-" not in member.code


def test_app_error_defaults():
    err = AppError(ErrorCode.SESSION_NOT_FOUND, args={"session_id": "s1"})
    assert err.error_code is ErrorCode.SESSION_NOT_FOUND
    assert err.http_status == 404
    assert err.args_data == {"session_id": "s1"}
    assert err.message == "Session not found"


def test_app_error_message_override():
    err = AppError(ErrorCode.INTERNAL_ERROR, message="boom: detail here")
    assert err.message == "boom: detail here"
    assert str(err) == "boom: detail here"


def test_app_error_lookup_by_code():
    err = AppError(ErrorCode.from_code("session_not_found"))
    assert err.error_code is ErrorCode.SESSION_NOT_FOUND


def test_legacy_machine_codes_absorbed():
    legacy = {
        "team_not_found",
        "team_member_model_unavailable",
        "persona_preset_not_found",
        "persona_preset_no_edit_permission",
        "persona_preset_no_delete_permission",
        "persona_preset_no_admin_permission",
        "model_not_found",
        "model_disabled",
        "model_not_allowed",
        "invalid_attachments",
        "session_delete_in_progress",
    }
    codes = {member.code for member in ErrorCode}
    assert legacy <= codes


# ---------- kernel 异常类改造 ----------


def test_retrofit_not_found_default_code():
    from src.kernel.exceptions import NotFoundError

    err = NotFoundError("whatever message")
    assert err.error_code.code == "not_found"
    assert err.http_status == 404
    assert err.message == "whatever message"
    assert isinstance(err, AppError)


def test_retrofit_not_found_explicit_code():
    from src.kernel.exceptions import NotFoundError

    err = NotFoundError(ErrorCode.MESSAGE_NOT_FOUND)
    assert err.error_code is ErrorCode.MESSAGE_NOT_FOUND
    assert err.args_data == {}


def test_retrofit_session_error_with_code_and_message():
    from src.kernel.exceptions import SessionError

    err = SessionError(ErrorCode.SESSION_DELETE_IN_PROGRESS)
    assert err.http_status == 409
    assert err.error_code.code == "session_delete_in_progress"


def test_retrofit_validation_error_defaults():
    from src.kernel.exceptions import ValidationError

    err = ValidationError("bad input")
    assert err.error_code.code == "validation_error"
    assert err.http_status == 422


def test_retrofit_email_not_verified_keeps_email():
    from src.kernel.exceptions import EmailNotVerifiedError

    err = EmailNotVerifiedError("verify first", "a@b.c")
    assert err.email == "a@b.c"
    assert err.error_code.code == "email_not_verified"
    assert err.http_status == 403


def test_retrofit_account_not_active():
    from src.kernel.exceptions import AccountNotActiveError

    err = AccountNotActiveError("inactive", "a@b.c")
    assert err.email == "a@b.c"
    assert err.error_code.code == "account_not_active"
    assert err.http_status == 403


def test_app_error_display_message_interpolates_args():
    """SSE/面向用户的错误文案要插值参数（{{detail}} 等占位符不留原文）。"""
    from src.kernel.errors import AppError, ErrorCode

    err = AppError(ErrorCode.SANDBOX_EXEC_FAILED, args={"detail": "expired"})
    assert err.display_message == "Local sandbox execution failed: expired"
    assert "{{" not in err.display_message


def test_app_error_display_message_without_args_returns_template():
    from src.kernel.errors import AppError, ErrorCode

    err = AppError(ErrorCode.SANDBOX_EXEC_FAILED)
    assert err.display_message == ErrorCode.SANDBOX_EXEC_FAILED.default_message
