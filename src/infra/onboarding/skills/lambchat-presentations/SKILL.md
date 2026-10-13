---
name: lambchat-presentations
description: "Turn your material into a clear, editable slide deck."
tags: [starter, presentations]
---

# Presentation assistant

Use when turning user material into an editable PowerPoint (.pptx).
1. Determine audience, purpose, desired takeaway and length from the request. Outline a clear progression before creating slides. Do not invent research or numbers to fill space.
2. Prepare JSON with `title` and `slides`: each slide has `title` and a `bullets` list. Keep slide text concise and avoid overcrowding. The helper creates an editable 16:9 deck with a title and body on each slide.
3. Locate/copy /skills/lambchat-presentations/scripts/create_presentations.py into the sandbox; virtual /skills paths may not be executable paths. Check python-pptx in that sandbox. If absent and uv is available run `uv run --no-project --with python-pptx python create_presentations.py INPUT.json OUTPUT.pptx`; otherwise use a sandbox-local virtual environment when permitted. Do not change global packages.
4. Reopen the PPTX and verify slide count and text. For charts, images or advanced layouts use python-pptx directly with real user data and accessible contrast; don't add decorative stock content without purpose.
5. Render and inspect slides if a renderer is available, checking overflow and readability. If only structural checks were possible say so. Return the actual editable file and any verified preview.

## Languages

Respond in the user's language.
- en: Turn your material into a clear, editable slide deck.
- zh: 把资料组织成清晰、可编辑的演示文稿。
- ja: 資料を分かりやすく編集可能なスライドにまとめます。
- ko: 자료를 명확하고 편집 가능한 슬라이드로 구성합니다.
- ru: Создание понятных редактируемых презентаций из ваших материалов.
