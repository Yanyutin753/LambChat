from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.agents.core.node_utils import build_human_message
from src.kernel.errors import AppError
from src.kernel.schemas.agent import AttachmentSchema


def local(path="/Users/me/original.tiff", machine="m1"):
    return dict(
        id="file1",
        name="original.tiff",
        type="image",
        mimeType="image/tiff",
        size=42,
        localFile=dict(path=path, machineId=machine, token="a" * 32),
    )


def test_local_reference_needs_no_upload_key_or_url():
    item = AttachmentSchema.model_validate(local())
    assert item.key == "" and item.url == ""
    assert item.model_dump()["local_file"]["path"] == "/Users/me/original.tiff"


@pytest.mark.parametrize("path", ["relative.txt", "https://example.com/a", "/tmp/a\x00b"])
def test_local_reference_rejects_non_filesystem_paths(path):
    with pytest.raises(ValidationError):
        AttachmentSchema.model_validate(local(path))


@pytest.mark.parametrize("path", ["/tmp/a b.txt", r"C:\Users\me\a.txt", r"\\server\share\a.txt"])
def test_local_reference_accepts_desktop_absolute_paths(path):
    assert AttachmentSchema.model_validate(local(path)).local_file.path == path


def test_cloud_attachment_still_requires_key_and_url():
    payload = local()
    payload.pop("localFile")
    with pytest.raises(ValidationError):
        AttachmentSchema.model_validate(payload)
    payload.update(key="images/a", url="/api/upload/file/images/a")
    assert AttachmentSchema.model_validate(payload).key == "images/a"


def test_local_reference_is_not_a_cloud_image_url():
    item = AttachmentSchema.model_validate(local()).model_dump()
    message = build_human_message("Read this", [item], supports_vision=True)
    assert isinstance(message.content, str)
    assert "/Users/me/original.tiff" in message.content
    assert "image_analyze" in message.content
    assert "upload_url_to_sandbox" not in message.content


@pytest.mark.parametrize(
    "options", [{}, {"sandbox": "cloud"}, {"sandbox": "local", "sandbox_machine_id": "other"}]
)
async def test_submission_rejects_incompatible_environment(options):
    from src.infra.upload.local_attachments import validate_local_attachments

    with pytest.raises(AppError):
        await validate_local_attachments([AttachmentSchema.model_validate(local())], options, "u1")


async def test_submission_resolves_only_owner_and_exact_machine():
    from src.infra.upload.local_attachments import validate_local_attachments

    with patch(
        "src.infra.sandbox.relay.registry.SandboxClientRegistry.resolve_target",
        new_callable=AsyncMock,
        return_value="m1",
    ) as resolve:
        await validate_local_attachments(
            [AttachmentSchema.model_validate(local())],
            {"sandbox": "local", "sandbox_machine_id": "m1"},
            "u1",
        )
        resolve.assert_awaited_once_with("u1", "m1")
    with patch(
        "src.infra.sandbox.relay.registry.SandboxClientRegistry.resolve_target",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(AppError):
            await validate_local_attachments(
                [AttachmentSchema.model_validate(local())],
                {"sandbox": "local", "sandbox_machine_id": "m1"},
                "u1",
            )


async def test_tiff_path_analysis_converts_small_original_without_object_upload():
    import base64
    import io

    from PIL import Image

    from src.infra.tool import image_analysis_tool

    raw = io.BytesIO()
    Image.new("RGB", (5, 5), "red").save(raw, format="TIFF")
    with (
        patch.object(image_analysis_tool, "get_backend_from_runtime", return_value=object()),
        patch.object(
            image_analysis_tool,
            "_download_file_from_backend",
            new_callable=AsyncMock,
            return_value=raw.getvalue(),
        ),
    ):
        result = await image_analysis_tool._inline_backend_image_paths(
            [{"url": "/tmp/a.tiff", "type": "image"}], object()
        )
    assert result[0]["data_url"].startswith("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.b64decode(result[0]["data_url"].split(",", 1)[1]))) as image:
        assert image.format == "JPEG"


async def test_local_reference_rejected_for_an_agent_without_sandbox():
    from types import SimpleNamespace

    from src.infra.upload.local_attachments import validate_local_attachments

    with patch(
        "src.agents.core.base.get_agent_class",
        return_value=SimpleNamespace(_supports_sandbox=False),
    ):
        with pytest.raises(AppError):
            await validate_local_attachments(
                [AttachmentSchema.model_validate(local())],
                {"sandbox": "local", "sandbox_machine_id": "m1"},
                "u1",
                "quick",
            )
