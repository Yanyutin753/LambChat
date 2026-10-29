"""Cloud upload compression preserves semantics and never silently ignores failures."""

from io import BytesIO

import pytest
from PIL import Image

from src.infra import image_utils


def encoded(fmt, size=(3000, 1500), mode="RGB"):
    buf = BytesIO()
    Image.new(mode, size, (20, 40, 60, 0) if mode == "RGBA" else (20, 40, 60)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    "ext,mime,size,want",
    [
        ("TIFF", "", 100, True),
        ("heic", "image/heic", 100, True),
        ("jpg", "image/jpeg", 300 * 1024, True),
        ("png", "", 300 * 1024, True),
        ("png", "image/png", 100, False),
        ("gif", "image/gif", 300 * 1024, False),
        ("svg", "image/svg+xml", 300 * 1024, False),
    ],
)
def test_upload_processing_routes_only_images_requiring_compression(ext, mime, size, want):
    assert image_utils.needs_upload_image_processing(ext, mime, size) is want


def test_large_tiff_is_resized_and_transcoded_in_cloud():
    content = encoded("TIFF")
    output, mime = image_utils.prepare_upload_image_bytes(content, "image/tiff", source_ext="tiff")
    assert mime == "image/jpeg"
    assert len(output) < len(content)
    with Image.open(BytesIO(output)) as image:
        assert image.size == (1920, 960)
        assert image.format == "JPEG"


def test_large_png_preserves_transparency_and_format():
    content = encoded("PNG", mode="RGBA") + b"x" * (210 * 1024)
    output, mime = image_utils.prepare_upload_image_bytes(content, "", source_ext="png")
    assert mime == "image/png"
    assert len(output) < len(content)
    with Image.open(BytesIO(output)) as image:
        assert image.size == (1920, 960)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0


def test_large_jpeg_is_compressed_even_if_browser_did_no_work():
    content = encoded("JPEG") + b"x" * (210 * 1024)
    output, mime = image_utils.prepare_upload_image_bytes(content, "image/jpeg", source_ext="jpg")
    assert mime == "image/jpeg"
    assert len(output) < len(content)
    with Image.open(BytesIO(output)) as image:
        assert image.size == (1920, 960)


@pytest.mark.parametrize(
    "ext,mime,content",
    [
        ("jpg", "image/jpeg", encoded("JPEG", (20, 20))),
        ("gif", "image/gif", encoded("GIF", (20, 20)) + b"x" * (210 * 1024)),
        ("svg", "image/svg+xml", b"<svg></svg>" + b" " * (210 * 1024)),
    ],
    ids=["small-jpeg", "gif", "svg"],
)
def test_small_images_animation_and_vectors_remain_intact(ext, mime, content):
    assert image_utils.prepare_upload_image_bytes(content, mime, source_ext=ext) == (content, mime)


def test_invalid_image_compression_fails_instead_of_publishing_original():
    with pytest.raises(ValueError):
        image_utils.prepare_upload_image_bytes(b"broken" * 50000, "image/jpeg", source_ext="jpg")


def test_cloud_compression_enforces_pixel_limit_before_decoding(monkeypatch):
    monkeypatch.setattr(image_utils, "IMAGE_COMPRESSION_MAX_PIXELS", 3)
    with pytest.raises(ValueError):
        image_utils.prepare_upload_image_bytes(
            encoded("TIFF", (2, 2)), "image/tiff", source_ext="tiff"
        )


@pytest.mark.parametrize("limit,expected", [(10, 20), (40, 50), (60, 60)])
def test_raw_image_intake_is_bounded_and_final_limit_is_not_changed(limit, expected):
    assert image_utils.image_upload_input_limit(limit * 1024 * 1024) == expected * 1024 * 1024


def test_tiff_alpha_is_flattened_onto_white_in_cloud():
    output, mime = image_utils.prepare_upload_image_bytes(
        encoded("TIFF", (40, 30), "RGBA"), "image/tiff", source_ext="tiff"
    )
    assert mime == "image/jpeg"
    with Image.open(BytesIO(output)) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_cloud_jpeg_quality_is_reduced_to_the_existing_size_target():
    import random

    image = Image.frombytes("RGB", (2000, 2000), random.Random(0).randbytes(2000 * 2000 * 3))
    source = BytesIO()
    image.save(source, format="TIFF")
    output, mime = image_utils.prepare_upload_image_bytes(
        source.getvalue(), "image/tiff", source_ext="tiff"
    )
    assert mime == "image/jpeg"
    assert len(output) <= 1024 * 1024
