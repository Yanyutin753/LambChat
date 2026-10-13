---
name: lambchat-spreadsheets
description: "Clean tables, analyze data and create spreadsheets and charts."
tags: [starter, spreadsheets]
---

# Data analyst

Use when reading, cleaning or generating CSV/XLSX data.
1. Inspect headers, types, encodings, units and missing values. Keep the source unchanged. Never silently turn identifiers into numbers, drop rows or guess missing financial values.
2. Prefer Python csv for simple CSV. For XLSX prepare JSON containing `headers`, `rows`, optional `sheet_name` and optional `chart` with `title`, `category_column` and `value_column` (1-based). Run scripts/create_spreadsheets.py INPUT.json OUTPUT.xlsx.
3. Locate/copy /skills/lambchat-spreadsheets/scripts/create_spreadsheets.py into the execution sandbox; /skills can be virtual. Check openpyxl in the sandbox. If absent and uv is available use `uv run --no-project --with openpyxl python create_spreadsheets.py INPUT.json OUTPUT.xlsx`; otherwise use a sandbox-local virtual environment when allowed. Do not change global packages.
4. The helper writes literal data: strings beginning with =, +, -, @ remain text. Create formulas deliberately with openpyxl only when requested; inspect formulas and cached values separately because openpyxl does not calculate them. Do not claim formula recalculation without an actual spreadsheet engine.
5. Reopen the workbook; compare row count, representative values, totals, types and any chart references against the source. Explain filters and assumptions, then provide the actual workbook path.

## Languages

Respond in the user's language.
- en: Clean tables, analyze data and create spreadsheets and charts.
- zh: 清洗表格、分析数据，生成工作簿与图表。
- ja: 表の整理、データ分析、ワークブックとグラフの作成を行います。
- ko: 표를 정리하고 데이터를 분석하여 통합 문서와 차트를 만듭니다.
- ru: Очистка таблиц, анализ данных, создание книг и диаграмм.
