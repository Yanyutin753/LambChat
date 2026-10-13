"""Create a simple DOCX (stdlib) or PDF (reportlab) from UTF-8 JSON."""

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def create(data, output):
    title = data["title"]
    paragraphs = data["paragraphs"]
    if (
        not isinstance(title, str)
        or not isinstance(paragraphs, list)
        or not all(isinstance(p, str) for p in paragraphs)
    ):
        raise ValueError("Expected a string title and a list of string paragraphs")
    if output.suffix.lower() == ".docx":
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body = "".join(
            f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
            for text in [title, *paragraphs]
        )
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            archive.writestr(
                "_rels/.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            archive.writestr(
                "word/document.xml",
                f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{ns}"><w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>',
            )
    elif output.suffix.lower() == ".pdf":
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        if data.get("font_path"):
            pdfmetrics.registerFont(TTFont("DocumentFont", data["font_path"]))
            font = "DocumentFont"
        else:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font = "STSong-Light"
        styles = getSampleStyleSheet()
        for style in styles.byName.values():
            style.fontName = font
            style.wordWrap = "CJK"
        story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12)]
        for text in paragraphs:
            story.extend(
                [Paragraph(escape(text).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 8)]
            )
        SimpleDocTemplate(str(output), title=title).build(story)
    else:
        raise ValueError("Output must end in .docx or .pdf")


if __name__ == "__main__":
    create(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2]))
