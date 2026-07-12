from plugins.system.agent_team.backend.runtime.asset_delivery import (
    AssetDeliveryEvidence,
    reveal_project_files,
    uploaded_file_path_from_url,
)


def test_uploaded_file_path_is_contained_under_upload_root(tmp_path) -> None:
    root = tmp_path / "uploads"

    resolved = uploaded_file_path_from_url(
        "https://app.example.com/api/upload/file/generated-images/user/image.png",
        upload_root=str(root),
    )

    assert resolved == str(root / "generated-images" / "user" / "image.png")
    assert (
        uploaded_file_path_from_url(
            "https://app.example.com/api/upload/file//etc/passwd",
            upload_root=str(root),
        )
        is None
    )
    assert (
        uploaded_file_path_from_url(
            "https://app.example.com/api/upload/file/%2e%2e/secret.txt",
            upload_root=str(root),
        )
        is None
    )
    assert (
        uploaded_file_path_from_url(
            "https://app.example.com/api/upload/file/%5c..%5csecret.txt",
            upload_root=str(root),
        )
        is None
    )


def test_reveal_project_files_requires_successful_nonempty_manifest() -> None:
    files, error = reveal_project_files(
        {
            "type": "project_reveal",
            "files": {
                "/scenes/scene_01/first_frame.png": {"url": "/api/upload/file/image.png"},
                "/package.zip": {"url": "/api/upload/file/package.zip"},
            },
        }
    )
    assert error is None
    assert files == {"/scenes/scene_01/first_frame.png", "/package.zip"}

    assert reveal_project_files('{"type":"project_reveal","error":"upload_failed"}') == (
        set(),
        "upload_failed",
    )
    assert reveal_project_files('{"type":"project_reveal","files":{}}') == (
        set(),
        "reveal_project returned no files",
    )


def test_delivery_evidence_preserves_existing_complete_delivery() -> None:
    evidence = AssetDeliveryEvidence()
    evidence.observe(
        {
            "event": "on_tool_end",
            "name": "image_generate",
            "data": {"output": '{"success":true,"images":[{"url":"/image.png"}]}'},
        }
    )
    evidence.observe(
        {
            "event": "on_tool_end",
            "name": "reveal_project",
            "data": {
                "output": {
                    "type": "project_reveal",
                    "files": {
                        "/scenes/scene_01/first_frame.png": {},
                        "/douyin_asset_package.zip": {},
                        "/README.md": {},
                    },
                }
            },
        }
    )

    assert evidence.has_delivery_attempt is True
    assert evidence.complete is True
    assert evidence.generated_image_count == 1
    assert "完整交付" in evidence.public_summary()


def test_delivery_evidence_reports_failed_reveal_without_claiming_completion() -> None:
    evidence = AssetDeliveryEvidence()
    evidence.observe(
        {
            "event": "on_tool_end",
            "name": "reveal_project",
            "data": {"output": '{"type":"project_reveal","error":"no_files_found"}'},
        }
    )

    assert evidence.has_delivery_attempt is True
    assert evidence.complete is False
    summary = evidence.public_summary()
    assert "部分交付" in summary
    assert "no_files_found" in summary
    assert "未使用固定模板或占位图覆盖已有交付结果" in summary
