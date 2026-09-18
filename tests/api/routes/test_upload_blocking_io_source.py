"""Upload routes must keep CPU/IO-heavy hashing off the event loop.

Source-structure test: sha256 hashing of upload payloads (per-chunk during
spooling and one-shot over transcoded image bytes) runs in the blocking-io
pool via run_blocking_io, and every remaining sync open()/PIL render path in
the upload route family stays wrapped as well.
"""

from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "src" / "api" / "routes"


def _source(name: str) -> str:
    return (UPLOAD_DIR / name).read_text(encoding="utf-8")


def test_spool_hash_updates_run_in_blocking_pool() -> None:
    source = _source("upload.py")
    assert "run_blocking_io(digest.update, chunk)" in source
    # The bare per-chunk hash update must not run on the event loop
    assert "\n            digest.update(chunk)" not in source


def test_transcoded_image_hash_runs_in_blocking_pool() -> None:
    source = _source("upload.py")
    assert "run_blocking_io(sha256_hexdigest, transcoded)" in source
    # One-shot hash of the full transcoded buffer must not run inline
    assert "digest = hashlib.sha256(transcoded)" not in source


def test_local_thumb_and_cover_render_stay_off_event_loop() -> None:
    assert "run_blocking_io(_read_and_render)" in _source("upload_thumb.py")
    assert "run_blocking_io(_read_and_render)" in _source("upload_cover.py")
    assert "run_blocking_io(_read_and_transcode)" in _source("upload_model_safe.py")


def test_pil_render_helpers_are_only_called_via_blocking_pool() -> None:
    thumb = _source("upload_thumb.py")
    assert "run_blocking_io(render_chat_thumb" in thumb
    model_safe = _source("upload_model_safe.py")
    assert "run_blocking_io(transcode_image_bytes" in model_safe
    cover = _source("upload_cover.py")
    assert "run_blocking_io(render, data)" in cover
