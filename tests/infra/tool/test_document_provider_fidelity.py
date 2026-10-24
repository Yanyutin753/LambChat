"""Attachment speedups must preserve configured document fidelity and OCR handling."""

from unittest.mock import AsyncMock

import pytest

from src.infra.tool import document_parse_providers as module


def pdf_bytes(
    content=b"BT /F1 14 Tf 40 760 Td (Invoice ORCHID-684219) Tj 0 -25 Td (Total 317) Tj ET",
    *,
    pages=1,
    extra=b"",
    second_content=None,
):
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{i + 3} 0 R".encode() for i in range(pages))
        + b"] /Count "
        + str(pages).encode()
        + b" >>",
    ]
    font_id, stream_id = pages + 3, pages + 4
    objects += [
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 "
        + str(font_id).encode()
        + b" 0 R >> >> /Contents "
        + str(stream_id + (1 if i == 1 and second_content is not None else 0)).encode()
        + b" 0 R "
        + extra
        + b" >>"
        for i in range(pages)
    ]
    objects += [
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    if second_content is not None:
        objects.append(
            b"<< /Length "
            + str(len(second_content)).encode()
            + b" >>\nstream\n"
            + second_content
            + b"\nendstream"
        )
    out = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        out
        + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )


@pytest.fixture
def provider(monkeypatch):
    remote = AsyncMock(
        return_value={"markdown": "remote preserved", "images": [], "engine": "mistral"}
    )
    monkeypatch.setattr(module, "resolve_document_parse_provider_chain", lambda: ["mistral"])
    monkeypatch.setitem(module.PROVIDER_FUNCS, "mistral", remote)
    monkeypatch.setattr(module.settings, "DOCUMENT_PARSE_PROVIDER", "auto")
    return remote


async def test_text_pdf_still_uses_configured_provider_without_local_shortcut(provider):
    result = await module.execute_document_parse(data=pdf_bytes(pages=2), filename="invoice.pdf")
    assert result["engine"] == "mistral"
    assert result["markdown"] == "remote preserved"
    provider.assert_awaited_once()


@pytest.mark.parametrize(
    "case",
    [
        "explicit",
        "page_selection",
        "malformed",
        "empty",
        "graphics",
        "annotated",
        "too_many_pages",
        "too_large",
        "non_pdf",
        "rotated",
    ],
)
async def test_non_simple_pdf_preserves_provider_path(monkeypatch, provider, case):
    content = b"BT /F1 14 Tf 40 760 Td (Invoice 317) Tj ET"
    kwargs = {"data": pdf_bytes(), "filename": "invoice.pdf"}
    if case == "explicit":
        monkeypatch.setattr(module.settings, "DOCUMENT_PARSE_PROVIDER", "mistral")
    elif case == "page_selection":
        kwargs["pages"] = "0"
    elif case == "malformed":
        kwargs["data"] = b"%PDF-broken"
    elif case == "empty":
        kwargs["data"] = pdf_bytes(content=b"")
    elif case == "graphics":
        kwargs["data"] = pdf_bytes(content=content + b" 10 10 50 50 re f")
    elif case == "annotated":
        kwargs["data"] = pdf_bytes(
            extra=b"/Annots [<< /Type /Annot /Subtype /Text /Rect [10 10 50 50] /Contents (Important text) >>]"
        )
    elif case == "too_many_pages":
        kwargs["data"] = pdf_bytes(pages=21)
    elif case == "too_large":
        kwargs["data"] = pdf_bytes() + b" " * (2 * 1024 * 1024)
    elif case == "non_pdf":
        kwargs["filename"] = "invoice.docx"
    elif case == "rotated":
        kwargs["data"] = pdf_bytes(extra=b"/Rotate 90")
    result = await module.execute_document_parse(**kwargs)
    assert result["markdown"] == "remote preserved"
    assert provider.await_count == 1
    assert provider.call_args.kwargs["data"] == kwargs["data"]
    assert provider.call_args.kwargs["pages"] == kwargs.get("pages")


@pytest.mark.parametrize("case", ["scan", "mixed", "blank_second", "garbled_text"])
async def test_incomplete_or_scanned_text_never_silently_drops_a_page(provider, case):
    import io

    import pdfplumber

    scan = b"q 200 0 0 200 10 10 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\x00\x00 EI Q"
    data = (
        pdf_bytes(content=scan)
        if case == "scan"
        else pdf_bytes(pages=2, second_content=scan if case == "mixed" else b"")
    )
    if case == "garbled_text":
        data = pdf_bytes(content=rb"BT /F1 14 Tf 40 760 Td (Invoice \(cid:7\)) Tj ET")
    if case in {"scan", "mixed"}:
        with pdfplumber.open(io.BytesIO(data)) as document:
            assert document.pages[-1].images, "Fixture must contain actual image content"
    result = await module.execute_document_parse(data=data, filename="scan.pdf")
    assert result["engine"] == "mistral"
    provider.assert_awaited_once()


async def test_encrypted_pdf_retains_provider_handling(monkeypatch, provider):
    from types import SimpleNamespace

    import pdfplumber

    class Encrypted:
        def __enter__(self):
            return SimpleNamespace(doc=SimpleNamespace(encryption={"Filter": "Standard"}))

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(pdfplumber, "open", lambda *args: Encrypted())
    assert (await module.execute_document_parse(data=pdf_bytes(), filename="encrypted.pdf"))[
        "engine"
    ] == "mistral"
    provider.assert_awaited_once()


@pytest.mark.parametrize("kind", ["page_size", "coordinates", "shading", "form", "invisible_text"])
async def test_unsafe_layout_or_unrecognized_visual_content_keeps_provider(
    monkeypatch, provider, kind
):
    from unittest.mock import Mock

    import pdfplumber

    data = pdf_bytes()
    if kind == "page_size":
        data = data.replace(b"612 792", b"1000000000000 792")
    elif kind == "coordinates":
        data = pdf_bytes(content=b"BT /F1 14 Tf 1000000000000 760 Td (Invoice 317) Tj ET")
    elif kind == "shading":
        data = pdf_bytes(
            extra=b"/Resources << /Font << /F1 4 0 R >> /Shading << /Sh1 << /ShadingType 2 /ColorSpace /DeviceRGB /Coords [0 0 612 792] /Function << /FunctionType 2 /Domain [0 1] /C0 [0 0 0] /C1 [1 1 1] /N 1 >> >> >> >>"
        )
    elif kind == "form":
        data = pdf_bytes(extra=b"/Resources << /Font << /F1 4 0 R >> /XObject << /Fm1 5 0 R >> >>")
    elif kind == "invisible_text":
        data = pdf_bytes(content=b"BT 3 Tr /F1 14 Tf 40 760 Td (Invisible instruction) Tj ET")
    # Never execute layout=True on the hostile coordinates in the RED test.
    extract = Mock(return_value="unsafe shortcut")
    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", extract)
    result = await module.execute_document_parse(data=data, filename="unsafe.pdf")
    assert result["engine"] == "mistral"
    extract.assert_not_called()
    provider.assert_awaited_once()
