import logging
from io import BytesIO

import pytest
from PIL import Image

from src.infra.image_utils import (
    IMAGE_COMPRESSION_THRESHOLD_BYTES,
    compress_image_bytes_if_needed,
    needs_model_safe_transcode,
    transcode_image_bytes,
)


def _transparent_png_over_threshold() -> bytes:
    source = BytesIO()
    Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(source, format="PNG")
    return source.getvalue() + b"x" * IMAGE_COMPRESSION_THRESHOLD_BYTES


def _palette_transparent_png_over_threshold() -> bytes:
    source = BytesIO()
    image = Image.new("P", (32, 32), 0)
    image.putpalette([255, 0, 0] + [0, 0, 0] * 255)
    image.save(source, format="PNG", transparency=0)
    return source.getvalue() + b"x" * IMAGE_COMPRESSION_THRESHOLD_BYTES


def test_compress_large_transparent_image_flattens_alpha_to_white():
    original = _transparent_png_over_threshold()

    compressed, mime_type = compress_image_bytes_if_needed(original, "image/png")

    with Image.open(BytesIO(compressed)) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
    assert len(compressed) < len(original)
    assert mime_type == "image/jpeg"
    assert pixel == (255, 255, 255)


def test_compress_large_palette_transparency_flattens_to_white():
    original = _palette_transparent_png_over_threshold()

    compressed, mime_type = compress_image_bytes_if_needed(original, "image/png")

    with Image.open(BytesIO(compressed)) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
    assert mime_type == "image/jpeg"
    assert pixel == (255, 255, 255)


def test_compress_small_image_keeps_original_content_and_mime_type():
    original = b"small-image"

    compressed, mime_type = compress_image_bytes_if_needed(original, "image/png")

    assert compressed == original
    assert mime_type == "image/png"


def test_compress_invalid_large_image_logs_warning_and_keeps_original(caplog):
    original = b"not-an-image" + b"x" * IMAGE_COMPRESSION_THRESHOLD_BYTES

    with caplog.at_level(logging.WARNING):
        compressed, mime_type = compress_image_bytes_if_needed(original, "image/png")

    assert compressed == original
    assert mime_type == "image/png"
    assert "Failed to compress oversized image" in caplog.text


def test_compress_refuses_image_over_pixel_limit(caplog):
    source = BytesIO()
    Image.new("RGB", (3, 2), "red").save(source, format="PNG")
    original = source.getvalue() + b"x" * IMAGE_COMPRESSION_THRESHOLD_BYTES

    with caplog.at_level(logging.WARNING):
        compressed, mime_type = compress_image_bytes_if_needed(
            original,
            "image/png",
            max_pixels=4,
        )

    assert compressed == original
    assert mime_type == "image/png"
    assert "exceeds pixel limit" in caplog.text


# ── 模型安全格式转码（TIFF 等视觉模型不支持的格式 → JPEG）─────────────────


def _tiff_bytes(mode: str = "RGB", size: tuple[int, int] = (40, 30)) -> bytes:
    source = BytesIO()
    color = (10, 20, 30) if mode == "RGB" else (10, 20, 30, 0)
    Image.new(mode, size, color).save(source, format="TIFF")
    return source.getvalue()


def test_needs_model_safe_transcode_by_extension():
    # 视觉模型/浏览器都支持的格式不转
    for safe_ext in ("jpg", "jpeg", "png", "gif", "webp"):
        assert needs_model_safe_transcode(safe_ext) is False
    # TIFF/BMP/ICO 视觉模型解不了（GLM 1210），需要转码
    for unsafe_ext in ("tiff", "tif", "bmp", "ico"):
        assert needs_model_safe_transcode(unsafe_ext) is True


def test_needs_model_safe_transcode_ignores_case_and_dot():
    assert needs_model_safe_transcode(".TIFF") is True
    assert needs_model_safe_transcode(" JPG ") is False


def test_needs_model_safe_transcode_mime_fallback_when_ext_missing():
    assert needs_model_safe_transcode(None, "image/tiff") is True
    assert needs_model_safe_transcode(None, "image/jpeg") is False
    assert needs_model_safe_transcode("", "image/bmp") is True


def test_needs_model_safe_transcode_leaves_svg_alone():
    # SVG 是矢量，Pillow 解不了，维持原样不转码
    assert needs_model_safe_transcode("svg", "image/svg+xml") is False


def test_needs_model_safe_transcode_unknown_format_defaults_to_transcode():
    # 未知格式宁可尝试转码：失败时上传会得到明确报错，好过透传给模型吃 1210
    assert needs_model_safe_transcode(None, None) is True


def test_transcode_tiff_to_jpeg_keeps_dimensions():
    transcoded, mime_type = transcode_image_bytes(_tiff_bytes())

    assert mime_type == "image/jpeg"
    with Image.open(BytesIO(transcoded)) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)


def test_transcode_rgba_tiff_flattens_alpha_to_white():
    transcoded, mime_type = transcode_image_bytes(_tiff_bytes(mode="RGBA"))

    assert mime_type == "image/jpeg"
    with Image.open(BytesIO(transcoded)) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
    # 透明区域合成白底，而不是 JPEG 转换的黑色
    assert pixel == (255, 255, 255)


def test_transcode_invalid_bytes_raises_value_error():
    with pytest.raises(ValueError):
        transcode_image_bytes(b"not-an-image-at-all")
