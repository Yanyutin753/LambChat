---
name: lambchat-documents
description: "Read and create Word and PDF documents with checked outputs."
tags: [starter, documents]
---

# Document assistant

Use when reading or creating Word (.docx) or PDF documents.
1. Read uploaded files with available file-reading tools; inspect structure before rewriting. Preserve source facts and distinguish missing text from OCR uncertainty.
2. For creation, prepare JSON with `title` and a `paragraphs` list. Invoke `scripts/create_documents.py INPUT.json OUTPUT.docx` (or OUTPUT.pdf) from this skill directory.
3. Locate or copy the script from /skills/lambchat-documents/scripts/create_documents.py into an executable sandbox path using available file tools; virtual /skills paths may not be OS paths. Do not assume server Python packages exist inside the sandbox.
4. DOCX creation uses Python's standard library. PDF requires reportlab. Check the interpreter and dependency first. If uv is available, use `uv run --no-project --with reportlab python create_documents.py INPUT.json OUTPUT.pdf`; otherwise install into a sandbox-local virtual environment only when permitted. Never change the user's global environment.
5. The helper produces a simple paragraph report. For tables, images, editing or advanced layout, use python-docx in the sandbox (uv `--with python-docx`) and preserve the original file. For PDF choose an available font covering the user's language; the helper supports Simplified Chinese using STSong-Light, otherwise supply a TrueType font with `font_path`.
6. Reopen the resulting DOCX ZIP/XML or PDF with available readers. Render and inspect pages when a renderer is available; state clearly if visual layout could not be checked. Link the actual output file. Never pretend conversion or layout verification succeeded.

## Languages

Respond in the user's language.
- en: Read and create Word and PDF documents with checked outputs.
- zh: 读取和生成 Word、PDF 文档，检查实际输出。
- ja: Word・PDF文書を読み取り、作成して出力を確認します。
- ko: Word 및 PDF 문서를 읽고 생성하여 결과를 확인합니다.
- ru: Чтение и создание документов Word и PDF с проверкой результата.
