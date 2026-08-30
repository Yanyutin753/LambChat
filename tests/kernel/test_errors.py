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
