import type { WorkSheet } from "xlsx";

export type ExcelDisplayRows = string[][];

interface ExcelUtils {
  decode_range: (range: string) => {
    s: { r: number; c: number };
    e: { r: number; c: number };
  };
  encode_cell: (cell: { r: number; c: number }) => string;
  format_cell: (cell: WorkSheet[string]) => string;
}

function cellDisplayValue(
  sheet: WorkSheet,
  address: string,
  utils: ExcelUtils,
): string {
  const cell = sheet[address];
  if (!cell || cell.v == null || cell.v === "") return "";
  if (cell.w != null && cell.w !== "") return String(cell.w);
  const formatted = utils.format_cell(cell);
  return formatted != null && formatted !== ""
    ? String(formatted)
    : String(cell.v);
}

export function worksheetToDisplayRows(
  sheet: WorkSheet,
  utils: ExcelUtils,
): ExcelDisplayRows {
  if (!sheet["!ref"]) return [];
  const range = utils.decode_range(sheet["!ref"]);
  if (range.e.r < range.s.r || range.e.c < range.s.c) return [];

  const rows: ExcelDisplayRows = [];
  for (let row = range.s.r; row <= range.e.r; row += 1) {
    const values: string[] = [];
    for (let col = range.s.c; col <= range.e.c; col += 1) {
      values.push(
        cellDisplayValue(sheet, utils.encode_cell({ r: row, c: col }), utils),
      );
    }
    rows.push(values);
  }
  return rows.some((row) => row.some((value) => value !== "")) ? rows : [];
}
