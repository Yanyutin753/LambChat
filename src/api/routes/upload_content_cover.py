"""Bounded, offline content previews; never execute a file or call a model."""

import io
import textwrap
import zipfile
from html.parser import HTMLParser

from defusedxml import ElementTree
from PIL import Image, ImageDraw, ImageOps

TEXT_EXTENSIONS = set(
    "txt md markdown csv json xml html htm log yaml yml toml ini cfg tex diff patch py js ts jsx tsx vue svelte go rs rb php java c cpp h cs swift kt scala dart lua r pl sql sh bash zsh fish ps1 bat cmd properties gradle cmake env graphql proto css scss sas".split()
)
OFFICE_EXTENSIONS = {"docx", "pptx", "odt", "ods", "odp", "epub"}
CONTENT_COVER_EXTENSIONS = TEXT_EXTENSIONS | OFFICE_EXTENSIONS | {"zip"}
_MAX_TEXT = 6000


def _checked_archive(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    entries = archive.infolist()
    if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 64 * 1024 * 1024:
        archive.close()
        raise ValueError("Preview archive is too large")
    if any(entry.file_size > max(1, entry.compress_size) * 100 for entry in entries):
        archive.close()
        raise ValueError("Preview archive expansion is too large")
    return archive


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.lines.append(data.strip())


def preview_text(data: bytes, ext: str) -> str:
    if ext in OFFICE_EXTENSIONS | {"zip"}:
        with _checked_archive(data) as archive:
            if ext == "zip":
                return "\n".join(entry.filename[:200] for entry in archive.infolist()[:24])[
                    :_MAX_TEXT
                ]
            if ext in {"odt", "ods", "odp"}:
                root = ElementTree.fromstring(archive.read("content.xml"))
                return "\n".join(text.strip() for text in root.itertext() if text.strip())[
                    :_MAX_TEXT
                ]
            if ext == "epub":
                names = [
                    name
                    for name in archive.namelist()
                    if name.endswith((".xhtml", ".html", ".htm"))
                ]
                parser = _HTMLText()
                for name in names[:3]:
                    parser.feed(archive.read(name)[:65536].decode("utf-8", errors="replace"))
                return "\n".join(parser.lines)[:_MAX_TEXT]
        from markitdown import MarkItDown

        result = MarkItDown(enable_plugins=False).convert_stream(
            io.BytesIO(data), file_extension="." + ext
        )
        return str(result.text_content or "")[:_MAX_TEXT]
    text = data[:65536].decode("utf-8-sig", errors="replace")
    if ext in {"html", "htm"}:
        parser = _HTMLText()
        parser.feed(text)
        text = "\n".join(parser.lines)
    if "\x00" in text:
        raise ValueError("Binary content is not a text preview")
    return text[:_MAX_TEXT]


def render_content_cover(data: bytes, ext: str) -> bytes:
    from src.api.routes.upload_cover import _cached_sheet_font

    text = preview_text(data, ext)
    # Office generators often retain a template thumbnail after editing the document.
    if not text.strip() and ext in OFFICE_EXTENSIONS:
        with _checked_archive(data) as archive:
            for name in (
                "docProps/thumbnail.jpeg",
                "docProps/thumbnail.jpg",
                "docProps/thumbnail.png",
                "Thumbnails/thumbnail.png",
            ):
                if name in archive.namelist():
                    with Image.open(io.BytesIO(archive.read(name))) as embedded:
                        image = ImageOps.contain(embedded.convert("RGB"), (560, 315))
                        output = io.BytesIO()
                        image.save(output, "JPEG", quality=85)
                        return output.getvalue()
    if not text.strip():
        raise ValueError("No preview content")
    image = Image.new("RGB", (560, 315), "#fafaf9")
    draw = ImageDraw.Draw(image)
    font = _cached_sheet_font(17)
    y = 20
    for paragraph in text.splitlines():
        for line in textwrap.wrap(paragraph.expandtabs(2), width=48, replace_whitespace=False) or [
            ""
        ]:
            while line and draw.textlength(line, font=font) > 520:
                line = line[:-1]
            draw.text((20, y), line, font=font, fill="#292524")
            y += 25
            if y > 295:
                output = io.BytesIO()
                image.save(output, "JPEG", quality=85)
                return output.getvalue()
    output = io.BytesIO()
    image.save(output, "JPEG", quality=85)
    return output.getvalue()
