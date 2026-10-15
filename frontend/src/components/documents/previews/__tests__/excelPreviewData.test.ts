import * as XLSX from "xlsx";
import { worksheetToDisplayRows } from "../excelPreviewData.ts";

test("uses formatted worksheet text for date cells", () => {
  const worksheet = XLSX.utils.aoa_to_sheet([["month"], [46143.33383101852]]);
  worksheet.A2.z = "mmm-yy";

  const rows = worksheetToDisplayRows(worksheet, XLSX.utils);

  expect(rows).toEqual([["month"], ["May-26"]]);
});

// Exercise the same byte-array reader as ExcelPreview against actual workbook files.
test.each(["xlsx", "biff8", "ods"] as const)(
  "reads a real %s workbook with Unicode, multiple sheets, and blank cells",
  (bookType) => {
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([
      ["Name", "Amount", "Enabled", "Notes"],
      ["Résumé 中文报告", 1234.5, true, ""],
    ]), "交付成果");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([
      ["second sheet"], ["保留内容"],
    ]), "Details");

    const bytes = XLSX.write(workbook, { type: "array", bookType });
    const restored = XLSX.read(bytes, { type: "array" });

    expect(restored.SheetNames).toEqual(["交付成果", "Details"]);
    expect(restored.Sheets["交付成果"].B2.v).toBe(1234.5);
    expect(restored.Sheets["交付成果"].C2.v).toBe(true);
    expect(worksheetToDisplayRows(restored.Sheets["交付成果"], XLSX.utils)).toEqual([
      ["Name", "Amount", "Enabled", "Notes"],
      ["Résumé 中文报告", "1234.5", "TRUE", ""],
    ]);
    expect(worksheetToDisplayRows(restored.Sheets.Details, XLSX.utils)).toEqual([
      ["second sheet"], ["保留内容"],
    ]);
  },
);

test.each(["xlsx", "biff8"] as const)(
  "preserves date and number display formats after a real %s roundtrip",
  (bookType) => {
    const sheet = XLSX.utils.aoa_to_sheet([["Date", "Amount"], [46143, 1234.5]]);
    sheet.A2.z = "yyyy-mm-dd";
    sheet.B2.z = "0.00";
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, sheet, "Formatted");

    const bytes = XLSX.write(workbook, { type: "array", bookType });
    const restored = XLSX.read(bytes, { type: "array" });

    expect(worksheetToDisplayRows(restored.Sheets.Formatted, XLSX.utils)).toEqual([
      ["Date", "Amount"], ["2026-05-01", "1234.50"],
    ]);
  },
);
