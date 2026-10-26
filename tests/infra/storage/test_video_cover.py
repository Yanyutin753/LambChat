import io
from unittest.mock import AsyncMock

import pytest

from src.infra.storage.s3 import media_cover as video_cover


@pytest.fixture(autouse=True)
def available_decoder(monkeypatch):
    monkeypatch.setattr(video_cover.shutil, "which", lambda _: "/usr/bin/ffmpeg")


async def test_prepares_one_small_cover_and_reuses_it(monkeypatch):
    storage = AsyncMock()
    storage.file_exists.side_effect = [False, True]
    monkeypatch.setattr(video_cover, "render_video_cover", AsyncMock(return_value=b"jpeg"))
    source = io.BytesIO(b"video")
    await video_cover.prepare_media_cover(storage, "video/owner/clip.mp4", source)
    await video_cover.prepare_media_cover(storage, "video/owner/clip.mp4", source)
    assert storage.upload_to_key.await_count == 1
    assert storage.upload_to_key.call_args.args[:2] == (
        b"jpeg",
        "covers/560x315/video/owner/clip.mp4.jpg",
    )
    assert video_cover.render_video_cover.await_count == 1


async def test_cover_failure_does_not_fail_uploaded_video(monkeypatch):
    storage = AsyncMock()
    storage.file_exists.return_value = False
    monkeypatch.setattr(
        video_cover, "render_video_cover", AsyncMock(side_effect=ValueError("unsupported"))
    )
    await video_cover.prepare_media_cover(storage, "video/owner/clip.mp4", io.BytesIO(b"bad"))
    storage.upload_to_key.assert_not_called()


async def test_non_video_does_not_probe_storage():
    storage = AsyncMock()
    await video_cover.prepare_media_cover(storage, "image/owner/a.jpg", io.BytesIO(b"image"))
    storage.file_exists.assert_not_called()


@pytest.mark.parametrize("provider", ["aws", "aliyun", "tencent", "minio", "custom", "local"])
@pytest.mark.parametrize("extension", sorted(video_cover.VIDEO_EXTENSIONS))
async def test_cached_poster_is_provider_independent(provider, extension):
    from types import SimpleNamespace

    from src.api.routes.upload_cover import get_file_cover_response

    storage = AsyncMock()
    storage._config = SimpleNamespace(provider=provider)
    storage.file_exists.return_value = True
    storage.download_file.return_value = b"jpeg"
    storage.get_cover_presigned_url.return_value = "https://signed.example/cover"
    response = await get_file_cover_response(storage, f"video/owner/clip.{extension}", None)
    assert response.status_code == (302 if provider == "aliyun" else 200)
    storage.download_to_file.assert_not_called()


async def test_audio_cover_uses_waveform_not_video_decoder(monkeypatch):
    storage = AsyncMock()
    storage.file_exists.return_value = False
    audio = AsyncMock(return_value=b"waveform")
    monkeypatch.setattr(video_cover, "render_audio_cover", audio, raising=False)
    assert await video_cover.prepare_media_cover(storage, "audio/me/clip.mp3", io.BytesIO(b"audio"))
    audio.assert_awaited_once()
