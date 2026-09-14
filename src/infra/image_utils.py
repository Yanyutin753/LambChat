"""Shared image transformation helpers."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)

IMAGE_COMPRESSION_THRESHOLD_BYTES = 5 * 1024 * 1024
IMAGE_COMPRESSION_MAX_PIXELS = 40_000_000

# Vision models and browsers both decode these natively; anything else
# uploaded as an image gets transcoded to JPEG (GLM rejects TIFF with
# error 1210 "image input format/parsing error", and canvas in browsers
# cannot decode TIFF either, so the frontend passes it through untouched).
MODEL_SAFE_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "gif", "webp"})
MODEL_SAFE_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
# Vector format Pillow cannot decode — leave it as-is instead of failing.
MODEL_UNTRANSCODABLE_EXTS = frozenset({"svg"})

TRANSCODE_JPEG_QUALITY = 90


def needs_model_safe_transcode(
    ext: str | None,
    mime_type: str | None = None,
) -> bool:
    """Return True when an image needs transcoding before a vision model sees it."""
    normalized_ext = (ext or "").strip().lower().lstrip(".")
    if normalized_ext in MODEL_SAFE_IMAGE_EXTS:
        return False
    if normalized_ext in MODEL_UNTRANSCODABLE_EXTS:
        return False

    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime in MODEL_SAFE_IMAGE_MIME_TYPES:
        return False
    if normalized_mime == "image/svg+xml":
        return False

    # Unknown formats default to transcoding: a failed transcode surfaces a
    # clear upload error, which beats passing the bytes through and letting
    # the model provider fail with an opaque 400.
    return True


def transcode_image_bytes(content: bytes) -> tuple[bytes, str]:
    """Transcode any Pillow-decodable image to a white-flattened JPEG.

    Raises ValueError when the bytes are not a decodable image (e.g. HEIC
    without pillow-heif installed).
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened)
            has_alpha = image.mode in ("RGBA", "LA", "PA") or (
                image.mode == "P" and "transparency" in opened.info
            )
            if has_alpha:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=TRANSCODE_JPEG_QUALITY)
    except Exception as exc:
        raise ValueError(f"Image transcode failed: {exc}") from exc

    return output.getvalue(), "image/jpeg"


def compress_image_bytes_if_needed(
    content: bytes,
    mime_type: str,
    *,
    threshold_bytes: int = IMAGE_COMPRESSION_THRESHOLD_BYTES,
    max_pixels: int = IMAGE_COMPRESSION_MAX_PIXELS,
) -> tuple[bytes, str]:
    """Compress oversized images for model requests without changing originals."""
    if len(content) <= threshold_bytes:
        return content, mime_type

    try:
        from PIL import Image

        with Image.open(BytesIO(content)) as image:
            pixel_count = image.width * image.height
            if pixel_count > max_pixels:
                raise ValueError(
                    f"Image has {pixel_count} pixels and exceeds pixel limit {max_pixels}"
                )
            image.load()
            output_image: Any = image
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", image.size, "white")
                background.alpha_composite(rgba)
                output_image = background.convert("RGB")
            elif image.mode not in ("RGB", "L"):
                output_image = image.convert("RGB")
            output = BytesIO()
            output_image.save(output, format="JPEG", quality=82, optimize=True)
            compressed = output.getvalue()
        if len(compressed) < len(content):
            return compressed, "image/jpeg"
    except Exception as exc:
        logger.warning("Failed to compress oversized image: %s", exc)
    return content, mime_type
